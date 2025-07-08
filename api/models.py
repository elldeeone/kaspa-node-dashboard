"""
Data models for the Kaspa Node Dashboard API.
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import time

@dataclass
class SyncProgress:
    """Represents the current sync progress state."""
    is_syncing: bool
    percentage: int
    headers_processed: int
    blocks_processed: int
    status: str
    message: str
    phase: str
    sub_phase: Optional[str] = None
    peer_address: Optional[str] = None
    last_block_timestamp: Optional[str] = None
    error: Optional[str] = None
    last_update: float = None
    
    def __post_init__(self):
        if self.last_update is None:
            self.last_update = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_syncing": self.is_syncing,
            "percentage": self.percentage,
            "headers_processed": self.headers_processed,
            "blocks_processed": self.blocks_processed,
            "status": self.status,
            "message": self.message,
            "phase": self.phase,
            "sub_phase": self.sub_phase,
            "peer_address": self.peer_address,
            "last_block_timestamp": self.last_block_timestamp,
            "error": self.error,
            "last_update": self.last_update
        }

@dataclass
class LogParseResult:
    """Result of parsing sync progress from logs."""
    phase: str
    percentage: int
    details: str
    blocks_processed: int = 0
    timestamp: Optional[str] = None
    peer_address: Optional[str] = None
    sub_phase: Optional[str] = None
    error: Optional[str] = None

@dataclass
class ContainerUptime:
    """Container uptime information."""
    uptime_seconds: int
    uptime_formatted: str
    started_at: Optional[str] = None

@dataclass
class PeerInfo:
    """Information about a connected peer."""
    ip: str
    port: int
    ping: int
    connected_time: int
    is_ibd: bool
    is_outbound: bool
    version: str

@dataclass
class NetworkStats:
    """Network statistics."""
    peer_count: int
    peers: List[PeerInfo]
    average_ping: int
    ibd_peers: int
    outbound_peers: int
    inbound_peers: int
    peer_versions: Dict[str, int]
    status: str = "ready"