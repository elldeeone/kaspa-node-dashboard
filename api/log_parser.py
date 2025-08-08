"""
Log parser for extracting peer and uptime information from kaspad logs.
"""
import re
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque

logger = logging.getLogger(__name__)

class KaspadLogParser:
    """Parser for kaspad log files to extract peer and node information."""
    
    def __init__(self, log_file_path: str = "/logs/kaspad_buffer.log"):
        self.log_file_path = log_file_path
        self.peer_patterns = {
            # Pattern for peer connection with new log format: "2025-08-08 02:29:51.944+00:00 [INFO ] P2P Connected to outgoing peer 54.39.156.234:16111"
            'connected': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{2}:\d{2}).*?(?:P2P\s+)?Connected.*?peer\s+(\d+\.\d+\.\d+\.\d+:\d+)', re.IGNORECASE),
            # Pattern for peer disconnection
            'disconnected': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{2}:\d{2}).*?(?:Disconnected|closed|lost).*?(\d+\.\d+\.\d+\.\d+:\d+)', re.IGNORECASE),
            # Pattern for IBD peer
            'ibd_peer': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{2}:\d{2}).*?(?:IBD|ibd).*?peer.*?(\d+\.\d+\.\d+\.\d+:\d+)', re.IGNORECASE),
            # Pattern for outbound connection - look for "outgoing peer" in the message
            'outbound': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{2}:\d{2}).*?(?:outgoing\s+peer|outbound).*?(\d+\.\d+\.\d+\.\d+:\d+)', re.IGNORECASE),
            # Pattern for protocol version - "Registering p2p flows for peer X for protocol version Y"
            'protocol_version': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{2}:\d{2}).*?Registering\s+p2p\s+flows.*?peer\s+(\d+\.\d+\.\d+\.\d+:\d+).*?protocol\s+version\s+(\d+)', re.IGNORECASE),
        }
        
        # Pattern for node start - look for "kaspad v" at the beginning
        self.start_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+\-]\d{2}:\d{2}).*?(?:kaspad\s+v[\d.]+|Application\s+version|Starting\s+Kaspad)', re.IGNORECASE)
        
        # Pattern for peer count in logs
        self.peer_count_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?).*?(?:peers?|connections?)[:\s]+(\d+)', re.IGNORECASE)
        
    def parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse log timestamp to datetime object."""
        try:
            # Handle the new format: "2025-08-08 02:29:37.648+00:00"
            # Replace space with T to make it ISO format
            if ' ' in timestamp_str:
                timestamp_str = timestamp_str.replace(' ', 'T')
            
            # Handle different timestamp formats
            if 'Z' in timestamp_str:
                timestamp_str = timestamp_str.replace('Z', '+00:00')
            
            # Python's strptime %z expects timezone without colon (e.g., +0000 not +00:00)
            # So we need to handle the colon in timezone offset
            if '+' in timestamp_str or '-' in timestamp_str:
                # Handle timezone with colon: +00:00 -> +0000
                if timestamp_str[-3] == ':':
                    timestamp_str = timestamp_str[:-3] + timestamp_str[-2:]
            
            # Try different formats
            formats = [
                '%Y-%m-%dT%H:%M:%S.%f%z',
                '%Y-%m-%dT%H:%M:%S%z',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S',
            ]
            
            for fmt in formats:
                try:
                    if '%z' not in fmt:
                        # Parse without timezone and assume UTC
                        dt = datetime.strptime(timestamp_str.replace('+0000', '').replace('-0000', ''), fmt)
                        return dt.replace(tzinfo=None)  # Return naive datetime
                    else:
                        dt = datetime.strptime(timestamp_str, fmt)
                        return dt.replace(tzinfo=None)  # Convert to naive for simplicity
                except ValueError:
                    continue
                    
            return None
        except Exception as e:
            logger.debug(f"Failed to parse timestamp {timestamp_str}: {e}")
            return None
    
    def read_recent_logs(self, max_lines: int = 5000) -> List[str]:
        """Read recent log lines from the circular buffer file."""
        try:
            if not os.path.exists(self.log_file_path):
                logger.debug(f"Log file not found: {self.log_file_path}")
                return []
            
            with open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Use deque for efficient memory usage
                lines = deque(f, maxlen=max_lines)
                return list(lines)
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return []
    
    def extract_node_start_time(self, lines: List[str]) -> Optional[datetime]:
        """Extract node start time from logs."""
        for line in lines:
            match = self.start_pattern.search(line)
            if match:
                timestamp_str = match.group(1)
                start_time = self.parse_timestamp(timestamp_str)
                if start_time:
                    return start_time
        return None
    
    def calculate_uptime(self, start_time: Optional[datetime]) -> str:
        """Calculate uptime from start time."""
        if not start_time:
            return "Unknown"
        
        now = datetime.utcnow()
        uptime_delta = now - start_time
        
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def extract_peer_info(self, lines: List[str]) -> Dict[str, any]:
        """Extract peer information from log lines."""
        connected_peers = {}
        disconnected_peers = set()
        ibd_peers = set()
        outbound_peers = set()
        peer_versions = {}  # Store protocol versions for each peer
        
        # Process lines in order to track peer state
        for line in lines:
            # Check for connected peers
            match = self.peer_patterns['connected'].search(line)
            if match:
                timestamp_str = match.group(1)
                peer_address = match.group(2)
                timestamp = self.parse_timestamp(timestamp_str)
                if peer_address not in disconnected_peers:
                    connected_peers[peer_address] = {
                        'connected_time': timestamp,
                        'is_ibd': False,
                        'is_outbound': False
                    }
            
            # Check for disconnected peers
            match = self.peer_patterns['disconnected'].search(line)
            if match:
                peer_address = match.group(2)
                disconnected_peers.add(peer_address)
                if peer_address in connected_peers:
                    del connected_peers[peer_address]
            
            # Check for IBD peers
            match = self.peer_patterns['ibd_peer'].search(line)
            if match:
                peer_address = match.group(2)
                ibd_peers.add(peer_address)
                if peer_address in connected_peers:
                    connected_peers[peer_address]['is_ibd'] = True
            
            # Check for outbound connections
            match = self.peer_patterns['outbound'].search(line)
            if match:
                peer_address = match.group(2)
                outbound_peers.add(peer_address)
                if peer_address in connected_peers:
                    connected_peers[peer_address]['is_outbound'] = True
            
            # Check for protocol version
            match = self.peer_patterns['protocol_version'].search(line)
            if match:
                peer_address = match.group(2)
                protocol_version = match.group(3)
                peer_versions[peer_address] = protocol_version
        
        # Build peer list
        peer_list = []
        now = datetime.utcnow()
        
        for peer_address, info in connected_peers.items():
            ip, port = peer_address.rsplit(':', 1)
            connected_duration = 0
            
            if info['connected_time']:
                delta = now - info['connected_time']
                connected_duration = int(delta.total_seconds())
            
            # Get protocol version if available
            protocol_version = peer_versions.get(peer_address, 'Unknown')
            version_string = f'Protocol v{protocol_version}' if protocol_version != 'Unknown' else 'Unknown'
            
            peer_list.append({
                'ip': ip,
                'port': int(port),
                'address': peer_address,
                'connected_time': connected_duration,
                'is_ibd': info['is_ibd'] or peer_address in ibd_peers,
                'is_outbound': info['is_outbound'] or peer_address in outbound_peers,
                'ping': 0,  # Will be filled from RPC if available
                'version': version_string,  # Protocol version from logs
                'protocol_version': int(protocol_version) if protocol_version != 'Unknown' else 0
            })
        
        # Count statistics
        total_peers = len(peer_list)
        ibd_peer_count = sum(1 for p in peer_list if p['is_ibd'])
        outbound_count = sum(1 for p in peer_list if p['is_outbound'])
        inbound_count = total_peers - outbound_count
        
        return {
            'peer_count': total_peers,
            'peers': peer_list,
            'ibd_peers': ibd_peer_count,
            'outbound_peers': outbound_count,
            'inbound_peers': inbound_count
        }
    
    def extract_peer_count_from_logs(self, lines: List[str]) -> Optional[int]:
        """Extract peer count from log messages."""
        # Look for the most recent peer count mention
        for line in reversed(lines):
            match = self.peer_count_pattern.search(line)
            if match:
                try:
                    return int(match.group(2))
                except (ValueError, IndexError):
                    continue
        return None
    
    def parse_logs(self) -> Dict[str, any]:
        """Parse logs and extract all available information."""
        lines = self.read_recent_logs(max_lines=10000)  # Read all available lines from buffer
        
        if not lines:
            logger.debug("No log lines to parse")
            return {
                'uptime': 'Unknown',
                'peer_info': {
                    'peer_count': 0,
                    'peers': [],
                    'ibd_peers': 0,
                    'outbound_peers': 0,
                    'inbound_peers': 0
                },
                'log_available': False
            }
        
        # Extract node start time and calculate uptime
        start_time = self.extract_node_start_time(lines)
        uptime = self.calculate_uptime(start_time)
        
        # Extract peer information
        peer_info = self.extract_peer_info(lines)
        
        # Try to get peer count from logs if no peers found
        if peer_info['peer_count'] == 0:
            log_peer_count = self.extract_peer_count_from_logs(lines)
            if log_peer_count is not None:
                peer_info['peer_count'] = log_peer_count
        
        return {
            'uptime': uptime,
            'uptime_seconds': int((datetime.utcnow() - start_time).total_seconds()) if start_time else 0,
            'node_start_time': start_time.isoformat() if start_time else None,
            'peer_info': peer_info,
            'log_available': True
        }