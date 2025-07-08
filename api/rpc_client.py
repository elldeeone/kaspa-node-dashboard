"""
Kaspad RPC client with WebSocket JSON-RPC communication.
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aiohttp
from utils import RateLimiter

logger = logging.getLogger(__name__)

class KaspadRPCClient:
    """Asynchronous RPC client for kaspad WebSocket JSON-RPC interface."""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}"
        self.is_ready = False
        self._connection_lock = asyncio.Lock()
        self._session = None
        self._rate_limiter = RateLimiter(max_calls=10, time_window=1)  # 10 calls per second
        
    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()
    
    async def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Make a JSON-RPC call to kaspad.
        
        Args:
            method: RPC method name (can include 'Request' suffix)
            params: Method parameters
            
        Returns:
            RPC response data or None if failed
        """
        if not self._rate_limiter.is_allowed():
            logger.warning("RPC call rate limited")
            return None
        
        if params is None:
            params = {}
        
        # Normalize method name (remove Request suffix if present)
        normalized_method = method.replace("Request", "")
        
        payload = {
            "id": 1,
            "method": normalized_method,
            "params": params
        }
        
        try:
            async with self._connection_lock:
                session = self._session or aiohttp.ClientSession()
                
                try:
                    async with session.ws_connect(
                        self.ws_url,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as ws:
                        # Send request
                        await ws.send_str(json.dumps(payload))
                        
                        # Wait for response
                        response = await asyncio.wait_for(ws.receive(), timeout=5.0)
                        
                        if response.type == aiohttp.WSMsgType.TEXT:
                            result = json.loads(response.data)
                            
                            if "error" in result:
                                logger.warning(f"RPC Error for {method}: {result['error']}")
                                self.is_ready = False
                                return None
                            
                            self.is_ready = True
                            # Kaspa wRPC responses contain data in 'params' field
                            return result.get("params", result)
                        else:
                            logger.warning(f"Unexpected WebSocket message type: {response.type}")
                            self.is_ready = False
                            return None
                            
                except aiohttp.WSServerHandshakeError as e:
                    logger.debug(f"WebSocket handshake failed: {e}")
                    self.is_ready = False
                    return None
                finally:
                    if not self._session:  # Close session if we created it locally
                        await session.close()
                        
        except (asyncio.TimeoutError, aiohttp.ClientConnectorError, 
                aiohttp.ServerDisconnectedError) as e:
            logger.debug(f"Kaspad not ready ({method}): {e}")
            self.is_ready = False
            return None
        except Exception as e:
            logger.warning(f"RPC call failed ({method}): {e}")
            self.is_ready = False
            return None
    
    async def check_readiness(self) -> bool:
        """
        Check if kaspad is ready to accept RPC calls.
        
        Returns:
            True if kaspad is responding to RPC calls
        """
        result = await self.call("getInfo")
        return result is not None
    
    async def get_node_info(self) -> Optional[Dict[str, Any]]:
        """Get basic node information."""
        return await self.call("getInfo")
    
    async def get_blockdag_info(self) -> Optional[Dict[str, Any]]:
        """Get blockchain/blockdag information."""
        return await self.call("getBlockDagInfo")
    
    async def get_connected_peer_info(self) -> Optional[Dict[str, Any]]:
        """Get information about connected peers."""
        return await self.call("getConnectedPeerInfo")
    
    async def get_mempool_entries(self) -> Optional[Dict[str, Any]]:
        """Get mempool entries."""
        return await self.call("getMempoolEntries")
    
    async def ping(self) -> bool:
        """Simple ping to check if service is responding."""
        try:
            result = await self.call("ping")
            return result is not None
        except Exception:
            return False