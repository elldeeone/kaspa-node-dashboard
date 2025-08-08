"""
Persistent WebSocket RPC client for Kaspa node with live event subscriptions.
"""
import asyncio
import json
import logging
import time
from enum import Enum
from typing import Dict, Any, Optional, Tuple
import aiohttp
from datetime import datetime
from log_sync_analyzer import LogSyncAnalyzer
from log_parser import KaspadLogParser
from peer_model import PeerInfo, PeerInfoCollection
from config import (
    CONNECTION_TIMEOUT, SOCKET_READ_TIMEOUT, HEARTBEAT_INTERVAL,
    REQUEST_TIMEOUT, CLEANUP_INTERVAL, HEALTH_CHECK_INTERVAL,
    ONESHOT_TIMEOUT, MAX_ONESHOT_RETRIES,
    INITIAL_RETRY_DELAY, MAX_RETRY_DELAY, RETRY_BACKOFF_FACTOR,
    SUBSCRIPTION_RETRY_DELAY, MAX_SUBSCRIPTION_RETRY_DELAY,
    MAX_CONNECTION_FAILURES, CIRCUIT_BREAKER_COOLDOWN,
    CONNECTION_POOL_SIZE, CONNECTION_POOL_TIMEOUT
)

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """Connection state machine for better state management."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    SUBSCRIBED = "subscribed"
    RECONNECTING = "reconnecting"

class PersistentKaspadRPCClient:
    """Persistent WebSocket connection to kaspad with event subscriptions."""
    
    def __init__(self, host: str, port: int, 
                 connection_timeout: int = CONNECTION_TIMEOUT,
                 socket_read_timeout: int = SOCKET_READ_TIMEOUT,
                 retry_delay: int = INITIAL_RETRY_DELAY,
                 max_retries: int = MAX_CONNECTION_FAILURES):
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}"
        
        # Configurable timeouts and retries
        self.connection_timeout = connection_timeout
        self.socket_read_timeout = socket_read_timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        
        # Connection state - using state machine
        self.ws = None
        self.session = None
        self.state = ConnectionState.DISCONNECTED
        self.reconnect_task = None
        
        # Connection pool for oneshot calls
        self.connection_pool = []
        self.pool_lock = asyncio.Lock()
        
        # Connection pool metrics
        self.pool_metrics = {
            "total_connections": 0,
            "active_connections": 0,
            "idle_connections": 0,
            "connection_reuse_count": 0,
            "connection_creation_count": 0,
            "failed_connections": 0,
            "avg_connection_duration": 0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "last_updated": time.time()
        }
        
        # Circuit breaker for connection failures
        self.connection_failures = 0
        self.last_connection_attempt = 0
        self.max_failures = max_retries
        
        # Health check task
        self.health_check_task = None
        self.last_health_check = time.time()
        
        # Message handling with cleanup tracking
        self.request_id = 0
        self.pending_requests = {}  # {request_id: (future, timestamp)}
        self.request_lock = asyncio.Lock()  # Lock to prevent race conditions
        self.request_timeout = REQUEST_TIMEOUT
        self.cleanup_interval = CLEANUP_INTERVAL
        self.last_cleanup = time.time()
        
        # Cached live data
        self.cached_data = {
            "node_info": None,
            "blockdag_info": None,
            "peer_info": None,
            "mempool": None,
            "sync_status": None,
            "last_update": None,
            "is_synced": False,
            "latest_block": None
        }
        
        # Subscription state and retry logic
        self.subscription_retry_count = 0
        self.max_subscription_retries = 5
        self.subscription_retry_delay = SUBSCRIPTION_RETRY_DELAY
        self.subscription_retry_task = None
        
        # Log-based sync progress tracking
        self.log_sync_analyzer = LogSyncAnalyzer()
        
        # Log parser for extracting peer info during IBD
        self.log_parser = KaspadLogParser()
        
        # Log parsing cache to reduce file I/O
        self._log_cache = None
        self._log_cache_timestamp = 0
        self._log_cache_ttl = 30  # Cache for 30 seconds
        
        # Network DAA cache to reduce API calls
        self._network_daa_cache = None
        self._network_daa_cache_timestamp = 0
        self._network_daa_cache_ttl = 300  # Cache for 5 minutes (network DAA doesn't change that fast)
        
    async def connect(self):
        """Establish persistent WebSocket connection with circuit breaker."""
        # Circuit breaker check
        if self.connection_failures >= self.max_failures:
            time_since_last = time.time() - self.last_connection_attempt
            if time_since_last < CIRCUIT_BREAKER_COOLDOWN:
                logger.warning("Circuit breaker active",
                             extra={"failures": self.connection_failures,
                                   "cooldown_remaining": CIRCUIT_BREAKER_COOLDOWN - time_since_last})
                return False
            else:
                # Reset circuit breaker after cooldown
                self.connection_failures = 0
                logger.info("Circuit breaker reset after cooldown")
        
        self.last_connection_attempt = time.time()
        self.state = ConnectionState.CONNECTING
        
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            
            logger.info("Connecting to kaspad",
                       extra={"host": self.host, "port": self.port})
            
            # Use configurable timeout settings
            self.ws = await self.session.ws_connect(
                self.ws_url,
                timeout=aiohttp.ClientTimeout(total=self.connection_timeout, 
                                             sock_read=self.socket_read_timeout),
                heartbeat=HEARTBEAT_INTERVAL,
                autoping=True,  # Auto-ping to keep connection alive
                autoclose=False  # Don't auto-close on server messages
            )
            
            self.state = ConnectionState.CONNECTED
            logger.info("WebSocket connection established",
                       extra={"state": self.state.value})
            
            # Reset failure count on successful connection
            self.connection_failures = 0
            
            # Start message handler with cleanup
            asyncio.create_task(self._message_handler())
            
            # Start periodic cleanup task
            asyncio.create_task(self._periodic_cleanup())
            
            # Start health check task
            if not self.health_check_task:
                self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            # Try subscriptions with retry logic (but don't fail if they don't work during IBD)
            try:
                await self._subscribe_with_retry()
            except (ConnectionError, TimeoutError) as e:
                logger.warning("Initial subscription failed (normal during IBD)",
                             extra={"error": str(e), "state": "IBD"})
            except Exception as e:
                logger.error("Unexpected subscription error",
                            extra={"error": str(e)}, exc_info=True)
            
            # Initial data fetch
            await self._fetch_initial_data()
            
            self.state = ConnectionState.READY
            return True
            
        except aiohttp.ClientError as e:
            logger.warning("Connection attempt failed",
                          extra={"error": str(e), "failures": self.connection_failures + 1})
            self.connection_failures += 1
            self.state = ConnectionState.DISCONNECTED
            return False
        except Exception as e:
            logger.error("Unexpected connection error",
                        extra={"error": str(e)}, exc_info=True)
            self.connection_failures += 1
            self.state = ConnectionState.DISCONNECTED
            return False
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages."""
        try:
            while self.connected and self.ws:
                try:
                    # Add timeout to prevent infinite hangs
                    msg = await asyncio.wait_for(
                        self.ws.receive(),
                        timeout=self.socket_read_timeout
                    )
                except asyncio.TimeoutError:
                    # Timeout is normal - just continue the loop
                    # This prevents infinite hangs while still maintaining the connection
                    continue
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Handle RPC responses
                    if "id" in data:
                        request_id = data["id"]
                        async with self.request_lock:
                            if request_id in self.pending_requests:
                                future, _ = self.pending_requests.pop(request_id)
                                if "error" in data:
                                    error_msg = data.get("error", "Unknown error")
                                    future.set_exception(ConnectionError(f"RPC error: {error_msg}"))
                                else:
                                    # Basic RPC response validation
                                    result = data.get("params", data)
                                    if self._validate_rpc_response(result):
                                        future.set_result(result)
                                    else:
                                        future.set_exception(ValueError("Invalid RPC response format"))
                    
                    # Handle notifications (these come from subscriptions)
                    elif "method" in data:
                        # Only handle if we're subscribed
                        if self.state == ConnectionState.SUBSCRIBED:
                            await self._handle_notification(data)
                        
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WebSocket error",
                                extra={"error": str(self.ws.exception())})
                    break
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed",
                               extra={"state": self.state.value})
                    break
                    
        except asyncio.CancelledError:
            logger.info("Message handler cancelled")
            raise
        except Exception as e:
            logger.error("Message handler error",
                        extra={"error": str(e)}, exc_info=True)
        finally:
            self.state = ConnectionState.DISCONNECTED
            # Schedule reconnection if not already scheduled
            if not self.reconnect_task:
                self.reconnect_task = asyncio.create_task(self._reconnect())
    
    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff and circuit breaker."""
        self.state = ConnectionState.RECONNECTING
        delay = self.retry_delay
        max_delay = MAX_RETRY_DELAY
        
        while self.state != ConnectionState.READY:
            # Check circuit breaker
            if self.connection_failures >= self.max_failures:
                logger.warning("Circuit breaker triggered",
                             extra={"failures": self.connection_failures})
                delay = CIRCUIT_BREAKER_COOLDOWN
            
            logger.info("Attempting reconnection",
                       extra={"delay": delay, "attempt": self.connection_failures})
            await asyncio.sleep(delay)
            
            if await self.connect():
                logger.info("Reconnection successful",
                           extra={"attempts": self.connection_failures})
                self.reconnect_task = None
                break
            
            # Exponential backoff
            delay = min(delay * RETRY_BACKOFF_FACTOR, max_delay)
    
    async def _periodic_cleanup(self):
        """Periodically clean up old pending requests to prevent memory leaks."""
        while self.state in [ConnectionState.CONNECTED, ConnectionState.READY, ConnectionState.SUBSCRIBED]:
            try:
                current_time = time.time()
                if current_time - self.last_cleanup > self.cleanup_interval:
                    expired_requests = []
                    
                    async with self.request_lock:
                        # Identify expired requests
                        for req_id, (future, timestamp) in list(self.pending_requests.items()):
                            if current_time - timestamp > self.request_timeout:
                                expired_requests.append(req_id)
                                if not future.done():
                                    future.set_exception(asyncio.TimeoutError(f"Request {req_id} timed out"))
                        
                        # Remove expired requests
                        for req_id in expired_requests:
                            self.pending_requests.pop(req_id, None)
                            logger.debug("Cleaned up expired request",
                                       extra={"request_id": req_id})
                    
                    if expired_requests:
                        logger.info("Cleaned up expired requests",
                                  extra={"count": len(expired_requests)})
                    
                    self.last_cleanup = current_time
                
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            except Exception as e:
                logger.error("Error in periodic cleanup",
                            extra={"error": str(e)}, exc_info=True)
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
    
    def _validate_rpc_response(self, response: Any) -> bool:
        """Validate RPC response format and content."""
        if response is None:
            return False
        
        # Basic validation - can be extended based on specific method requirements
        if isinstance(response, dict):
            # Check for common error indicators
            if "error" in response:
                return False
            # Ensure response has expected structure
            return True
        
        return True
    
    async def _subscribe_with_retry(self):
        """Subscribe to events with retry logic for post-IBD."""
        try:
            await self._subscribe_to_events()
            self.state = ConnectionState.SUBSCRIBED
        except (ConnectionError, TimeoutError) as e:
            logger.warning("Initial subscription failed",
                          extra={"error": str(e), "state": "IBD"})
            # During IBD, subscriptions often fail - that's OK, we'll use oneshot calls
            self.state = ConnectionState.READY  # Still mark as ready even without subscriptions
            # Start retry task for subscriptions
            if not self.subscription_retry_task:
                self.subscription_retry_task = asyncio.create_task(self._retry_subscriptions())
        except Exception as e:
            logger.error("Unexpected subscription error",
                        extra={"error": str(e)}, exc_info=True)
            self.state = ConnectionState.READY
    
    async def _retry_subscriptions(self):
        """Retry subscriptions periodically until successful."""
        retry_delay = self.subscription_retry_delay
        
        while self.subscription_retry_count < self.max_subscription_retries:
            await asyncio.sleep(retry_delay)
            
            if self.state not in [ConnectionState.CONNECTED, ConnectionState.READY]:
                break
            
            try:
                logger.info("Retrying subscriptions",
                           extra={"attempt": self.subscription_retry_count + 1,
                                 "max_attempts": self.max_subscription_retries})
                await self._subscribe_to_events()
                self.state = ConnectionState.SUBSCRIBED
                logger.info("Successfully subscribed to events after retry",
                           extra={"attempts": self.subscription_retry_count + 1})
                self.subscription_retry_task = None
                self.subscription_retry_count = 0
                break
            except (ConnectionError, TimeoutError) as e:
                self.subscription_retry_count += 1
                logger.warning("Subscription retry failed",
                             extra={"attempt": self.subscription_retry_count,
                                   "error": str(e)})
                retry_delay = min(retry_delay * RETRY_BACKOFF_FACTOR, MAX_SUBSCRIPTION_RETRY_DELAY)
            except Exception as e:
                self.subscription_retry_count += 1
                logger.error("Unexpected subscription retry error",
                            extra={"attempt": self.subscription_retry_count,
                                  "error": str(e)}, exc_info=True)
                retry_delay = min(retry_delay * RETRY_BACKOFF_FACTOR, MAX_SUBSCRIPTION_RETRY_DELAY)
    
    async def _subscribe_to_events(self):
        """Subscribe to kaspad events for real-time updates."""
        if self.state not in [ConnectionState.CONNECTED, ConnectionState.READY]:
            raise ConnectionError(f"Cannot subscribe in state: {self.state.value}")
        
        try:
            # Subscribe to block added events
            await self.call("Subscribe", {
                "scope": {
                    "blockAdded": {}
                }
            })
            
            # Subscribe to virtual chain changed events
            await self.call("Subscribe", {
                "scope": {
                    "virtualChainChanged": {
                        "includeAcceptedTransactionIds": False
                    }
                }
            })
            
            # Subscribe to virtual DAA score changed
            await self.call("Subscribe", {
                "scope": {
                    "virtualDaaScoreChanged": {}
                }
            })
            
            self.state = ConnectionState.SUBSCRIBED
            logger.info("Successfully subscribed to kaspad events",
                       extra={"subscriptions": ["blockAdded", "virtualChainChanged", "virtualDaaScoreChanged"]})
            
        except Exception as e:
            logger.error("Failed to subscribe to events",
                        extra={"error": str(e)}, exc_info=True)
            raise  # Re-raise for retry logic
    
    async def _handle_notification(self, data: Dict[str, Any]):
        """Process incoming notifications from kaspad."""
        method = data.get("method", "")
        params = data.get("params", {})
        
        try:
            if method == "blockAddedNotification":
                # Update cached block info
                block = params.get("block", {})
                self.cached_data["latest_block"] = {
                    "hash": block.get("verboseData", {}).get("hash"),
                    "timestamp": datetime.now().isoformat(),
                    "blue_score": block.get("verboseData", {}).get("blueScore"),
                    "tx_count": len(block.get("transactions", []))
                }
                
                # Trigger data refresh
                await self._refresh_cached_data()
                logger.debug("New block received",
                            extra={"hash": self.cached_data['latest_block']['hash'][:16] + "..."})
                
            elif method == "virtualChainChangedNotification":
                # Chain reorganization - refresh everything
                await self._refresh_cached_data()
                logger.info("Virtual chain changed - refreshing data",
                           extra={"event": "chain_reorg"})
                
            elif method == "virtualDaaScoreChangedNotification":
                # Update DAA score
                daa_score = params.get("virtualDaaScore")
                if self.cached_data["blockdag_info"]:
                    self.cached_data["blockdag_info"]["virtualDaaScore"] = daa_score
                    
        except Exception as e:
            logger.error("Error handling notification",
                        extra={"method": method, "error": str(e)}, exc_info=True)
    
    def _get_cached_log_data(self) -> Dict[str, Any]:
        """Get log data with caching to reduce file I/O.
        
        Returns:
            Parsed log data from cache or fresh parse
        """
        current_time = time.time()
        
        # Check if cache is still valid
        if (self._log_cache is not None and 
            current_time - self._log_cache_timestamp < self._log_cache_ttl):
            logger.debug("Using cached log data",
                        extra={"cache_age": current_time - self._log_cache_timestamp})
            return self._log_cache
        
        # Parse logs and update cache
        try:
            logger.debug("Parsing logs (cache miss or expired)")
            log_data = self.log_parser.parse_logs()
            
            # Validate log data structure
            if not isinstance(log_data, dict):
                logger.warning("Invalid log data format, using defaults")
                log_data = {'peer_info': {'peers': [], 'peer_count': 0}, 'uptime': 'Unknown', 'uptime_seconds': 0}
            if 'peer_info' not in log_data:
                log_data['peer_info'] = {'peers': [], 'peer_count': 0}
            if not isinstance(log_data.get('peer_info'), dict):
                log_data['peer_info'] = {'peers': [], 'peer_count': 0}
            
            # Update cache
            self._log_cache = log_data
            self._log_cache_timestamp = current_time
            
            return log_data
        except Exception as e:
            logger.error(f"Error parsing logs: {e}")
            return {'peer_info': {'peers': [], 'peer_count': 0}, 'uptime': 'Unknown', 'uptime_seconds': 0}
    
    def _transform_rpc_peer(self, peer: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single RPC peer response to normalized format using PeerInfo model.
        
        Args:
            peer: Raw peer data from RPC response
            
        Returns:
            Normalized peer dictionary
        """
        # Use the unified model for transformation
        peer_info = PeerInfo.from_rpc_data(peer)
        # Return internal format for backward compatibility
        return peer_info.to_internal_format()
    
    async def _fetch_initial_data(self):
        """Fetch initial data to populate cache."""
        await self._refresh_cached_data()
    
    async def _fetch_network_daa_from_api(self) -> Optional[int]:
        """Fetch the actual network DAA score from Kaspa public API with caching."""
        current_time = time.time()
        
        # Check if cache is still valid
        if (self._network_daa_cache is not None and 
            current_time - self._network_daa_cache_timestamp < self._network_daa_cache_ttl):
            logger.debug(f"Using cached network DAA: {self._network_daa_cache} (cache age: {current_time - self._network_daa_cache_timestamp:.1f}s)")
            return self._network_daa_cache
        
        # Cache miss or expired, fetch from API
        try:
            async with aiohttp.ClientSession() as session:
                # Try to get the network info which includes virtualDaaScore
                async with session.get("https://api.kaspa.org/info/network", 
                                     timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        network_daa = int(data.get("virtualDaaScore", 0))
                        
                        # Update cache
                        self._network_daa_cache = network_daa
                        self._network_daa_cache_timestamp = current_time
                        
                        logger.info(f"Fetched fresh network DAA from public API: {network_daa} (will cache for {self._network_daa_cache_ttl}s)")
                        return network_daa
        except Exception as e:
            logger.warning(f"Failed to fetch network DAA from public API: {e}")
            # Return cached value if available, even if expired
            if self._network_daa_cache is not None:
                logger.info(f"Using expired cache due to API failure: {self._network_daa_cache}")
                return self._network_daa_cache
        return None
    
    async def _refresh_cached_data(self):
        """Refresh all cached data from kaspad."""
        try:
            logger.debug("Starting cache refresh",
                        extra={"state": self.state.value})
            
            # Always try oneshot calls first during IBD since persistent connections are unreliable
            # Check if we should use oneshot (not fully connected or no WebSocket)
            use_oneshot = (
                self.state not in [ConnectionState.CONNECTED, ConnectionState.READY, ConnectionState.SUBSCRIBED]
                or not self.ws
                or self.ws.closed
            )
            
            if use_oneshot:
                logger.info("Using oneshot calls for cache refresh",
                           extra={"reason": "no_persistent_connection"})
                results = await asyncio.gather(
                    self._oneshot_call("getInfo"),
                    self._oneshot_call("getBlockDagInfo"),
                    self._oneshot_call("getConnectedPeerInfo"),
                    self._oneshot_call("getMempoolEntries"),
                    self._oneshot_call("getConnections"),  # Get connection count during IBD
                    self._oneshot_call("getMetrics", {"connection_metrics": True, "process_metrics": True}),  # Get comprehensive metrics
                    self._oneshot_call("getServerInfo"),  # Get network DAA score for accurate sync progress
                    return_exceptions=True
                )
            else:
                # Use persistent connection when available
                logger.info("Using persistent connection for cache refresh",
                           extra={"state": self.state.value})
                results = await asyncio.gather(
                    self.call("getInfo"),
                    self.call("getBlockDagInfo"),
                    self.call("getConnectedPeerInfo"),
                    self.call("getMempoolEntries"),
                    self.call("getConnections"),  # Get connection count during IBD
                    self.call("getMetrics", {"connection_metrics": True, "process_metrics": True}),  # Get comprehensive metrics
                    self.call("getServerInfo"),  # Get network DAA score for accurate sync progress
                    return_exceptions=True
                )
            
            # Log results
            for i, name in enumerate(["node_info", "blockdag_info", "peer_info", "mempool", "connections", "metrics", "server_info"]):
                if i < len(results):
                    if isinstance(results[i], Exception):
                        logger.warning("Failed to fetch data",
                                     extra={"data_type": name, "error": str(results[i])})
                    elif results[i] is None:
                        logger.warning("Got None for data",
                                     extra={"data_type": name})
                    else:
                        logger.debug("Successfully fetched data",
                                   extra={"data_type": name})
            
            # Update cache with successful results
            if results[0] and not isinstance(results[0], Exception):
                self.cached_data["node_info"] = results[0]
                self.cached_data["is_synced"] = results[0].get("isSynced", False) if results[0] else False
            
            if results[1] and not isinstance(results[1], Exception):
                self.cached_data["blockdag_info"] = results[1]
            
            # Handle peer info - merge RPC data with log data if needed
            peer_info_from_rpc = results[2] if results[2] and not isinstance(results[2], Exception) else None
            connections_data = results[4] if len(results) > 4 and results[4] and not isinstance(results[4], Exception) else None
            metrics_data = results[5] if len(results) > 5 and results[5] and not isinstance(results[5], Exception) else None
            
            # Get log data with caching
            log_data = self._get_cached_log_data()
            
            # Process and normalize peer information from RPC
            if peer_info_from_rpc and peer_info_from_rpc.get("peerInfo"):
                # Transform RPC peer data to expected format
                transformed_peers = [
                    self._transform_rpc_peer(peer) 
                    for peer in peer_info_from_rpc.get("peerInfo", [])
                ]
                
                self.cached_data["peer_info"] = {
                    "infos": transformed_peers,
                    "peer_count": len(transformed_peers)
                }
            elif connections_data and connections_data.get("peers", 0) > 0:
                # During IBD, use connection count from getConnections and details from logs
                peer_list_from_logs = log_data['peer_info'].get('peers', [])
                self.cached_data["peer_info"] = {
                    "infos": peer_list_from_logs,
                    "peer_count": connections_data.get("peers", 0)
                }
            else:
                # Fallback to log data only
                self.cached_data["peer_info"] = {
                    "infos": log_data['peer_info'].get('peers', []),
                    "peer_count": log_data['peer_info'].get('peer_count', 0)
                }
            
            # Store connections and metrics data
            self.cached_data["connections"] = connections_data
            self.cached_data["metrics"] = metrics_data
            
            # Store server info (contains network DAA score for sync progress)
            server_info_data = results[6] if len(results) > 6 and results[6] and not isinstance(results[6], Exception) else None
            self.cached_data["server_info"] = server_info_data
            
            # Fetch actual network DAA from public API for accurate sync progress
            network_daa = await self._fetch_network_daa_from_api()
            self.cached_data["network_daa"] = network_daa
            
            # Store uptime from logs
            self.cached_data["uptime"] = {
                "uptime_formatted": log_data.get('uptime', 'Unknown'),
                "uptime_seconds": log_data.get('uptime_seconds', 0),
                "node_start_time": log_data.get('node_start_time')
            }
            
            if results[3] and not isinstance(results[3], Exception):
                self.cached_data["mempool"] = results[3]
            
            # Get sync status from log analysis
            sync_progress = self.log_sync_analyzer.get_sync_status()
            
            # Merge with node sync status if available
            if self.cached_data["node_info"]:
                node_is_synced = self.cached_data["node_info"].get("isSynced", False)
                # If logs say we're synced or node says we're synced, we're synced
                sync_progress["is_synced"] = sync_progress.get("is_synced", False) or node_is_synced
            
            self.cached_data["sync_status"] = sync_progress
            
            self.cached_data["last_update"] = datetime.now().isoformat()
            logger.info("Cache refresh complete",
                       extra={"has_node_info": self.cached_data['node_info'] is not None,
                             "has_blockdag": self.cached_data['blockdag_info'] is not None,
                             "is_synced": self.cached_data.get('is_synced', False)})
            
        except Exception as e:
            logger.error("Error refreshing cached data",
                        extra={"error": str(e)}, exc_info=True)
    
    async def _get_connection_from_pool(self):
        """Get a WebSocket connection from the pool or create a new one."""
        async with self.pool_lock:
            # Try to get an existing connection from pool
            while self.connection_pool:
                ws = self.connection_pool.pop(0)
                if not ws.closed:
                    logger.debug("Reusing connection from pool",
                               extra={"pool_size": len(self.connection_pool)})
                    return ws, False  # Return connection and flag that it's not new
                else:
                    logger.debug("Removed closed connection from pool")
            
            # No valid connections in pool, return None to create new one
            return None, True
    
    async def _return_connection_to_pool(self, ws):
        """Return a WebSocket connection to the pool for reuse."""
        async with self.pool_lock:
            if not ws.closed and len(self.connection_pool) < CONNECTION_POOL_SIZE:
                self.connection_pool.append(ws)
                logger.debug("Returned connection to pool",
                           extra={"pool_size": len(self.connection_pool)})
            else:
                # Pool is full or connection is closed, close it
                if not ws.closed:
                    await ws.close()
                logger.debug("Closed connection (pool full or connection invalid)")
    
    async def _health_check_loop(self):
        """Periodically check WebSocket health and recover if needed."""
        while self.state in [ConnectionState.CONNECTED, ConnectionState.READY, ConnectionState.SUBSCRIBED]:
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                
                # Check if we have a WebSocket and it's not closed
                if self.ws and not self.ws.closed:
                    # Try a simple ping to verify connection is alive
                    try:
                        # Send a lightweight request to check connection
                        test_result = await asyncio.wait_for(
                            self.call("getInfo"),
                            timeout=10.0
                        )
                        if test_result:
                            self.last_health_check = time.time()
                            logger.debug("Health check passed",
                                       extra={"state": self.state.value})
                        else:
                            logger.warning("Health check failed - no response")
                            # Trigger reconnection
                            if self.ws:
                                await self.ws.close()
                    except asyncio.TimeoutError:
                        logger.warning("Health check timeout - connection may be dead")
                        if self.ws:
                            await self.ws.close()
                else:
                    logger.warning("Health check found closed connection",
                                 extra={"ws_exists": self.ws is not None,
                                       "ws_closed": self.ws.closed if self.ws else None})
                    # Connection is dead, trigger reconnection
                    self.state = ConnectionState.DISCONNECTED
                    if not self.reconnect_task:
                        self.reconnect_task = asyncio.create_task(self._reconnect())
                        
            except Exception as e:
                logger.error("Health check error",
                            extra={"error": str(e)}, exc_info=True)
    
    async def _oneshot_call(self, method: str, params: Optional[Dict[str, Any]] = None, 
                           retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """Make a one-shot RPC call with retry logic and timeout recovery.
        
        Args:
            method: RPC method to call
            params: Method parameters
            retry_count: Current retry attempt (for internal use)
            
        Returns:
            RPC response or None if failed
        """
        if params is None:
            params = {}
        
        # Normalize method name
        normalized_method = method.replace("Request", "")
        
        # Use proper JSON-RPC 2.0 format
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": normalized_method,
            "params": params
        }
        
        logger.info("Attempting oneshot call",
                   extra={"method": normalized_method})
        
        ws = None
        created_new = False
        temp_session = None
        connection_start_time = time.time()
        
        # Track request start
        self._update_pool_metrics("request_started")
        
        try:
            # Try to get connection from pool first
            ws, created_new = await self._get_connection_from_pool()
            
            if ws and not created_new:
                self._update_pool_metrics("connection_reused")
            
            # Create new connection if needed
            if ws is None:
                # Create temporary session if needed
                if not self.session:
                    temp_session = aiohttp.ClientSession()
                    session = temp_session
                else:
                    session = self.session
                
                logger.debug("Creating new connection for oneshot call",
                           extra={"url": self.ws_url})
                ws = await session.ws_connect(
                    self.ws_url,
                    timeout=aiohttp.ClientTimeout(total=CONNECTION_POOL_TIMEOUT)
                )
                created_new = True
                self._update_pool_metrics("connection_created")
                
                # Track connection duration
                connection_duration = time.time() - connection_start_time
                self._update_pool_metrics("connection_duration", duration=connection_duration)
            # Send request
            logger.debug("Sending oneshot request",
                        extra={"method": normalized_method})
            await ws.send_str(json.dumps(payload))
            
            # Wait for response with configurable timeout
            response = await asyncio.wait_for(ws.receive(), timeout=ONESHOT_TIMEOUT)
            
            if response.type == aiohttp.WSMsgType.TEXT:
                result = json.loads(response.data)
                logger.info("Received oneshot response",
                           extra={"method": method})
                
                if "error" in result:
                    logger.warning("RPC Error in oneshot call",
                                 extra={"method": method, "error": result['error']})
                    # Don't return connection to pool if there was an error
                    if ws and not ws.closed:
                        await ws.close()
                    return None
                
                # Update readiness flag
                if self.state == ConnectionState.DISCONNECTED:
                    self.state = ConnectionState.READY
                    
                # Return connection to pool for reuse
                await self._return_connection_to_pool(ws)
                
                # Track successful request
                self._update_pool_metrics("request_success")
                    
                return result.get("params", result)
            elif response.type == aiohttp.WSMsgType.CLOSE:
                logger.warning("WebSocket closed in oneshot call",
                             extra={"method": method})
                return None
            else:
                logger.warning("Unexpected WebSocket message type",
                             extra={"type": str(response.type), "method": method})
                if ws and not ws.closed:
                    await ws.close()
                return None
            
        except asyncio.TimeoutError:
            if ws and not ws.closed:
                await ws.close()
            
            # Retry logic for timeout
            if retry_count < MAX_ONESHOT_RETRIES:
                logger.warning("Oneshot call timeout, retrying",
                             extra={"method": method, "retry": retry_count + 1})
                await asyncio.sleep(INITIAL_RETRY_DELAY * (retry_count + 1))
                return await self._oneshot_call(method, params, retry_count + 1)
            else:
                logger.error("Oneshot call timeout after retries",
                           extra={"method": method, "retries": retry_count})
                self._update_pool_metrics("request_failed")
                return None
                
        except aiohttp.ClientError as e:
            if ws and not ws.closed:
                await ws.close()
            
            # Retry logic for connection errors
            if retry_count < MAX_ONESHOT_RETRIES:
                logger.warning("Oneshot call connection error, retrying",
                             extra={"method": method, "error": str(e), "retry": retry_count + 1})
                await asyncio.sleep(INITIAL_RETRY_DELAY * (retry_count + 1))
                return await self._oneshot_call(method, params, retry_count + 1)
            else:
                logger.error("Oneshot call failed after retries",
                           extra={"method": method, "error": str(e), "retries": retry_count})
                self._update_pool_metrics("request_failed")
                self._update_pool_metrics("connection_failed")
                return None
                
        except Exception as e:
            logger.error("Oneshot call failed",
                        extra={"method": method, "error": str(e)}, exc_info=True)
            if ws and not ws.closed:
                await ws.close()
            self._update_pool_metrics("request_failed")
            return None
        finally:
            if temp_session:
                await temp_session.close()
    
    def _calculate_sync_percentage(self) -> float:
        """Calculate sync percentage based on headers and blocks."""
        if not self.cached_data["blockdag_info"]:
            return 0.0
            
        headers = self.cached_data["blockdag_info"].get("headerCount", 0)
        blocks = self.cached_data["blockdag_info"].get("blockCount", 0)
        
        if headers == 0:
            return 0.0
            
        # Simple percentage based on blocks vs headers
        percentage = (blocks / headers) * 100.0
        return min(percentage, 99.9)  # Cap at 99.9% until truly synced
    
    async def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make an RPC call through the persistent connection."""
        # Cleanup old requests periodically
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            asyncio.create_task(self._periodic_cleanup())
        
        # If not connected, try a one-shot connection (useful during IBD)
        if self.state not in [ConnectionState.CONNECTED, ConnectionState.READY, ConnectionState.SUBSCRIBED] or not self.ws:
            return await self._oneshot_call(method, params)
        
        if params is None:
            params = {}
        
        # Generate request ID
        self.request_id += 1
        request_id = self.request_id
        
        # Normalize method name
        normalized_method = method.replace("Request", "")
        
        # Create request with proper JSON-RPC 2.0 format
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": normalized_method,
            "params": params
        }
        
        # Create future for response with timestamp for cleanup
        future = asyncio.Future()
        async with self.request_lock:
            self.pending_requests[request_id] = (future, time.time())
        
        try:
            # Send request
            await self.ws.send_str(json.dumps(request))
            
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=self.request_timeout)
            return result
            
        except asyncio.TimeoutError:
            async with self.request_lock:
                self.pending_requests.pop(request_id, None)
            logger.warning("Request timed out",
                          extra={"method": method, "request_id": request_id})
            return None
        except Exception as e:
            async with self.request_lock:
                self.pending_requests.pop(request_id, None)
            logger.error("Request failed",
                        extra={"method": method, "error": str(e)}, exc_info=True)
            return None
    
    def get_cached_data(self) -> Dict[str, Any]:
        """Get all cached data."""
        return self.cached_data.copy()
    
    def get_pool_metrics(self) -> Dict[str, Any]:
        """Get connection pool metrics."""
        self.pool_metrics["last_updated"] = time.time()
        self.pool_metrics["idle_connections"] = len(self.connection_pool)
        self.pool_metrics["active_connections"] = self.pool_metrics["total_connections"] - self.pool_metrics["idle_connections"]
        
        # Calculate success rate
        total_reqs = self.pool_metrics["total_requests"]
        if total_reqs > 0:
            self.pool_metrics["success_rate"] = (self.pool_metrics["successful_requests"] / total_reqs) * 100
        else:
            self.pool_metrics["success_rate"] = 0
            
        return self.pool_metrics.copy()
    
    def _update_pool_metrics(self, event: str, **kwargs):
        """Update connection pool metrics based on events."""
        if event == "connection_created":
            self.pool_metrics["total_connections"] += 1
            self.pool_metrics["connection_creation_count"] += 1
        elif event == "connection_reused":
            self.pool_metrics["connection_reuse_count"] += 1
        elif event == "connection_failed":
            self.pool_metrics["failed_connections"] += 1
        elif event == "request_started":
            self.pool_metrics["total_requests"] += 1
        elif event == "request_success":
            self.pool_metrics["successful_requests"] += 1
        elif event == "request_failed":
            self.pool_metrics["failed_requests"] += 1
        elif event == "connection_duration":
            # Update average connection duration
            duration = kwargs.get("duration", 0)
            current_avg = self.pool_metrics["avg_connection_duration"]
            count = self.pool_metrics["connection_creation_count"]
            if count > 0:
                self.pool_metrics["avg_connection_duration"] = ((current_avg * (count - 1)) + duration) / count
    
    def get_node_info(self) -> Optional[Dict[str, Any]]:
        """Get cached node info."""
        return self.cached_data.get("node_info")
    
    def get_blockdag_info(self) -> Optional[Dict[str, Any]]:
        """Get cached blockdag info."""
        return self.cached_data.get("blockdag_info")
    
    def get_peer_info(self) -> Optional[Dict[str, Any]]:
        """Get cached peer info."""
        return self.cached_data.get("peer_info")
    
    def get_mempool(self) -> Optional[Dict[str, Any]]:
        """Get cached mempool info."""
        return self.cached_data.get("mempool")
    
    def get_sync_status(self) -> Optional[Dict[str, Any]]:
        """Get cached sync status."""
        return self.cached_data.get("sync_status")
    
    def is_synced(self) -> bool:
        """Check if node is synced."""
        return self.cached_data.get("is_synced", False)
    
    @property
    def connected(self) -> bool:
        """Backward compatibility property for connection state."""
        return self.state in [ConnectionState.CONNECTED, ConnectionState.READY, ConnectionState.SUBSCRIBED]
    
    @property
    def is_ready(self) -> bool:
        """Backward compatibility property for ready state."""
        return self.state in [ConnectionState.READY, ConnectionState.SUBSCRIBED]
    
    @property
    def subscribed(self) -> bool:
        """Check if subscribed to events."""
        return self.state == ConnectionState.SUBSCRIBED
    
    async def close(self):
        """Close the WebSocket connection and clean up resources."""
        self.state = ConnectionState.DISCONNECTED
        
        # Cancel health check task
        if self.health_check_task:
            self.health_check_task.cancel()
            self.health_check_task = None
        
        # Close all pooled connections
        async with self.pool_lock:
            for ws in self.connection_pool:
                if not ws.closed:
                    await ws.close()
            self.connection_pool.clear()
        
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("WebSocket connection and resources closed",
                   extra={"state": "closed"})