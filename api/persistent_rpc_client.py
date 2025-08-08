"""
Persistent WebSocket RPC client for Kaspa node with live event subscriptions.
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aiohttp
from datetime import datetime
from ibd_tracker import IBDProgressTracker

logger = logging.getLogger(__name__)

class PersistentKaspadRPCClient:
    """Persistent WebSocket connection to kaspad with event subscriptions."""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}"
        
        # Connection state
        self.ws = None
        self.session = None
        self.connected = False
        self.is_ready = False
        self.reconnect_task = None
        
        # Message handling
        self.request_id = 0
        self.pending_requests = {}
        
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
        
        # Subscription state
        self.subscribed = False
        
        # IBD progress tracking
        self.ibd_tracker = IBDProgressTracker(network="mainnet")
        
    async def connect(self):
        """Establish persistent WebSocket connection."""
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
            
            logger.info(f"Connecting to kaspad at {self.ws_url}")
            
            # Use longer timeout during IBD
            self.ws = await self.session.ws_connect(
                self.ws_url,
                timeout=aiohttp.ClientTimeout(total=60)
            )
            
            self.connected = True
            self.is_ready = True
            logger.info("WebSocket connection established")
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
            # During IBD, skip subscriptions as they may fail
            # We'll use oneshot calls instead
            try:
                await self._subscribe_to_events()
            except Exception as e:
                logger.warning(f"Subscription failed (normal during IBD): {e}")
            
            # Initial data fetch
            await self._fetch_initial_data()
            
            return True
            
        except Exception as e:
            logger.warning(f"Connection attempt failed (normal during IBD): {e}")
            self.connected = False
            self.is_ready = False
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
                            future = self.pending_requests.pop(request_id)
                            if "error" in data:
                                future.set_exception(Exception(data["error"]))
                            else:
                                future.set_result(data.get("params", data))
                    
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
            self.connected = False
            self.is_ready = False
            # Schedule reconnection
            if not self.reconnect_task:
                self.reconnect_task = asyncio.create_task(self._reconnect())
    
    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff."""
        delay = 5  # Start with 5 seconds during IBD
        max_delay = 60  # Max 60 seconds between attempts
        
        while not self.connected:
            logger.info(f"Attempting reconnection in {delay} seconds...")
            await asyncio.sleep(delay)
            
            if await self.connect():
                logger.info("Reconnection successful")
                self.reconnect_task = None
                break
            
            # Exponential backoff for IBD conditions
            delay = min(delay * 1.5, max_delay)
    
    async def _subscribe_to_events(self):
        """Subscribe to kaspad events for real-time updates."""
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
            
            self.subscribed = True
            logger.info("Subscribed to kaspad events")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to events: {e}")
            self.subscribed = False
    
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
            logger.debug(f"Starting cache refresh (connected={self.connected})")
            
            # During IBD or when not connected, use oneshot calls
            if not self.connected:
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
                    self.is_ready = True
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
        # If not connected, try a one-shot connection (useful during IBD)
        if not self.connected or not self.ws:
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
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # Send request
            await self.ws.send_str(json.dumps(request))
            
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=10.0)
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
    
    async def close(self):
        """Close the WebSocket connection."""
        self.connected = False
        
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("WebSocket connection closed")