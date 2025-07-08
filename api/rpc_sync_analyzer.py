"""
RPC-based sync progress analyzer.
Analyzes kaspad RPC responses to determine detailed sync progress without requiring log access.
"""
import logging
from typing import Optional, Dict, Any
from models import LogParseResult
from config import SYNC_PHASE_PERCENTAGES

logger = logging.getLogger(__name__)

class RPCSyncAnalyzer:
    """Analyzes kaspad RPC responses to determine sync progress."""
    
    def __init__(self, rpc_client):
        self.rpc_client = rpc_client
    
    async def analyze_sync_progress(self) -> LogParseResult:
        """
        Analyze kaspad RPC responses to determine current sync progress.
        
        Returns:
            LogParseResult with current sync state based on RPC data
        """
        try:
            # Get RPC data
            info_result = await self.rpc_client.get_node_info()
            blockdag_result = await self.rpc_client.get_blockdag_info()
            peer_result = await self.rpc_client.get_connected_peer_info()
            
            if not info_result or not blockdag_result:
                return LogParseResult(
                    phase="Connecting",
                    percentage=0,
                    details="Waiting for node to respond...",
                    error="RPC not available"
                )
            
            return self._analyze_rpc_data(info_result, blockdag_result, peer_result)
            
        except Exception as e:
            logger.warning(f"Error analyzing RPC sync progress: {e}")
            return LogParseResult(
                phase="Error",
                percentage=0,
                details=f"RPC analysis failed: {str(e)}",
                error=str(e)
            )
    
    def _analyze_rpc_data(self, info_result: Dict[str, Any], 
                         blockdag_result: Dict[str, Any], 
                         peer_result: Optional[Dict[str, Any]]) -> LogParseResult:
        """Analyze RPC data to determine sync state."""
        
        is_synced = info_result.get("isSynced", False)
        block_count = blockdag_result.get("blockCount", 0)
        header_count = blockdag_result.get("headerCount", 0)
        
        # Get peer information
        peer_address = None
        if peer_result and peer_result.get("peerInfo"):
            peers = peer_result["peerInfo"]
            # Find IBD peer or first peer
            ibd_peers = [p for p in peers if p.get("is_ibd_peer", False)]
            if ibd_peers:
                addr = ibd_peers[0].get("address", {})
                peer_address = f"{addr.get('ip', 'unknown')}:{addr.get('port', 0)}"
            elif peers:
                addr = peers[0].get("address", {})
                peer_address = f"{addr.get('ip', 'unknown')}:{addr.get('port', 0)}"
        
        # Node is fully synced
        if is_synced and block_count > 0:
            return LogParseResult(
                phase="Sync Complete",
                percentage=100,
                details=f"Node fully synced with {block_count:,} blocks",
                blocks_processed=block_count,
                peer_address=peer_address,
                sub_phase="complete"
            )
        
        # Node is syncing
        if not is_synced:
            return self._determine_sync_phase(info_result, blockdag_result, peer_address)
        
        # Edge case: isSynced=true but no blocks (shouldn't happen)
        return LogParseResult(
            phase="Initializing",
            percentage=5,
            details="Node reports synced but no blocks found",
            blocks_processed=block_count,
            peer_address=peer_address,
            sub_phase="initializing"
        )
    
    def _determine_sync_phase(self, info_result: Dict[str, Any], 
                             blockdag_result: Dict[str, Any], 
                             peer_address: Optional[str]) -> LogParseResult:
        """Determine sync phase based on available metrics."""
        
        block_count = blockdag_result.get("blockCount", 0)
        header_count = blockdag_result.get("headerCount", 0)
        virtual_daa_score = blockdag_result.get("virtualDaaScore", 0)
        
        # If we have no blocks or headers, we're in early sync phases
        if block_count == 0 and header_count == 0:
            if peer_address:
                return LogParseResult(
                    phase="IBD Negotiation",
                    percentage=SYNC_PHASE_PERCENTAGES["negotiation_start"],
                    details=f"Negotiating initial sync with peer {peer_address}",
                    blocks_processed=0,
                    peer_address=peer_address,
                    sub_phase="negotiation"
                )
            else:
                return LogParseResult(
                    phase="Connecting",
                    percentage=2,
                    details="Establishing peer connections...",
                    blocks_processed=0,
                    sub_phase="peer_discovery"
                )
        
        # If we have headers but no blocks, we're in headers-first sync
        if header_count > 0 and block_count == 0:
            # Estimate progress based on header count vs expected network size
            # This is a rough estimate - you might need to adjust based on network conditions
            estimated_network_headers = 50000000  # Rough estimate
            header_progress = min(header_count / estimated_network_headers, 0.5) * 100
            
            return LogParseResult(
                phase="Headers Proof IBD",
                percentage=max(SYNC_PHASE_PERCENTAGES["headers_proof_start"], int(15 + header_progress * 0.5)),
                details=f"Processing headers: {header_count:,} received",
                blocks_processed=header_count,
                peer_address=peer_address,
                sub_phase="headers_processing"
            )
        
        # If we have blocks, we're in block download phase
        if block_count > 0:
            # Estimate progress based on blocks vs headers
            if header_count > 0:
                block_progress = (block_count / header_count) * 100
                adjusted_percentage = 70 + int(block_progress * 0.20)  # Map to 70-90% range
                
                return LogParseResult(
                    phase="Block Download",
                    percentage=min(adjusted_percentage, 90),
                    details=f"Downloading blocks: {block_count:,} / {header_count:,} ({block_progress:.1f}%)",
                    blocks_processed=block_count,
                    peer_address=peer_address,
                    sub_phase="block_download"
                )
            else:
                # We have blocks but no header info - later stage sync
                return LogParseResult(
                    phase="Block Processing",
                    percentage=85,
                    details=f"Processing {block_count:,} blocks",
                    blocks_processed=block_count,
                    peer_address=peer_address,
                    sub_phase="block_processing"
                )
        
        # Fallback case
        return LogParseResult(
            phase="Syncing",
            percentage=10,
            details="Synchronizing blockchain data...",
            blocks_processed=block_count,
            peer_address=peer_address,
            sub_phase="unknown"
        )