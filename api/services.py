"""
Business logic services for the Kaspa Node Dashboard API.
"""
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from models import SyncProgress, ContainerUptime, NetworkStats, PeerInfo
from rpc_client import KaspadRPCClient
from sync_analyzer import SyncAnalyzer
from utils import run_docker_command, extract_peer_version, format_uptime, format_timestamp, format_hash
from config import (
    DEFAULT_KASPAD_INFO, DEFAULT_BLOCKDAG_INFO, DEFAULT_NETWORK_INFO, DEFAULT_PEER_INFO,
    PEER_DISPLAY_LIMIT
)

logger = logging.getLogger(__name__)

class KaspadService:
    """Service for interacting with kaspad node."""
    
    def __init__(self, rpc_client: KaspadRPCClient, container_name: str):
        self.rpc_client = rpc_client
        self.container_name = container_name
        self.sync_analyzer = SyncAnalyzer(container_name)
    
    async def get_node_info(self) -> Dict[str, Any]:
        """Get comprehensive node information."""
        try:
            info_result = await self.rpc_client.get_node_info()
            uptime_info = await self.get_container_uptime()
            
            if info_result is None:
                return {
                    **DEFAULT_KASPAD_INFO,
                    "uptime": uptime_info.to_dict() if uptime_info else None
                }
            
            return {
                "isSynced": info_result.get("isSynced", False),
                "version": info_result.get("serverVersion", "unknown"),
                "hasUtxoIndex": info_result.get("isUtxoIndexed", False),
                "mempoolSize": info_result.get("mempoolSize", 0),
                "networkName": info_result.get("network", "kaspa-mainnet"),
                "p2pId": info_result.get("p2pId", "unknown"),
                "status": "ready",
                "uptime": uptime_info.to_dict() if uptime_info else None
            }
            
        except Exception as e:
            logger.warning(f"Failed to get kaspad info: {e}")
            uptime_info = await self.get_container_uptime()
            return {
                **DEFAULT_KASPAD_INFO,
                "status": "error",
                "error": str(e),
                "uptime": uptime_info.to_dict() if uptime_info else None
            }
    
    async def get_blockdag_info(self) -> Dict[str, Any]:
        """Get blockchain/blockdag information."""
        try:
            result = await self.rpc_client.get_blockdag_info()
            
            if result is None:
                return DEFAULT_BLOCKDAG_INFO
            
            tip_hashes = result.get("tipHashes", [])
            past_median_time = result.get("pastMedianTime", 0)
            
            # Format tip hash for display
            tip_hash_display = "unknown"
            full_tip_hash = "unknown"
            if tip_hashes:
                full_tip_hash = tip_hashes[0]
                tip_hash_display = format_hash(full_tip_hash)
            
            # Format timestamp
            last_block_time = format_timestamp(past_median_time)
            
            return {
                "blockCount": result.get("blockCount", 0),
                "headerCount": result.get("headerCount", 0),
                "tipHashes": tip_hashes,
                "tipHashDisplay": tip_hash_display,
                "fullTipHash": full_tip_hash,
                "difficulty": result.get("difficulty", 0),
                "pastMedianTime": past_median_time,
                "lastBlockTime": last_block_time,
                "virtualParentHashes": result.get("virtualParentHashes", []),
                "prunedBlockCount": result.get("prunedBlockCount", 0),
                "virtualDaaScore": result.get("virtualDaaScore", 0),
                "blueScore": result.get("virtualDaaScore", 0),  # Alias for clarity
                "network": result.get("network", "mainnet"),
                "pruningPointHash": result.get("pruningPointHash", "unknown"),
                "sinkHash": result.get("sink", "unknown"),
                "status": "ready"
            }
            
        except Exception as e:
            logger.warning(f"Failed to get blockdag info: {e}")
            return {
                **DEFAULT_BLOCKDAG_INFO,
                "status": "error",
                "error": str(e)
            }
    
    async def get_network_stats(self) -> NetworkStats:
        """Get network statistics and peer information."""
        try:
            if not await self.rpc_client.check_readiness():
                return NetworkStats(**DEFAULT_NETWORK_INFO, peers=[])
            
            # Get peer information
            peers_result = await self.rpc_client.get_connected_peer_info()
            peer_info_list = peers_result.get("peerInfo", []) if peers_result else []
            
            # Get basic info for mempool size
            info_result = await self.rpc_client.get_node_info()
            mempool_size = info_result.get("mempoolSize", 0) if info_result else 0
            
            # Process peer data
            peers = []
            ping_times = []
            ibd_peers = 0
            outbound_peers = 0
            peer_versions = {}
            
            for peer_data in peer_info_list[:PEER_DISPLAY_LIMIT]:
                # Extract peer information
                address = peer_data.get("address", {})
                ping = peer_data.get("last_ping_duration", 0)
                connected_time_ms = peer_data.get("time_connected", 0)
                connected_time_sec = int(connected_time_ms / 1000) if connected_time_ms > 0 else 0
                is_ibd = peer_data.get("is_ibd_peer", False)
                is_outbound = peer_data.get("is_outbound", False)
                user_agent = peer_data.get("user_agent", "unknown")
                
                # Count statistics
                if ping > 0:
                    ping_times.append(ping)
                if is_ibd:
                    ibd_peers += 1
                if is_outbound:
                    outbound_peers += 1
                
                # Extract and count versions
                version = extract_peer_version(user_agent)
                peer_versions[version] = peer_versions.get(version, 0) + 1
                
                # Create peer info object
                peer = PeerInfo(
                    ip=address.get("ip", "unknown"),
                    port=address.get("port", 0),
                    ping=ping,
                    connected_time=connected_time_sec,
                    is_ibd=is_ibd,
                    is_outbound=is_outbound,
                    version=user_agent
                )
                peers.append(peer)
            
            # Calculate average ping
            average_ping = int(sum(ping_times) / len(ping_times)) if ping_times else 0
            
            return NetworkStats(
                peer_count=len(peer_info_list),
                peers=peers,
                average_ping=average_ping,
                ibd_peers=ibd_peers,
                outbound_peers=outbound_peers,
                inbound_peers=len(peer_info_list) - outbound_peers,
                peer_versions=peer_versions,
                status="ready"
            )
            
        except Exception as e:
            logger.warning(f"Failed to get network stats: {e}")
            return NetworkStats(
                **DEFAULT_PEER_INFO,
                peers=[],
                status="error"
            )
    
    async def get_container_uptime(self) -> Optional[ContainerUptime]:
        """Get container uptime information."""
        try:
            result = await run_docker_command(f"inspect {self.container_name}")
            if not result["success"]:
                return None
            
            import json
            container_data = json.loads(result["output"])
            
            if not container_data:
                return None
            
            started_at_str = container_data[0]["State"]["StartedAt"]
            # Handle nanoseconds in timestamp by truncating to microseconds
            if '.' in started_at_str and started_at_str.endswith('Z'):
                # Split on the decimal point and keep only 6 digits for microseconds
                date_part, time_part = started_at_str.split('.')
                microseconds = time_part.rstrip('Z')[:6].ljust(6, '0')
                started_at_str = f"{date_part}.{microseconds}Z"
            started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
            
            # Calculate uptime
            now = datetime.now(timezone.utc)
            uptime_delta = now - started_at
            uptime_seconds = int(uptime_delta.total_seconds())
            
            return ContainerUptime(
                uptime_seconds=uptime_seconds,
                uptime_formatted=format_uptime(uptime_seconds),
                started_at=started_at_str
            )
            
        except Exception as e:
            logger.warning(f"Error getting container uptime: {e}")
            return None

