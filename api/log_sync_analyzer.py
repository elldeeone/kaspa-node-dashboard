"""
Log-based sync progress analyzer for Kaspa Node Dashboard.
Reads logs from /logs/kaspad_buffer.log and extracts sync progress directly from log messages.
"""
import logging
import re
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex patterns for extracting sync progress from logs
LOG_PATTERNS = {
    # IBD completion states
    'ibd_complete_success': re.compile(r'IBD with peer ([^\s]+) completed successfully'),
    'ibd_complete_error': re.compile(r'IBD with peer ([^\s]+) completed with error: (.+)'),
    
    # IBD phases
    'ibd_started': re.compile(r'IBD started with peer ([^\s]+)'),
    'headers_proof_start': re.compile(r'Starting IBD with headers proof with peer ([^\s]+)'),
    
    # Progress indicators with percentages  
    'block_headers': re.compile(r'IBD: Processed (\d+) block headers \((\d+)%\)'),
    'block_bodies': re.compile(r'IBD: Processed (\d+) blocks \((\d+)%\)'),
    
    # Headers proof progress
    'headers_proof_received': re.compile(r'Received headers proof with overall (\d+) headers \((\d+) unique\)'),
    'trusted_blocks_start': re.compile(r'Starting to process (\d+) trusted blocks'),
    'trusted_blocks_progress': re.compile(r'Processed (\d+) trusted blocks in the last ([\d.]+)s \(total (\d+)\)'),
    
    # UTXO set progress
    'utxo_chunks': re.compile(r'Received (\d+) UTXO set chunks so far, totaling in (\d+) UTXOs'),
    'utxo_complete': re.compile(r'Finished receiving the UTXO set\. Total UTXOs: (\d+)'),
    
    # Block timestamp extraction
    'block_timestamp': re.compile(r'last block timestamp: ([^:]+)'),
    
    # Crescendo countdown
    'crescendo_countdown': re.compile(r'Accepted block ([^\s]+) via relay \[Crescendo countdown: -(\d+)\]'),
}

# Phase percentage mappings (adjusted for overall progress)
PHASE_PERCENTAGES = {
    "ibd_negotiation": (0, 15),      # 0-15%
    "headers_proof": (15, 65),       # 15-65%
    "block_headers": (65, 75),       # 65-75%
    "block_bodies": (75, 90),        # 75-90%
    "finalization": (90, 100)        # 90-100%
}

