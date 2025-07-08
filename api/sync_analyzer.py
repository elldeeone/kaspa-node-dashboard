"""
Kaspad sync progress analyzer.
Analyzes kaspad container logs to determine detailed sync progress.
"""
import logging
from typing import Optional
from models import LogParseResult
from utils import REGEX_PATTERNS, run_docker_command
from config import SYNC_PHASE_PERCENTAGES, DOCKER_LOG_TAIL_LINES

logger = logging.getLogger(__name__)

class SyncAnalyzer:
    """Analyzes kaspad logs to determine sync progress."""
    
    def __init__(self, container_name: str):
        self.container_name = container_name
    
    async def analyze_sync_progress(self) -> LogParseResult:
        """
        Analyze kaspad logs to determine current sync progress.
        
        Returns:
            LogParseResult with current sync state
        """
        try:
            # Get container logs
            result = await run_docker_command(
                f"logs --tail={DOCKER_LOG_TAIL_LINES} {self.container_name}"
            )
            
            if not result["success"]:
                return LogParseResult(
                    phase="Unknown",
                    percentage=0,
                    details="Cannot read container logs",
                    error="Log access failed"
                )
            
            return self._parse_logs(result["output"])
            
        except Exception as e:
            logger.warning(f"Error analyzing sync progress: {e}")
            return LogParseResult(
                phase="Error",
                percentage=0,
                details=f"Analysis failed: {str(e)}",
                error=str(e)
            )
    
    def _parse_logs(self, logs: str) -> LogParseResult:
        """Parse log content to extract sync progress."""
        log_lines = [line.strip() for line in logs.split('\n') if line.strip()]
        
        # Initialize result with defaults
        result = LogParseResult(
            phase="Initializing",
            percentage=0,
            details="Starting up..."
        )
        
        # State tracking variables
        current_peer = None
        trusted_blocks_total = None
        trusted_blocks_current = 0
        
        # Parse logs in reverse order to get most recent state first
        for line in reversed(log_lines):
            # Check for completion states first
            completion_result = self._check_completion_states(line)
            if completion_result:
                return completion_result
        
        # Parse logs in forward order for progressive state tracking
        for line in log_lines:
            # Update state tracking variables and result
            self._process_log_line(line, result, current_peer, 
                                 trusted_blocks_total, trusted_blocks_current)
        
        # Handle fallback cases
        if result.phase == "Initializing":
            result = self._check_basic_sync_indicators(log_lines, result)
        
        return result
    
    def _check_completion_states(self, line: str) -> Optional[LogParseResult]:
        """Check for IBD completion states."""
        # IBD Success
        match = REGEX_PATTERNS['ibd_complete_success'].search(line)
        if match:
            peer = match.group(1)
            return LogParseResult(
                phase="IBD Complete",
                percentage=100,
                details=f"IBD completed successfully with peer {peer}",
                peer_address=peer,
                sub_phase="success"
            )
        
        # IBD Error
        match = REGEX_PATTERNS['ibd_complete_error'].search(line)
        if match:
            peer, error = match.group(1), match.group(2)
            return LogParseResult(
                phase="IBD Error",
                percentage=0,
                details=f"IBD failed with peer {peer}: {error}",
                peer_address=peer,
                sub_phase="error",
                error=error
            )
        
        # Post-processing (Unorphaning)
        match = REGEX_PATTERNS['ibd_unorphaned'].search(line)
        if match:
            block_count = int(match.group(1))
            return LogParseResult(
                phase="IBD Post-Processing",
                percentage=SYNC_PHASE_PERCENTAGES["post_processing"],
                details=f"Unorphaned {block_count} blocks, finalizing sync...",
                blocks_processed=block_count,
                sub_phase="unorphaning"
            )
        
        return None
    
    def _process_log_line(self, line: str, result: LogParseResult, 
                         current_peer: str, trusted_blocks_total: int, 
                         trusted_blocks_current: int) -> None:
        """Process a single log line and update result."""
        
        # Phase 1: IBD Negotiation
        if self._process_negotiation_phase(line, result):
            return
        
        # Phase 2: Headers Proof IBD
        if self._process_headers_proof_phase(line, result, trusted_blocks_total, trusted_blocks_current):
            return
        
        # Phase 3: Block Download
        if self._process_block_download_phase(line, result):
            return
        
        # Special cases
        self._process_special_cases(line, result)
    
    def _process_negotiation_phase(self, line: str, result: LogParseResult) -> bool:
        """Process IBD negotiation phase logs."""
        # IBD Started
        match = REGEX_PATTERNS['ibd_started'].search(line)
        if match:
            peer = match.group(1)
            result.phase = "IBD Negotiation"
            result.percentage = SYNC_PHASE_PERCENTAGES["negotiation_start"]
            result.details = f"IBD started with peer {peer}"
            result.peer_address = peer
            result.sub_phase = "started"
            return True
        
        # Chain Negotiation
        match = REGEX_PATTERNS['chain_negotiation'].search(line)
        if match:
            peer, hash_count = match.group(1), int(match.group(2))
            result.phase = "IBD Negotiation"
            result.percentage = SYNC_PHASE_PERCENTAGES["negotiation_chain"]
            result.details = f"Negotiating chain with peer {peer}, received {hash_count} hashes"
            result.peer_address = peer
            result.sub_phase = "chain_negotiation"
            return True
        
        # Negotiation Zoom-in
        match = REGEX_PATTERNS['negotiation_zoom'].search(line)
        if match:
            peer = match.group(1)
            result.phase = "IBD Negotiation"
            result.percentage = SYNC_PHASE_PERCENTAGES["negotiation_zoom"]
            result.details = f"Zooming in on common ancestor with peer {peer}"
            result.peer_address = peer
            result.sub_phase = "zoom_in"
            return True
        
        return False
    
    def _process_headers_proof_phase(self, line: str, result: LogParseResult,
                                   trusted_blocks_total: int, trusted_blocks_current: int) -> bool:
        """Process Headers Proof IBD phase logs."""
        # Headers Proof Start
        match = REGEX_PATTERNS['headers_proof_start'].search(line)
        if match:
            peer = match.group(1)
            result.phase = "Headers Proof IBD"
            result.percentage = SYNC_PHASE_PERCENTAGES["headers_proof_start"]
            result.details = f"Starting headers proof sync with peer {peer}"
            result.peer_address = peer
            result.sub_phase = "headers_proof_start"
            return True
        
        # Headers Proof Received
        match = REGEX_PATTERNS['headers_proof_received'].search(line)
        if match:
            total_headers, unique_headers = int(match.group(1)), int(match.group(2))
            result.phase = "Headers Proof IBD"
            result.percentage = SYNC_PHASE_PERCENTAGES["headers_proof_received"]
            result.details = f"Received headers proof: {total_headers:,} total headers ({unique_headers:,} unique)"
            result.blocks_processed = total_headers
            result.sub_phase = "headers_proof_received"
            return True
        
        # Continue with other headers proof phase patterns...
        # (Similar pattern for anticone_download, utxo_chunks, etc.)
        
        return False
    
    def _process_block_download_phase(self, line: str, result: LogParseResult) -> bool:
        """Process block download phase logs."""
        # Block Headers
        match = REGEX_PATTERNS['block_headers'].search(line)
        if match:
            headers_processed, percentage = int(match.group(1)), int(match.group(2))
            
            # Extract timestamp if present
            timestamp_match = REGEX_PATTERNS['block_timestamp'].search(line)
            timestamp = timestamp_match.group(1).strip() if timestamp_match else None
            
            # Map to our overall progress
            min_pct, max_pct = SYNC_PHASE_PERCENTAGES["block_headers"]
            adjusted_percentage = min_pct + int((percentage / 100) * (max_pct - min_pct))
            
            result.phase = "Block Download"
            result.percentage = adjusted_percentage
            result.details = f"Processing block headers: {headers_processed:,} ({percentage}%)"
            result.blocks_processed = headers_processed
            result.timestamp = timestamp
            result.sub_phase = "block_headers"
            return True
        
        # Block Bodies
        match = REGEX_PATTERNS['block_bodies'].search(line)
        if match and "block headers" not in line:  # Ensure it's block bodies, not headers
            blocks_processed, percentage = int(match.group(1)), int(match.group(2))
            
            timestamp_match = REGEX_PATTERNS['block_timestamp'].search(line)
            timestamp = timestamp_match.group(1).strip() if timestamp_match else None
            
            min_pct, max_pct = SYNC_PHASE_PERCENTAGES["block_bodies"]
            adjusted_percentage = min_pct + int((percentage / 100) * (max_pct - min_pct))
            
            result.phase = "Block Download"
            result.percentage = adjusted_percentage
            result.details = f"Processing block bodies: {blocks_processed:,} ({percentage}%)"
            result.blocks_processed = blocks_processed
            result.timestamp = timestamp
            result.sub_phase = "block_bodies"
            return True
        
        return False
    
    def _process_special_cases(self, line: str, result: LogParseResult) -> None:
        """Process special case logs like Crescendo countdown."""
        match = REGEX_PATTERNS['crescendo_countdown'].search(line)
        if match:
            countdown = int(match.group(2))
            current_details = result.details or "Processing blocks"
            result.details = f"{current_details} [Crescendo countdown: -{countdown}]"
            result.sub_phase = "crescendo_countdown"
    
    def _check_basic_sync_indicators(self, log_lines: list, result: LogParseResult) -> LogParseResult:
        """Check for basic sync activity if no specific IBD logs found."""
        logs_text = " ".join(log_lines).lower()
        
        if "syncing" in logs_text:
            result.phase = "Connecting"
            result.percentage = 0
            result.details = "Connecting to network and establishing peers..."
            result.sub_phase = "connecting"
        elif "connecting" in logs_text:
            result.phase = "Connecting"
            result.percentage = 2
            result.details = "Establishing peer connections..."
            result.sub_phase = "peer_discovery"
        
        return result