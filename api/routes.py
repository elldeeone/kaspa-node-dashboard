"""
API routes using persistent RPC client with cached data.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any
from rate_limiter import rate_limiter, expensive_rate_limiter

def get_persistent_client():
    """Dependency to get the persistent RPC client."""
    from main import persistent_client
    return persistent_client

def create_router() -> APIRouter:
    """Create and configure API router with persistent client."""
    router = APIRouter()
    
    @router.get("/")
    async def root():
        """Root endpoint."""
        return {"message": "Kaspa Node Dashboard API", "status": "running", "version": "2.0.0", "mode": "persistent"}
    
    @router.get("/info/health")
    async def health(client = Depends(get_persistent_client)):
        """Health check endpoint using cached data."""
        if not client:
            return {"status": "DOWN", "service": "kaspad", "ready": False, "message": "Client not initialized"}
        
        sync_status = client.get_sync_status()
        is_synced = client.is_synced()
        
        if not is_synced:
            percentage = sync_status.get("percentage", 0) if sync_status else 0
            return {
                "status": "SYNCING",
                "service": "kaspad",
                "ready": False,
                "message": f"Kaspad is syncing ({percentage:.2f}%)",
                "sync_progress": sync_status
            }
        else:
            return {"status": "UP", "service": "kaspad", "ready": True, "cached": True}
    
    @router.get("/info/sync")
    async def sync_status(client = Depends(get_persistent_client)):
        """Get detailed sync progress information from cache."""
        if not client:
            return {"error": "Client not initialized"}
        
        sync_status = client.get_sync_status()
        
        if not sync_status:
            # Fallback if no sync status available
            return {
                "is_syncing": not client.is_synced(),
                "is_synced": client.is_synced(),
                "percentage": 0,
                "headers": 0,
                "blocks": 0,
                "phase": "Unknown",
                "cached": True,
                "last_update": client.cached_data.get("last_update")
            }
        
        # Return the enhanced sync status from IBD tracker
        return {
            **sync_status,
            "cached": True,
            "last_update": client.cached_data.get("last_update"),
            "latest_block": client.cached_data.get("latest_block")
        }
    
    @router.get("/info/kaspad")
    async def kaspad_info(client = Depends(get_persistent_client)):
        """Get kaspad node information from cache."""
        if not client:
            return {"error": "Client not initialized"}
        
        node_info = client.get_node_info()
        sync_status = client.get_sync_status()
        
        if not node_info:
            return {"error": "Node info not available"}
        
        # Build response with cached data - match frontend expectations
        return {
            "version": node_info.get("serverVersion", "Unknown"),  # Frontend expects 'version'
            "serverVersion": node_info.get("serverVersion", "Unknown"),
            "protocolVersion": node_info.get("protocolVersion", 0),
            "network": node_info.get("networkId", "kaspa-mainnet"),
            "isSynced": client.is_synced(),
            "isUtxoIndexed": node_info.get("hasUtxoIndex", False),
            "p2pId": node_info.get("p2pId", ""),
            "mempoolSize": len(client.get_mempool().get("entries", [])) if client.get_mempool() else 0,
            "syncProgress": sync_status,  # This now includes phase, percentage, details from IBD tracker
            "cached": True,
            "last_update": client.cached_data.get("last_update"),
            "latest_block": client.cached_data.get("latest_block")
        }
    
    @router.get("/info/blockdag")
    async def blockdag_info(client = Depends(get_persistent_client)):
        """Get blockchain/blockdag information from cache."""
        if not client:
            return {"error": "Client not initialized"}
        
        blockdag = client.get_blockdag_info()
        
        if not blockdag:
            return {"error": "Blockdag info not available"}
        
        return {
            "network": blockdag.get("network", "kaspa-mainnet"),
            "blockCount": blockdag.get("blockCount", 0),
            "headerCount": blockdag.get("headerCount", 0),
            "tipHashes": blockdag.get("tipHashes", []),
            "difficulty": blockdag.get("difficulty", 0),
            "pastMedianTime": blockdag.get("pastMedianTime", 0),
            "virtualDaaScore": blockdag.get("virtualDaaScore", 0),
            "cached": True,
            "last_update": client.cached_data.get("last_update")
        }
    
    @router.get("/info/network")
    async def network_info(client = Depends(get_persistent_client)):
        """Get network information from cache."""
        if not client:
            return {"error": "Client not initialized"}
        
        peer_info = client.get_peer_info()
        mempool = client.get_mempool()
        node_info = client.get_node_info()
        
        peer_count = len(peer_info.get("infos", [])) if peer_info else 0
        mempool_size = len(mempool.get("entries", [])) if mempool else 0
        
        return {
            "connectedPeers": peer_count,
            "mempoolSize": mempool_size,
            "networkName": node_info.get("networkId", "kaspa-mainnet") if node_info else "kaspa-mainnet",
            "status": "connected" if client.connected else "disconnected",
            "cached": True,
            "last_update": client.cached_data.get("last_update")
        }
    
    @router.get("/info/peers")
    async def peer_details(client = Depends(get_persistent_client)):
        """Get detailed peer information from cache."""
        if not client:
            return {"error": "Client not initialized"}
        
        peer_info = client.get_peer_info()
        
        if not peer_info:
            return {"error": "Peer info not available"}
        
        peers = peer_info.get("infos", [])
        
        # Process peer list
        peer_list = []
        total_ping = 0
        ping_count = 0
        ibd_peers = 0
        outbound_peers = 0
        inbound_peers = 0
        
        for peer in peers:
            # Extract peer details
            is_outbound = peer.get("isOutbound", False)
            is_ibd = peer.get("isIbdPeer", False)
            ping_ms = peer.get("lastPingDuration", 0) // 1000000  # Convert nanoseconds to milliseconds
            
            if is_outbound:
                outbound_peers += 1
            else:
                inbound_peers += 1
            
            if is_ibd:
                ibd_peers += 1
            
            if ping_ms > 0:
                total_ping += ping_ms
                ping_count += 1
            
            peer_list.append({
                "id": peer.get("id", ""),
                "address": peer.get("address", ""),
                "ping": ping_ms,
                "connected_time": peer.get("connectedTime", ""),
                "is_ibd": is_ibd,
                "is_outbound": is_outbound,
                "version": peer.get("userAgent", ""),
                "protocol_version": peer.get("advertisedProtocolVersion", 0)
            })
        
        average_ping = total_ping / ping_count if ping_count > 0 else 0
        
        return {
            "peerCount": len(peers),
            "peers": peer_list,
            "averagePing": average_ping,
            "ibdPeers": ibd_peers,
            "outboundPeers": outbound_peers,
            "inboundPeers": inbound_peers,
            "status": "connected" if client.connected else "disconnected",
            "cached": True,
            "last_update": client.cached_data.get("last_update"),
            "latest_block": client.cached_data.get("latest_block")
        }
    
    # New endpoint to get all cached data at once
    @router.get("/info/all", dependencies=[Depends(expensive_rate_limiter)])
    async def all_info(client = Depends(get_persistent_client)):
        """Get all cached data in a single call. Rate limited due to response size."""
        if not client:
            return {"error": "Client not initialized"}
        
        return client.get_cached_data()
    
    # New endpoint to check connection status
    @router.get("/info/connection")
    async def connection_status(client = Depends(get_persistent_client)):
        """Get connection status and details."""
        if not client:
            return {"connected": False, "error": "Client not initialized"}
        
        return {
            "connected": client.connected,
            "ready": client.is_ready,
            "subscribed": client.subscribed,
            "host": client.host,
            "port": client.port,
            "last_update": client.cached_data.get("last_update")
        }
    
    return router