class LogSyncAnalyzer:
    """Analyzes sync progress from kaspad log file."""
    
    def __init__(self, log_file_path: str = "/logs/kaspad_buffer.log"):
        self.log_file_path = Path(log_file_path)
        self.last_position = 0
        self.cached_state = {
            "phase": "Initializing",
            "percentage": 0,
            "details": "Starting up...",
            "sub_phase": None,
            "blocks_processed": 0,
            "headers_processed": 0,
            "timestamp": None,
            "peer_address": None,
            "is_synced": False
        }
    
    def read_log_file(self) -> str:
        """Read the log file and return its contents."""
        try:
            if not self.log_file_path.exists():
                logger.warning(f"Log file not found: {self.log_file_path}")
                return ""
            
            with open(self.log_file_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return ""
    
    def analyze_sync_progress(self) -> Dict[str, Any]:
        """
        Analyze log file to determine current sync progress.
        Returns sync state with percentage directly extracted from logs.
        """
        try:
            log_content = self.read_log_file()
            if not log_content:
                return self.cached_state
            
            # Parse logs and update cached state
            self._parse_logs(log_content)
            return self.cached_state
            
        except Exception as e:
            logger.error(f"Error analyzing sync progress: {e}")
            return self.cached_state
    
    def _parse_logs(self, log_content: str) -> None:
        """Parse log content and update cached state with sync progress."""
        log_lines = [line.strip() for line in log_content.split('\n') if line.strip()]
        
        # Check for completion first (parse in reverse to get most recent)
        for line in reversed(log_lines[-100:]):  # Check last 100 lines for completion
            if self._check_completion(line):
                return
        
        # Parse forward to track progressive state
        for line in log_lines:
            self._process_log_line(line)
    
    def _check_completion(self, line: str) -> bool:
        """Check if IBD is complete."""
        # Success completion
        match = LOG_PATTERNS['ibd_complete_success'].search(line)
        if match:
            peer = match.group(1)
            self.cached_state.update({
                "phase": "Complete",
                "percentage": 100,
                "details": f"IBD completed successfully with peer {peer}",
                "sub_phase": "complete",
                "peer_address": peer,
                "is_synced": True
            })
            return True
        
        # Error completion
        match = LOG_PATTERNS['ibd_complete_error'].search(line)
        if match:
            peer = match.group(1)
            error = match.group(2)
            self.cached_state.update({
                "phase": "Error",
                "percentage": self.cached_state.get("percentage", 0),
                "details": f"IBD failed with peer {peer}: {error}",
                "sub_phase": "error",
                "peer_address": peer,
                "error": error
            })
            return True
        
        return False
    
    def _process_log_line(self, line: str) -> None:
        """Process a single log line and update state."""
        
        # IBD Started
        match = LOG_PATTERNS['ibd_started'].search(line)
        if match:
            peer = match.group(1)
            self.cached_state.update({
                "phase": "IBD Negotiation",
                "percentage": 5,
                "details": f"IBD started with peer {peer}",
                "sub_phase": "negotiation",
                "peer_address": peer
            })
            return
        
        # Headers Proof Start
        match = LOG_PATTERNS['headers_proof_start'].search(line)
        if match:
            peer = match.group(1)
            self.cached_state.update({
                "phase": "Headers Proof IBD",
                "percentage": 15,
                "details": f"Starting headers proof with peer {peer}",
                "sub_phase": "headers_proof",
                "peer_address": peer
            })
            return
        
        # Block Headers Progress (with percentage)
        match = LOG_PATTERNS['block_headers'].search(line)
        if match:
            headers_processed = int(match.group(1))
            percentage = int(match.group(2))
            
            # Extract timestamp if present
            timestamp_match = LOG_PATTERNS['block_timestamp'].search(line)
            timestamp = timestamp_match.group(1).strip() if timestamp_match else None
            
            # Map the percentage to our overall progress range
            min_pct, max_pct = PHASE_PERCENTAGES["block_headers"]
            adjusted_percentage = min_pct + int((percentage / 100) * (max_pct - min_pct))
            
            self.cached_state.update({
                "phase": "Block Download",
                "percentage": adjusted_percentage,
                "details": f"Processing block headers: {headers_processed:,} ({percentage}%)",
                "sub_phase": "block_headers",
                "headers_processed": headers_processed,
                "timestamp": timestamp
            })
            return
        
        # Block Bodies Progress (with percentage)
        match = LOG_PATTERNS['block_bodies'].search(line)
        if match and "block headers" not in line:  # Ensure it's bodies, not headers
            blocks_processed = int(match.group(1))
            percentage = int(match.group(2))
            
            # Extract timestamp if present
            timestamp_match = LOG_PATTERNS['block_timestamp'].search(line)
            timestamp = timestamp_match.group(1).strip() if timestamp_match else None
            
            # Map the percentage to our overall progress range
            min_pct, max_pct = PHASE_PERCENTAGES["block_bodies"]
            adjusted_percentage = min_pct + int((percentage / 100) * (max_pct - min_pct))
            
            self.cached_state.update({
                "phase": "Block Download",
                "percentage": adjusted_percentage,
                "details": f"Processing blocks: {blocks_processed:,} ({percentage}%)",
                "sub_phase": "block_bodies",
                "blocks_processed": blocks_processed,
                "timestamp": timestamp
            })
            return
        
        # Headers Proof Received
        match = LOG_PATTERNS['headers_proof_received'].search(line)
        if match:
            total_headers = int(match.group(1))
            unique_headers = int(match.group(2))
            
            # Estimate progress in headers proof phase (15-65%)
            min_pct, max_pct = PHASE_PERCENTAGES["headers_proof"]
            # Rough estimate: receiving headers is about 30% through the phase
            adjusted_percentage = min_pct + int(0.3 * (max_pct - min_pct))
            
            self.cached_state.update({
                "phase": "Headers Proof IBD",
                "percentage": adjusted_percentage,
                "details": f"Received {total_headers:,} headers ({unique_headers:,} unique)",
                "sub_phase": "headers_proof_received"
            })
            return
        
        # Trusted Blocks Processing
        match = LOG_PATTERNS['trusted_blocks_start'].search(line)
        if match:
            total_blocks = int(match.group(1))
            
            # Starting trusted blocks means we're about 40% through headers proof
            min_pct, max_pct = PHASE_PERCENTAGES["headers_proof"]
            adjusted_percentage = min_pct + int(0.4 * (max_pct - min_pct))
            
            self.cached_state.update({
                "phase": "Headers Proof IBD",
                "percentage": adjusted_percentage,
                "details": f"Processing {total_blocks:,} trusted blocks",
                "sub_phase": "trusted_blocks",
                "trusted_blocks_total": total_blocks
            })
            return
        
        # Trusted Blocks Progress
        match = LOG_PATTERNS['trusted_blocks_progress'].search(line)
        if match:
            processed_recent = int(match.group(1))
            time_taken = float(match.group(2))
            total_processed = int(match.group(3))
            
            # Calculate progress through trusted blocks (40-90% of headers proof phase)
            trusted_total = self.cached_state.get("trusted_blocks_total", 100000)  # Default estimate
            if trusted_total > 0:
                progress_ratio = min(total_processed / trusted_total, 1.0)
                min_pct, max_pct = PHASE_PERCENTAGES["headers_proof"]
                # Trusted blocks are 40-90% of the headers proof phase
                phase_progress = 0.4 + (0.5 * progress_ratio)
                adjusted_percentage = min_pct + int(phase_progress * (max_pct - min_pct))
                
                self.cached_state.update({
                    "phase": "Headers Proof IBD",
                    "percentage": adjusted_percentage,
                    "details": f"Processed {total_processed:,}/{trusted_total:,} trusted blocks",
                    "sub_phase": "trusted_blocks_progress",
                    "trusted_blocks_processed": total_processed
                })
            return
        
        # UTXO Chunks
        match = LOG_PATTERNS['utxo_chunks'].search(line)
        if match:
            chunks = int(match.group(1))
            utxos = int(match.group(2))
            
            # UTXO processing is near the end of headers proof (85-95% of phase)
            min_pct, max_pct = PHASE_PERCENTAGES["headers_proof"]
            adjusted_percentage = min_pct + int(0.85 * (max_pct - min_pct))
            
            self.cached_state.update({
                "phase": "Headers Proof IBD",
                "percentage": adjusted_percentage,
                "details": f"Received {chunks} UTXO chunks ({utxos:,} UTXOs)",
                "sub_phase": "utxo_sync"
            })
            return
        
        # UTXO Complete
        match = LOG_PATTERNS['utxo_complete'].search(line)
        if match:
            total_utxos = int(match.group(1))
            
            # UTXO complete means headers proof is done, moving to block download
            self.cached_state.update({
                "phase": "Block Download",
                "percentage": 65,
                "details": f"UTXO set complete ({total_utxos:,} UTXOs)",
                "sub_phase": "utxo_complete"
            })
            return
        
        # Crescendo Countdown (special indicator)
        match = LOG_PATTERNS['crescendo_countdown'].search(line)
        if match:
            countdown = int(match.group(2))
            current_details = self.cached_state.get("details", "Processing blocks")
            self.cached_state["details"] = f"{current_details} [Crescendo: -{countdown}]"
            return
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get comprehensive sync status including progress.
        Compatible with existing API structure.
        """
        progress = self.analyze_sync_progress()
        
        return {
            "is_synced": progress.get("is_synced", False),
            "percentage": progress.get("percentage", 0),
            "phase": progress.get("phase", "Unknown"),
            "sub_phase": progress.get("sub_phase"),
            "details": progress.get("details", ""),
            "blocks_processed": progress.get("blocks_processed", 0),
            "headers_processed": progress.get("headers_processed", 0),
            "timestamp": progress.get("timestamp"),
            "peer_address": progress.get("peer_address"),
            "error": progress.get("error")
        }