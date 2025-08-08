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
from ibd_tracker import IBDProgressTracker

logger = logging.getLogger(__name__)

# Connection Configuration Constants
CONNECTION_TIMEOUT = 60  # Total connection timeout in seconds
SOCKET_READ_TIMEOUT = 30  # Socket read timeout in seconds
HEARTBEAT_INTERVAL = 30  # WebSocket heartbeat interval in seconds
REQUEST_TIMEOUT = 30.0  # Individual request timeout in seconds
CLEANUP_INTERVAL = 60.0  # Cleanup old requests every minute
HEALTH_CHECK_INTERVAL = 30  # Health check interval in seconds

# Retry Configuration Constants
INITIAL_RETRY_DELAY = 5  # Initial reconnection delay in seconds
MAX_RETRY_DELAY = 60  # Maximum reconnection delay in seconds
RETRY_BACKOFF_FACTOR = 1.5  # Exponential backoff multiplier
SUBSCRIPTION_RETRY_DELAY = 30  # Initial subscription retry delay
MAX_SUBSCRIPTION_RETRY_DELAY = 300  # Maximum subscription retry delay (5 minutes)

# Circuit Breaker Configuration
MAX_CONNECTION_FAILURES = 10  # Maximum failures before circuit breaker activates
CIRCUIT_BREAKER_COOLDOWN = 300  # Cooldown period in seconds (5 minutes)

# Connection Pool Configuration
CONNECTION_POOL_SIZE = 3  # Number of connections to maintain in pool
CONNECTION_POOL_TIMEOUT = 30  # Timeout for getting connection from pool

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
        
        # IBD progress tracking
        self.ibd_tracker = IBDProgressTracker(network="mainnet")
        
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
                msg = await self.ws.receive()
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Handle RPC responses
                    if "id" in data:
                        request_id = data["id"]
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
                    for req_id, (future, timestamp) in self.pending_requests.items():
                        if current_time - timestamp > self.request_timeout:
                            expired_requests.append(req_id)
                            if not future.done():
                                future.set_exception(asyncio.TimeoutError(f"Request {req_id} timed out"))
                    
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
    
    async def _fetch_initial_data(self):
        """Fetch initial data to populate cache."""
        await self._refresh_cached_data()
    
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
                    return_exceptions=True
                )
            
            # Log results
            for i, name in enumerate(["node_info", "blockdag_info", "peer_info", "mempool"]):
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
            
            if results[2] and not isinstance(results[2], Exception):
                self.cached_data["peer_info"] = results[2]
            
            if results[3] and not isinstance(results[3], Exception):
                self.cached_data["mempool"] = results[3]
            
            # Calculate sync status using IBD tracker
            if self.cached_data["node_info"] and self.cached_data["blockdag_info"]:
                # Use IBD tracker for accurate phase detection and progress
                sync_progress = self.ibd_tracker.get_sync_progress(
                    self.cached_data["node_info"],
                    self.cached_data["blockdag_info"]
                )
                
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
    
    async def _oneshot_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make a one-shot RPC call using connection pooling."""
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
        
        try:
            # Try to get connection from pool first
            ws, created_new = await self._get_connection_from_pool()
            
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
            # Send request
            logger.debug("Sending oneshot request",
                        extra={"method": normalized_method})
            await ws.send_str(json.dumps(payload))
            
            # Wait for response
            response = await asyncio.wait_for(ws.receive(), timeout=5.0)
            
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
            logger.error("Oneshot call timeout",
                        extra={"method": method})
            if ws and not ws.closed:
                await ws.close()
            return None
        except aiohttp.ClientError as e:
            logger.error("Oneshot call client error",
                        extra={"method": method, "error": str(e)})
            if ws and not ws.closed:
                await ws.close()
            return None
        except Exception as e:
            logger.error("Oneshot call failed",
                        extra={"method": method, "error": str(e)}, exc_info=True)
            if ws and not ws.closed:
                await ws.close()
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
        self.pending_requests[request_id] = (future, time.time())
        
        try:
            # Send request
            await self.ws.send_str(json.dumps(request))
            
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=self.request_timeout)
            return result
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            logger.warning("Request timed out",
                          extra={"method": method, "request_id": request_id})
            return None
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            logger.error("Request failed",
                        extra={"method": method, "error": str(e)}, exc_info=True)
            return None
    
    def get_cached_data(self) -> Dict[str, Any]:
        """Get all cached data."""
        return self.cached_data.copy()
    
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