class SyncProgressService:
    """Service for monitoring sync progress."""
    
    def __init__(self, rpc_client: KaspadRPCClient, kaspad_service: KaspadService, 
                 container_name: str):
        self.rpc_client = rpc_client
        self.kaspad_service = kaspad_service
        self.sync_analyzer = SyncAnalyzer(container_name)
        self.current_progress = SyncProgress(
            is_syncing=True,
            percentage=0,
            headers_processed=0,
            blocks_processed=0,
            status="starting",
            message="Initializing...",
            phase="initialization"
        )
    
    async def update_sync_progress(self) -> None:
        """Update the current sync progress state."""
        try:
            # Get RPC data
            info_result = await self.rpc_client.get_node_info()
            blockdag_result = await self.rpc_client.get_blockdag_info()
            
            # Determine if actually synced
            is_synced = False
            if info_result and blockdag_result:
                block_count = blockdag_result.get("blockCount", 0)
                is_synced_flag = info_result.get("isSynced", False)
                is_synced = is_synced_flag and block_count > 0
            
            if is_synced:
                # Update to synced state
                header_count = blockdag_result.get("headerCount", 0)
                block_count = blockdag_result.get("blockCount", 0)
                
                self.current_progress = SyncProgress(
                    is_syncing=False,
                    percentage=100,
                    headers_processed=header_count,
                    blocks_processed=block_count,
                    status="ready",
                    message="Fully synced and ready",
                    phase="complete"
                )
            else:
                # Still syncing - get detailed progress from logs
                log_result = await self.sync_analyzer.analyze_sync_progress()
                
                self.current_progress = SyncProgress(
                    is_syncing=True,
                    percentage=log_result.percentage,
                    headers_processed=log_result.blocks_processed,
                    blocks_processed=blockdag_result.get("blockCount", 0) if blockdag_result else 0,
                    status="syncing",
                    message=log_result.details,
                    phase=log_result.phase,
                    sub_phase=log_result.sub_phase,
                    peer_address=log_result.peer_address,
                    last_block_timestamp=log_result.timestamp,
                    error=log_result.error
                )
                
        except Exception as e:
            logger.warning(f"Error updating sync progress: {e}")
    
    def get_current_progress(self) -> Dict[str, Any]:
        """Get current sync progress as dictionary."""
        return self.current_progress.to_dict()