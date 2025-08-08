"""
API routes using persistent RPC client with cached data.
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Dict, Any
from rate_limiter import rate_limiter, expensive_rate_limiter
from peer_model import PeerInfo, PeerInfoCollection
from error_sanitizer import sanitizer
from config import IS_PRODUCTION

def get_persistent_client():
    """Dependency to get the persistent RPC client."""
    from main import persistent_client
    return persistent_client

def _extract_peer_version(peer: Dict[str, Any]) -> str:
    """Extract clean version string from peer data.
    
    Handles multiple formats:
    - User agent: "/kaspad:1.0.0/kaspad:1.0.0(kaspa-ng:1.0.1-2a36ea0)/"
    - Log version: "Protocol v7" or "v1.0.0"
    - Fallback to protocol version if nothing else available
    """
    user_agent = peer.get("userAgent", peer.get("version", ""))
    
    if not user_agent:
        # No version info, fallback to protocol version
        protocol_v = peer.get("advertisedProtocolVersion", peer.get("protocol_version", 0))
        return f"Protocol v{protocol_v}" if protocol_v else "Unknown"
    
    # If already in clean format (from logs)
    if user_agent.startswith("Protocol v") or user_agent.startswith("v"):
        return user_agent
    
    # Parse from user agent string format: "/kaspad:1.0.0/..."
    if user_agent.startswith("/"):
        try:
            # Split by "/" and find the kaspad version part
            parts = [p for p in user_agent.split("/") if p]
            for part in parts:
                if "kaspad:" in part:
                    # Extract version after "kaspad:"
                    version = part.split("kaspad:")[1].split("(")[0].strip()
                    return f"v{version}" if version else "Unknown"
        except (IndexError, AttributeError):
            pass
    
    # Return as-is if no special parsing needed
    return user_agent if user_agent else "Unknown"

def create_router() -> APIRouter:
    """Create and configure API router with persistent client."""
    router = APIRouter()
    
    @router.get("/")
    async def root(request: Request, _: None = Depends(rate_limiter)):
        """Root endpoint."""
        return {"message": "Kaspa Node Dashboard API", "status": "running", "version": "2.0.0", "mode": "persistent"}
    
    @router.get("/info/health")
    async def health(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
        """Health check endpoint using cached data."""
        try:
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
        except Exception as e:
            error_response = sanitizer.create_safe_error_response(
                e, 
                status_code=503,
                is_production=IS_PRODUCTION,
                context={"endpoint": "health"}
            )
            raise HTTPException(status_code=503, detail=error_response["message"])
    
    @router.get("/info/sync")
    async def sync_status(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
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
    async def kaspad_info(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
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
            "uptime": client.cached_data.get("uptime", {}),  # Include uptime from logs
            "cached": True,
            "last_update": client.cached_data.get("last_update"),
            "latest_block": client.cached_data.get("latest_block")
        }
    
    @router.get("/info/blockdag")
    async def blockdag_info(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
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
        
        # Handle both RPC peer info and log-based peer info
        peers = peer_info.get("infos", [])
        # If we have a peer_count from getConnections but empty peer list, show the count
        peer_count_override = peer_info.get("peer_count", len(peers))
        
        # Process peer list using unified model for cleaner code
        peer_collection = PeerInfoCollection()
        
        for peer_data in peers:
            # Convert to unified model
            peer_info = PeerInfo.from_mixed_format(peer_data)
            peer_collection.add_peer(peer_info)
        
        # For backward compatibility, also build the traditional response
        peer_list = []
        total_ping = 0
        ping_count = 0
        ibd_peers = 0
        outbound_peers = 0
        inbound_peers = 0
        
        for peer in peers:
            # Extract peer details - handle both RPC format and log parser format
            # RPC uses "isOutbound", log parser uses "is_outbound"
            is_outbound = peer.get("isOutbound", peer.get("is_outbound", False))
            is_ibd = peer.get("isIbdPeer", peer.get("is_ibd", False))
            
            # Handle ping - RPC provides it pre-converted to ms in "ping", or from logs
            ping_ms = peer.get("ping", 0)
            if "lastPingDuration" in peer and ping_ms == 0:
                # Fallback to converting from microseconds if ping not set
                ping_us = peer.get("lastPingDuration", 0)
                ping_ms = round(ping_us / 1000, 1) if ping_us else 0
            
            if is_outbound:
                outbound_peers += 1
            else:
                inbound_peers += 1
            
            if is_ibd:
                ibd_peers += 1
            
            if ping_ms > 0:
                total_ping += ping_ms
                ping_count += 1
            
            # Extract version with simplified logic
            version = _extract_peer_version(peer)
            
            # Handle connected time - might be different formats
            connected_time = peer.get("connectedTime", peer.get("connected_time", ""))
            
            peer_list.append({
                "id": peer.get("id", ""),
                "address": peer.get("address", ""),
                "ping": ping_ms,
                "connected_time": connected_time,
                "is_ibd": is_ibd,
                "is_outbound": is_outbound,
                "version": version,
                "protocol_version": peer.get("advertisedProtocolVersion", peer.get("protocol_version", 0))
            })
        
        average_ping = round(total_ping / ping_count, 1) if ping_count > 0 else 0
        
        return {
            "peerCount": max(peer_count_override, len(peers)),  # Use override count if higher
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
    
    # Optimized endpoint for frontend dashboard - returns all needed data in one call
    @router.get("/info/dashboard")
    async def dashboard_data(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
        """Get all dashboard data in a single optimized call."""
        try:
            if not client:
                return {"error": "Client not initialized", "connected": False}
            
            # Gather all data
            node_info = client.get_node_info()
            sync_status = client.get_sync_status()
            blockdag = client.get_blockdag_info()
            peer_info = client.get_peer_info()
            mempool = client.get_mempool()
            
            # Process peer data
            peers = []
            inbound_count = 0
            outbound_count = 0
            total_ping = 0
            valid_ping_count = 0
            
            if peer_info and "infos" in peer_info:
                for p in peer_info["infos"]:
                    is_outbound = p.get("isOutbound", False)
                    if is_outbound:
                        outbound_count += 1
                    else:
                        inbound_count += 1
                        
                    # Get ping value - it's already in milliseconds from PeerInfo model
                    # The field is 'ping' from to_internal_format() method
                    ping_ms = p.get("ping", 0)
                    
                    # Filter out invalid or placeholder ping values
                    if ping_ms and ping_ms > 0 and ping_ms < 10000:  # Less than 10 seconds is reasonable
                        total_ping += ping_ms
                        valid_ping_count += 1
                    else:
                        ping_ms = None  # Set to None if invalid
                    
                    # Extract peer info
                    peer_data = {
                        "id": p.get("id", ""),
                        "address": p.get("address", ""),
                        "version": _extract_peer_version(p),
                        "isOutbound": is_outbound,
                        "isIbdPeer": p.get("isIbdPeer", False),
                        "pingMs": round(ping_ms, 2) if ping_ms else None,
                        "lastPingTime": p.get("lastPingTime"),
                        "timeOffset": p.get("timeOffset", 0),
                        "userAgent": p.get("userAgent", ""),
                        "connected_time": p.get("connectedTime", p.get("connected_time", 0))
                    }
                    peers.append(peer_data)
            
            avg_ping = round(total_ping / valid_ping_count, 2) if valid_ping_count > 0 else None
            
            # Build comprehensive response
            return {
            "connection": {
                "connected": client.connected,
                "ready": client.state.value == "ready" or client.state.value == "subscribed",
                "state": client.state.value
            },
            "kaspad": {
                "version": node_info.get("serverVersion", "Unknown") if node_info else "Unknown",
                "protocolVersion": node_info.get("protocolVersion", 0) if node_info else 0,
                "network": node_info.get("networkId", "kaspa-mainnet") if node_info else "kaspa-mainnet",
                "isSynced": client.is_synced(),
                "isUtxoIndexed": node_info.get("hasUtxoIndex", False) if node_info else False,
                "p2pId": node_info.get("p2pId", "") if node_info else "",
                "uptime": client.cached_data.get("uptime", {})
            },
            "syncProgress": sync_status if sync_status else {
                "is_syncing": not client.is_synced(),
                "is_synced": client.is_synced(),
                "percentage": 0,
                "phase": "Unknown"
            },
            "blockdag": {
                "blockCount": blockdag.get("blockCount", 0) if blockdag else 0,
                "headerCount": blockdag.get("headerCount", 0) if blockdag else 0,
                "tipHashes": blockdag.get("tipHashes", []) if blockdag else [],
                "pruningPoint": blockdag.get("pruningPointHash", "") if blockdag else "",
                "difficulty": blockdag.get("difficulty", 0) if blockdag else 0,
                "pastMedianTime": blockdag.get("pastMedianTime", 0) if blockdag else 0,
                "virtualDaaScore": blockdag.get("virtualDaaScore", 0) if blockdag else 0,
                "blueScore": sync_status.get("headers", 0) if sync_status else 0
            },
            "peers": {
                "total": len(peers),
                "inbound": inbound_count,
                "outbound": outbound_count,
                "averagePing": avg_ping,
                "ibdPeerCount": sum(1 for p in peers if p.get("isIbdPeer")),
                "details": peers
            },
            "mempool": {
                "size": len(mempool.get("entries", [])) if mempool else 0,
                "entries": mempool.get("entries", [])[:10] if mempool else []  # Limit to 10 for performance
            },
            "cached": True,
            "lastUpdate": client.cached_data.get("last_update"),
            "latestBlock": client.cached_data.get("latest_block")
            }
        except Exception as e:
            # Return safe error for dashboard - don't raise exception to keep dashboard functional
            error_response = sanitizer.create_safe_error_response(
                e,
                status_code=500,
                is_production=IS_PRODUCTION,
                context={"endpoint": "dashboard"}
            )
            return {
                "error": True,
                "message": error_response["message"],
                "connection": {"connected": False, "ready": False, "state": "error"},
                "kaspad": {"version": "Unknown", "isSynced": False},
                "syncProgress": {"percentage": 0, "phase": "Error"},
                "blockdag": {},
                "peers": {"total": 0, "details": []},
                "mempool": {"size": 0, "entries": []}
            }
    
    # New endpoint to check connection status
    @router.get("/info/connection")
    async def connection_status(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
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
    
    # Endpoint to get connection pool metrics
    @router.get("/info/metrics")
    async def pool_metrics(request: Request, client = Depends(get_persistent_client), _: None = Depends(rate_limiter)):
        """Get connection pool and performance metrics."""
        if not client:
            return {"error": "Client not initialized"}
        
        return {
            "connection_pool": client.get_pool_metrics(),
            "connection_state": {
                "state": client.state.value,
                "connected": client.connected,
                "failures": client.connection_failures
            },
            "cache_info": {
                "last_update": client.cached_data.get("last_update"),
                "is_synced": client.is_synced()
            }
        }
    
    return router