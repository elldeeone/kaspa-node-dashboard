"""
Utility functions for the Kaspa Node Dashboard API.
"""
import re
import subprocess
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for performance
REGEX_PATTERNS = {
    'ibd_complete_success': re.compile(r'IBD with peer ([^\s]+) completed successfully'),
    'ibd_complete_error': re.compile(r'IBD with peer ([^\s]+) completed with error: (.+)'),
    'ibd_unorphaned': re.compile(r'unorphaned (\d+) blocks'),
    'ibd_started': re.compile(r'IBD started with peer ([^\s]+)'),
    'chain_negotiation': re.compile(r'IBD chain negotiation with peer ([^\s]+) started and received (\d+) hashes'),
    'negotiation_zoom': re.compile(r'IBD chain negotiation with peer ([^\s]+) zoomed in'),
    'negotiation_restart': re.compile(r'IBD chain negotiation with syncer ([^\s]+) restarted (\d+) times'),
    'headers_proof_start': re.compile(r'Starting IBD with headers proof with peer ([^\s]+)'),
    'headers_proof_received': re.compile(r'Received headers proof with overall (\d+) headers \((\d+) unique\)'),
    'anticone_download': re.compile(r'Downloaded (\d+) blocks from the pruning point anticone'),
    'utxo_chunks': re.compile(r'Received (\d+) UTXO set chunks so far, totaling in (\d+) UTXOs'),
    'utxo_complete': re.compile(r'Finished receiving the UTXO set\. Total UTXOs: (\d+)'),
    'trusted_blocks_start': re.compile(r'Starting to process (\d+) trusted blocks'),
    'trusted_blocks_progress': re.compile(r'Processed (\d+) trusted blocks in the last ([\d.]+)s \(total (\d+)\)'),
    'block_headers': re.compile(r'IBD: Processed (\d+) block headers \((\d+)%\)'),
    'block_bodies': re.compile(r'IBD: Processed (\d+) blocks \((\d+)%\)'),
    'block_timestamp': re.compile(r'last block timestamp: ([^:]+)'),
    'crescendo_countdown': re.compile(r'Accepted block ([^\s]+) via relay \[Crescendo countdown: -(\d+)\]'),
    'peer_version': re.compile(r'/kaspad:([^/]+)/')
}

async def run_docker_command(command: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Execute a docker command asynchronously.
    
    Args:
        command: Docker command to execute
        timeout: Command timeout in seconds
    
    Returns:
        Dictionary with success status, output, and error
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", *command.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), 
            timeout=timeout
        )
        
        return {
            "success": process.returncode == 0,
            "output": stdout.decode('utf-8'),
            "error": stderr.decode('utf-8')
        }
    except asyncio.TimeoutError:
        return {"success": False, "output": "", "error": "Command timed out"}
    except Exception as e:
        return {"success": False, "output": "", "error": f"Command failed: {e}"}

def extract_peer_version(user_agent: str) -> str:
    """Extract version from kaspad user agent string."""
    if "/kaspad:" in user_agent:
        match = REGEX_PATTERNS['peer_version'].search(user_agent)
        return match.group(1) if match else "unknown"
    return "unknown"

def format_uptime(seconds: int) -> str:
    """Format uptime seconds into human-readable string."""
    if seconds <= 0:
        return "Unknown"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m {secs}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def get_container_uptime() -> tuple:
    """
    Get the container's uptime by calculating from PID 1's start time.
    Returns tuple of (uptime_seconds, uptime_formatted).
    
    This works by finding when PID 1 (the container's init process) started,
    which effectively gives us the container start time without needing Docker socket access.
    """
    import os
    import time
    
    try:
        # Get system boot time from /proc/stat
        boot_time = 0
        with open('/proc/stat', 'r') as f:
            for line in f:
                if line.startswith('btime'):
                    boot_time = int(line.split()[1])
                    break
        
        if boot_time == 0:
            raise ValueError("Could not find boot time in /proc/stat")
        
        # Get PID 1 start time in clock ticks from /proc/1/stat
        with open('/proc/1/stat', 'r') as f:
            # The stat file format has the command name in parentheses, 
            # so we split after the last ')' to get the numeric fields
            stat_data = f.read()
            # Find the last ) to handle commands with ) in their name
            last_paren = stat_data.rfind(')')
            fields = stat_data[last_paren + 1:].split()
            starttime_ticks = int(fields[19])  # 22nd field (0-indexed as 19 after command name)
        
        # Convert ticks to seconds
        clock_ticks_per_sec = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
        starttime_seconds = starttime_ticks / clock_ticks_per_sec
        
        # Calculate actual start time
        pid1_start_time = boot_time + starttime_seconds
        
        # Calculate uptime
        current_time = time.time()
        uptime_seconds = int(current_time - pid1_start_time)
        
        # Format the uptime
        uptime_formatted = format_uptime(uptime_seconds)
        
        return uptime_seconds, uptime_formatted
        
    except Exception as e:
        logger.debug(f"Could not calculate container uptime: {e}")
        return 0, "Unknown"

def format_timestamp(timestamp_ms: int) -> str:
    """Format timestamp from milliseconds to readable string."""
    if timestamp_ms <= 0:
        return "unknown"
    
    try:
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, OSError):
        return f"timestamp: {timestamp_ms}"

def format_hash(hash_string: str) -> str:
    """Format hash string for display."""
    if not hash_string or hash_string == "unknown":
        return "unknown"
    
    if len(hash_string) > 16:
        return f"{hash_string[:8]}...{hash_string[-8:]}"
    
    return hash_string

def calculate_percentage_range(current: int, total: int, min_pct: int, max_pct: int) -> int:
    """Calculate percentage within a range based on progress."""
    if total <= 0:
        return min_pct
    
    progress_ratio = min(current / total, 1.0)
    return min_pct + int((max_pct - min_pct) * progress_ratio)

class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, max_calls: int, time_window: int):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def is_allowed(self) -> bool:
        """Check if a call is allowed under rate limit."""
        now = datetime.now().timestamp()
        
        # Remove old calls outside the time window
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < self.time_window]
        
        if len(self.calls) >= self.max_calls:
            return False
        
        self.calls.append(now)
        return True