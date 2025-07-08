"""
API routes for the Kaspa Node Dashboard.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

def get_services():
    """Dependency to get initialized services."""
    from main import get_services
    return get_services()

def create_router() -> APIRouter:
    """Create and configure API router."""
    router = APIRouter()
    
    @router.get("/")
    async def root():
        """Root endpoint."""
        return {"message": "Kaspa Node Dashboard API", "status": "running", "version": "2.0.0"}
    
    @router.get("/info/health")
    async def health(services: Dict[str, Any] = Depends(get_services)):
        """Health check endpoint."""
        sync_service = services["sync_service"]
        current_progress = sync_service.get_current_progress()
        
        if current_progress.get("is_syncing", True):
            return {
                "status": "SYNCING",
                "service": "kaspad",
                "ready": False,
                "message": f"Kaspad is syncing ({current_progress.get('percentage', 0)}%)",
                "sync_progress": current_progress
            }
        else:
            return {"status": "UP", "service": "kaspad", "ready": True}
    
    @router.get("/info/sync")
    async def sync_status(services: Dict[str, Any] = Depends(get_services)):
        """Get detailed sync progress information."""
        sync_service = services["sync_service"]
        return sync_service.get_current_progress()
    
    @router.get("/info/kaspad")
    async def kaspad_info(services: Dict[str, Any] = Depends(get_services)):
        """Get kaspad node information."""
        kaspad_service = services["kaspad_service"]
        sync_service = services["sync_service"]
        
        node_info = await kaspad_service.get_node_info()
        current_progress = sync_service.get_current_progress()
        
        # Add sync progress to response
        node_info["syncProgress"] = current_progress
        
        return node_info
    
    @router.get("/info/blockdag")
    async def blockdag_info(services: Dict[str, Any] = Depends(get_services)):
        """Get blockchain/blockdag information."""
        kaspad_service = services["kaspad_service"]
        return await kaspad_service.get_blockdag_info()
    
    @router.get("/info/network")
    async def network_info(services: Dict[str, Any] = Depends(get_services)):
        """Get network information."""
        kaspad_service = services["kaspad_service"]
        network_stats = await kaspad_service.get_network_stats()
        
        return {
            "connectedPeers": network_stats.peer_count,
            "mempoolSize": 0,  # Will be populated from node info
            "networkName": "kaspa-mainnet",
            "status": network_stats.status
        }
    
    @router.get("/info/peers")
    async def peer_details(services: Dict[str, Any] = Depends(get_services)):
        """Get detailed peer information."""
        kaspad_service = services["kaspad_service"]
        network_stats = await kaspad_service.get_network_stats()
        
        # Convert PeerInfo objects to dictionaries
        peer_list = []
        for peer in network_stats.peers:
            peer_list.append({
                "ip": peer.ip,
                "port": peer.port,
                "ping": peer.ping,
                "connected_time": peer.connected_time,
                "is_ibd": peer.is_ibd,
                "is_outbound": peer.is_outbound,
                "version": peer.version
            })
        
        return {
            "peerCount": network_stats.peer_count,
            "peers": peer_list,
            "averagePing": network_stats.average_ping,
            "ibdPeers": network_stats.ibd_peers,
            "outboundPeers": network_stats.outbound_peers,
            "inboundPeers": network_stats.inbound_peers,
            "peerVersions": network_stats.peer_versions,
            "status": network_stats.status
        }
    
    return router