"""
IBD Progress Tracker for Kaspa Node
Based on RPC patterns without Docker log dependency
"""
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class IBDProgressTracker:
    """
    Tracks IBD progress using RPC data patterns and time-based estimation.
    Maps to 4 frontend phases:
    1. IBD Negotiation (0-15%)
    2. Headers Proof IBD (15-65%) 
    3. Block Download (65-90%)
    4. Finalization (90-100%)
    """
    
    # Genesis timestamps for DAA score estimation (in milliseconds)
    GENESIS_TIMESTAMPS = {
        "mainnet": 1636298787611,  # November 7, 2021, 16:39:47 UTC
        "testnet": 1696096695269,  # September 30, 2023, 19:58:15 UTC (Testnet-11)
        "testnet11": 1696096695269,  # Alias
        "kaspa-mainnet": 1636298787611,  # Alias
    }
    
    # Crescendo hardfork timestamp (changes from 1 BPS to 10 BPS)
    CRESCENDO_TIMESTAMP = 1714924800000  # May 5, 2025, 15:00 UTC
    
    # Network checkpoints for better estimation (update monthly)
    NETWORK_CHECKPOINTS = {
        "mainnet": {
            '2024-11-01': 78000000,
            '2024-12-01': 80600000,
            '2025-01-01': 83200000,
        },
        "testnet11": {
            '2024-11-01': 35000000,
            '2024-12-01': 37600000,
        }
    }
    
    def __init__(self, network: str = "mainnet"):
        self.network = network.lower()
        self.phase2_start_time = None
        self.last_daa_score = None
        self.last_block_count = 0
        self.previous_phase = None
        self.phase_start_times = {}
        
    def detect_phase(self, node_info: Dict[str, Any], blockdag_info: Dict[str, Any]) -> str:
        """
        Detect current IBD phase based on RPC patterns.
        
        Returns one of: NEGOTIATION, HEADERS_PROOF, BLOCK_DOWNLOAD, FINALIZATION, COMPLETE
        """
        is_synced = node_info.get("isSynced", False)
        
        if is_synced:
            return "COMPLETE"
            
        header_count = blockdag_info.get("headerCount", 0)
        block_count = blockdag_info.get("blockCount", 0)
        virtual_daa_score = blockdag_info.get("virtualDaaScore", 0)
        
        # Phase 2 (Headers Proof) - distinctive signature: both counts are 0 during IBD
        # This is the most common phase during early/mid IBD
        if header_count == 0 and block_count == 0 and not is_synced:
            # If DAA score is > 0, we're likely in headers proof
            # (negotiation phase has very low DAA scores)
            if virtual_daa_score > 100000:  # Arbitrary threshold for "not just starting"
                logger.debug(f"Detected HEADERS_PROOF: DAA={virtual_daa_score}, headers={header_count}, blocks={block_count}")
                return "HEADERS_PROOF"
            
            # Check if virtualDaaScore is changing (indicates headers proof)
            if self.last_daa_score and virtual_daa_score != self.last_daa_score:
                logger.debug(f"Detected HEADERS_PROOF by DAA change: {self.last_daa_score} → {virtual_daa_score}")
                return "HEADERS_PROOF"
            
            # If we don't have enough info yet, check if we've been running for a bit
            if not self.phase2_start_time:
                self.phase2_start_time = time.time()
            
            # After 15 seconds with 0 counts, assume headers proof
            if (time.time() - self.phase2_start_time) > 15:
                logger.debug(f"Detected HEADERS_PROOF by time: {time.time() - self.phase2_start_time}s")
                return "HEADERS_PROOF"
            
            # Very early stage - still negotiating
            return "NEGOTIATION"
        
        # Phase 3 (Block Download) - blocks are being downloaded
        if block_count > 0 and not is_synced:
            # Check if we're near the end (>90% of estimated network height)
            estimated_network = self.estimate_network_daa_score()
            progress_ratio = virtual_daa_score / estimated_network if estimated_network > 0 else 0
            
            if progress_ratio > 0.9:
                logger.debug(f"Detected FINALIZATION: progress={progress_ratio:.2%}")
                return "FINALIZATION"
            
            logger.debug(f"Detected BLOCK_DOWNLOAD: blocks={block_count}, progress={progress_ratio:.2%}")
            return "BLOCK_DOWNLOAD"
        
        # Default to negotiation for very early stages
        logger.debug(f"Defaulting to NEGOTIATION: DAA={virtual_daa_score}, headers={header_count}, blocks={block_count}")
        return "NEGOTIATION"
    
    def estimate_network_daa_score(self) -> int:
        """
        Estimate current network DAA score using time since genesis.
        Accounts for Crescendo hardfork (1 BPS → 10 BPS on May 5, 2025).
        """
        genesis_time_ms = self.GENESIS_TIMESTAMPS.get(self.network, self.GENESIS_TIMESTAMPS["mainnet"])
        current_time_ms = int(time.time() * 1000)
        
        # Calculate based on block generation rate
        if current_time_ms < self.CRESCENDO_TIMESTAMP:
            # Pre-Crescendo: 1 block per second
            seconds_since_genesis = (current_time_ms - genesis_time_ms) / 1000
            estimated_score = int(seconds_since_genesis)
        else:
            # Post-Crescendo: 10 blocks per second
            # Calculate pre-Crescendo blocks
            pre_crescendo_seconds = (self.CRESCENDO_TIMESTAMP - genesis_time_ms) / 1000
            pre_crescendo_blocks = int(pre_crescendo_seconds)
            
            # Calculate post-Crescendo blocks (10 BPS = 100ms per block)
            post_crescendo_ms = current_time_ms - self.CRESCENDO_TIMESTAMP
            post_crescendo_blocks = int(post_crescendo_ms / 100)
            
            estimated_score = pre_crescendo_blocks + post_crescendo_blocks
        
        # Check if we have a recent checkpoint for better accuracy
        checkpoint_estimate = self._get_checkpoint_estimate()
        if checkpoint_estimate:
            # Use weighted average favoring checkpoint (more accurate)
            estimated_score = int(checkpoint_estimate * 0.7 + estimated_score * 0.3)
        
        return estimated_score
    
    def _get_checkpoint_estimate(self) -> Optional[int]:
        """Get estimate based on hardcoded checkpoints."""
        checkpoints = self.NETWORK_CHECKPOINTS.get(self.network, self.NETWORK_CHECKPOINTS.get("mainnet", {}))
        if not checkpoints:
            return None
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        dates = sorted(checkpoints.keys())
        
        # Find the most recent checkpoint
        for i in range(len(dates) - 1, -1, -1):
            if dates[i] <= current_date:
                checkpoint_date = datetime.strptime(dates[i], '%Y-%m-%d')
                checkpoint_value = checkpoints[dates[i]]
                days_since = (datetime.now() - checkpoint_date).days
                
                # Estimate blocks since checkpoint
                # Pre-Crescendo: ~86,400 blocks per day (1 BPS)
                # Post-Crescendo: ~864,000 blocks per day (10 BPS)
                if datetime.now().timestamp() * 1000 < self.CRESCENDO_TIMESTAMP:
                    blocks_per_day = 86400
                else:
                    blocks_per_day = 864000
                
                return checkpoint_value + (days_since * blocks_per_day)
        
        return None
    
    def calculate_progress(self, phase: str, node_info: Dict[str, Any], blockdag_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate sync progress based on phase and available data.
        
        Returns dict with phase name, percentage, and details.
        """
        virtual_daa_score = blockdag_info.get("virtualDaaScore", 0)
        block_count = blockdag_info.get("blockCount", 0)
        estimated_network = self.estimate_network_daa_score()
        
        # Track phase transitions
        if phase != self.previous_phase:
            logger.info(f"IBD Phase transition: {self.previous_phase} → {phase}")
            self.phase_start_times[phase] = time.time()
            if phase == "HEADERS_PROOF" and not self.phase2_start_time:
                self.phase2_start_time = time.time()
        
        self.previous_phase = phase
        self.last_daa_score = virtual_daa_score
        
        result = {
            "phase": self._map_phase_name(phase),
            "percentage": 0,
            "details": "",
            "message": "",
            "headers": blockdag_info.get("headerCount", 0),
            "blocks": block_count,
            "is_syncing": not node_info.get("isSynced", False),
            "is_synced": node_info.get("isSynced", False)
        }
        
        if phase == "COMPLETE":
            result["percentage"] = 100
            result["details"] = "Synchronization complete"
            result["message"] = "Node is fully synchronized"
            
        elif phase == "NEGOTIATION":
            # Phase 1: 0-15%
            # Use time-based estimation (typically takes 30-60 seconds)
            start_time = self.phase_start_times.get("NEGOTIATION", time.time())
            elapsed = time.time() - start_time
            progress = min((elapsed / 60) * 15, 15)  # Max 15%
            result["percentage"] = progress
            result["details"] = "Negotiating with peers"
            result["message"] = f"Finding sync peer and negotiating chain state"
            
        elif phase == "HEADERS_PROOF":
            # Phase 2: 15-65% (50% of total range)
            # Headers proof typically takes 5-15 minutes
            if not self.phase2_start_time:
                self.phase2_start_time = time.time()
            
            elapsed = time.time() - self.phase2_start_time
            # Estimate 10 minutes (600 seconds) for headers proof
            estimated_duration = 600
            phase_progress = min((elapsed / estimated_duration) * 100, 100)
            
            # Map to 15-65% range
            result["percentage"] = 15 + (phase_progress * 0.5)
            result["details"] = f"Downloading and validating headers proof"
            result["message"] = f"Processing headers proof ({int(phase_progress)}% of phase)"
            result["sub_phase"] = "headers_proof_download"
            
        elif phase == "BLOCK_DOWNLOAD":
            # Phase 3: 65-90%
            # Use actual DAA score progress
            if estimated_network > 0 and virtual_daa_score > 0:
                actual_progress = (virtual_daa_score / estimated_network) * 100
                # Map to 65-90% range
                result["percentage"] = 65 + (min(actual_progress, 100) * 0.25)
            else:
                result["percentage"] = 65
            
            result["details"] = f"Downloading blocks: {block_count:,} processed"
            result["message"] = f"Downloading and validating block bodies"
            result["blocks"] = block_count
            
        elif phase == "FINALIZATION":
            # Phase 4: 90-100%
            if estimated_network > 0 and virtual_daa_score > 0:
                actual_progress = (virtual_daa_score / estimated_network) * 100
                # Map to 90-100% range
                result["percentage"] = 90 + (min(actual_progress - 90, 10))
            else:
                result["percentage"] = 95
            
            result["details"] = f"Finalizing synchronization"
            result["message"] = f"Processing final blocks and UTXO set"
        
        # Ensure percentage doesn't exceed 100 unless truly synced
        if not node_info.get("isSynced", False):
            result["percentage"] = min(result["percentage"], 99.9)
        
        return result
    
    def _map_phase_name(self, internal_phase: str) -> str:
        """Map internal phase names to frontend display names."""
        mapping = {
            "NEGOTIATION": "IBD Negotiation",
            "HEADERS_PROOF": "Headers Proof IBD",
            "BLOCK_DOWNLOAD": "Block Download",
            "FINALIZATION": "Finalization",
            "COMPLETE": "Complete"
        }
        return mapping.get(internal_phase, internal_phase)
    
    def get_sync_progress(self, node_info: Dict[str, Any], blockdag_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point to get current sync progress.
        """
        phase = self.detect_phase(node_info, blockdag_info)
        return self.calculate_progress(phase, node_info, blockdag_info)