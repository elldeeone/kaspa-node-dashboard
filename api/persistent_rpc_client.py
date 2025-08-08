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
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}"
        
        # Connection state - using state machine
        self.ws = None
        self.session = None
        self.state = ConnectionState.DISCONNECTED
        self.reconnect_task = None
        
        # Circuit breaker for connection failures
        self.connection_failures = 0
        self.last_connection_attempt = 0
        self.max_failures = 10
        
        # Message handling with cleanup tracking
        self.request_id = 0
        self.pending_requests = {}  # {request_id: (future, timestamp)}
        self.request_timeout = 30.0  # 30 seconds timeout
        self.cleanup_interval = 60.0  # Cleanup old requests every minute
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
        self.subscription_retry_task = None
        
        # IBD progress tracking
        self.ibd_tracker = IBDProgressTracker(network="mainnet")
        
    async def connect(self):
        """Establish persistent WebSocket connection with circuit breaker."""
        # Circuit breaker check
        if self.connection_failures >= self.max_failures:
            time_since_last = time.time() - self.last_connection_attempt
            if time_since_last < 300:  # 5 minutes cooldown after max failures
                logger.warning(f"Circuit breaker active: {self.connection_failures} failures, waiting...")
                return False
            else:
                # Reset circuit breaker after cooldown
                self.connection_failures = 0
        
        self.last_connection_attempt = time.time()
        self.state = ConnectionState.CONNECTING
        
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            
            logger.info(f"Connecting to kaspad at {self.ws_url}")
            
            # Use longer timeout during IBD
            self.ws = await self.session.ws_connect(
                self.ws_url,
                timeout=aiohttp.ClientTimeout(total=60),
                heartbeat=30  # Add heartbeat for keep-alive
            )
            
            self.state = ConnectionState.CONNECTED
            logger.info("WebSocket connection established")
            
            # Reset failure count on successful connection
            self.connection_failures = 0
            
            # Start message handler with cleanup
            asyncio.create_task(self._message_handler())
            
            # Start periodic cleanup task
            asyncio.create_task(self._periodic_cleanup())
            
            # Try subscriptions with retry logic
            await self._subscribe_with_retry()
            
            # Initial data fetch
            await self._fetch_initial_data()
            
            self.state = ConnectionState.READY
            return True
            
        except Exception as e:
            logger.warning(f"Connection attempt failed: {e}")
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
                                future.set_exception(Exception(data["error"]))
                            else:
                                # Basic RPC response validation
                                result = data.get("params", data)
                                if self._validate_rpc_response(result):
                                    future.set_result(result)
                                else:
                                    future.set_exception(Exception("Invalid RPC response format"))
                    
                    # Handle notifications
                    elif "method" in data:
                        await self._handle_notification(data)
                        
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.ws.exception()}")
                    break
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed")
                    break
                    
        except Exception as e:
            logger.error(f"Message handler error: {e}")
        finally:
            self.state = ConnectionState.DISCONNECTED
            # Schedule reconnection if not already scheduled
            if not self.reconnect_task:
                self.reconnect_task = asyncio.create_task(self._reconnect())
    
    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff and circuit breaker."""
        self.state = ConnectionState.RECONNECTING
        delay = 5  # Start with 5 seconds
        max_delay = 60  # Max 60 seconds between attempts
        
        while self.state != ConnectionState.READY:
            # Check circuit breaker
            if self.connection_failures >= self.max_failures:
                logger.warning(f"Circuit breaker triggered after {self.connection_failures} failures")
                delay = 300  # 5 minutes when circuit breaker is active
            
            logger.info(f"Attempting reconnection in {delay} seconds...")
            await asyncio.sleep(delay)
            
            if await self.connect():
                logger.info("Reconnection successful")
                self.reconnect_task = None
                break
            
            # Exponential backoff
            delay = min(delay * 1.5, max_delay)
    
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
                        logger.debug(f"Cleaned up expired request {req_id}")
                    
                    if expired_requests:
                        logger.info(f"Cleaned up {len(expired_requests)} expired requests")
                    
                    self.last_cleanup = current_time
                
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(30)
    
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
        except Exception as e:
            logger.warning(f"Initial subscription failed: {e}")
            # Start retry task for subscriptions
            if not self.subscription_retry_task:
                self.subscription_retry_task = asyncio.create_task(self._retry_subscriptions())
    
    async def _retry_subscriptions(self):
        """Retry subscriptions periodically until successful."""
        retry_delay = 30  # Start with 30 seconds
        
        while self.subscription_retry_count < self.max_subscription_retries:
            await asyncio.sleep(retry_delay)
            
            if self.state not in [ConnectionState.CONNECTED, ConnectionState.READY]:
                break
            
            try:
                logger.info(f"Retrying subscriptions (attempt {self.subscription_retry_count + 1}/{self.max_subscription_retries})")
                await self._subscribe_to_events()
                self.state = ConnectionState.SUBSCRIBED
                logger.info("Successfully subscribed to events after retry")
                self.subscription_retry_task = None
                self.subscription_retry_count = 0
                break
            except Exception as e:
                self.subscription_retry_count += 1
                logger.warning(f"Subscription retry {self.subscription_retry_count} failed: {e}")
                retry_delay = min(retry_delay * 1.5, 300)  # Max 5 minutes
    
    async def _subscribe_to_events(self):
        """Subscribe to kaspad events for real-time updates."""
        if self.state not in [ConnectionState.CONNECTED, ConnectionState.READY]:
            raise Exception("Not connected")
        
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
            logger.info("Successfully subscribed to kaspad events")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to events: {e}")
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
                logger.debug(f"New block: {self.cached_data['latest_block']['hash']}")
                
            elif method == "virtualChainChangedNotification":
                # Chain reorganization - refresh everything
                await self._refresh_cached_data()
                logger.info("Virtual chain changed - refreshing data")
                
            elif method == "virtualDaaScoreChangedNotification":
                # Update DAA score
                daa_score = params.get("virtualDaaScore")
                if self.cached_data["blockdag_info"]:
                    self.cached_data["blockdag_info"]["virtualDaaScore"] = daa_score
                    
        except Exception as e:
            logger.error(f"Error handling notification {method}: {e}")
    
    async def _fetch_initial_data(self):
        """Fetch initial data to populate cache."""
        await self._refresh_cached_data()
    
    async def _refresh_cached_data(self):
        """Refresh all cached data from kaspad."""
        try:
            logger.debug(f"Starting cache refresh (state={self.state})")
            
            # During IBD or when not connected, use oneshot calls
            if self.state not in [ConnectionState.CONNECTED, ConnectionState.READY, ConnectionState.SUBSCRIBED]:
                logger.info("Using oneshot calls for cache refresh")
                results = await asyncio.gather(
                    self._oneshot_call("getInfo"),
                    self._oneshot_call("getBlockDagInfo"),
                    self._oneshot_call("getConnectedPeerInfo"),
                    self._oneshot_call("getMempoolEntries"),
                    return_exceptions=True
                )
            else:
                # Use persistent connection when available
                logger.info("Using persistent connection for cache refresh")
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
                    logger.warning(f"Failed to fetch {name}: {results[i]}")
                elif results[i] is None:
                    logger.warning(f"Got None for {name}")
                else:
                    logger.debug(f"Successfully fetched {name}")
            
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
            logger.info(f"Cache refresh complete: node_info={self.cached_data['node_info'] is not None}, blockdag={self.cached_data['blockdag_info'] is not None}")
            
        except Exception as e:
            logger.error(f"Error refreshing cached data: {e}")
    
    async def _oneshot_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make a one-shot RPC call when persistent connection is not available."""
        if params is None:
            params = {}
        
        # Normalize method name
        normalized_method = method.replace("Request", "")
        
        # Use proper JSON-RPC 2.0 format - THIS IS REQUIRED!
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": normalized_method,
            "params": params
        }
        
        logger.info(f"Attempting oneshot call: {normalized_method}")
        
        try:
            # Create temporary session if needed
            temp_session = None
            if not self.session:
                temp_session = aiohttp.ClientSession()
                session = temp_session
            else:
                session = self.session
            
            # Make one-shot connection
            logger.debug(f"Connecting to {self.ws_url}")
            async with session.ws_connect(
                self.ws_url,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as ws:
                # Send request with proper JSON-RPC 2.0 format
                logger.debug(f"Sending request: {payload}")
                await ws.send_str(json.dumps(payload))
                
                # Wait for response
                response = await asyncio.wait_for(ws.receive(), timeout=5.0)
                
                if response.type == aiohttp.WSMsgType.TEXT:
                    result = json.loads(response.data)
                    logger.info(f"Received response for {method}")
                    
                    if "error" in result:
                        logger.warning(f"RPC Error for {method}: {result['error']}")
                        return None
                    
                    # Update readiness flag
                    if self.state == ConnectionState.DISCONNECTED:
                        self.state = ConnectionState.READY
                    return result.get("params", result)
                elif response.type == aiohttp.WSMsgType.CLOSE:
                    logger.warning(f"WebSocket closed for {method}")
                    return None
                else:
                    logger.warning(f"Unexpected WebSocket message type: {response.type} for {method}")
                    return None
            
        except Exception as e:
            logger.error(f"One-shot call failed ({method}): {e}")
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
            logger.warning(f"Request {method} timed out")
            return None
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            logger.error(f"Request {method} failed: {e}")
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
        """Close the WebSocket connection."""
        self.state = ConnectionState.DISCONNECTED
        
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("WebSocket connection closed")