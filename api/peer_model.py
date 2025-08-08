"""
Unified peer data model for Kaspa Node Dashboard.

This module provides a consistent data structure for peer information
across different data sources (RPC, logs, API responses).
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Unified peer data model used throughout the application.
    
    This class normalizes peer data from various sources (RPC, logs)
    into a consistent format for use across the application.
    """
    
    # Identity
    id: str
    ip: str
    port: int
    
    # Connection details
    is_outbound: bool
    is_ibd: bool
    connection_duration_seconds: int
    
    # Performance
    ping_ms: float  # Always in milliseconds with decimal precision
    
    # Version info
    version: str  # Clean version like "1.0.0" or "Unknown"
    user_agent: str  # Full user agent string if available
    protocol_version: int
    
    @property
    def address(self) -> str:
        """Get formatted address string."""
        return f"{self.ip}:{self.port}"
    
    @classmethod
    def from_rpc_data(cls, rpc_peer: Dict[str, Any]) -> 'PeerInfo':
        """Create PeerInfo from RPC response format.
        
        Args:
            rpc_peer: Peer data from getConnectedPeerInfo RPC call
            
        Returns:
            Normalized PeerInfo instance
        """
        # Extract address components
        addr = rpc_peer.get("address", {})
        ip = addr.get("ip", "")
        port = addr.get("port", 0)
        
        # Ping duration is in milliseconds from the RPC
        ping_ms = rpc_peer.get("last_ping_duration", 0)
        ping_ms = round(ping_ms, 1) if ping_ms else 0.0
        
        # Extract version from user agent
        user_agent = rpc_peer.get("user_agent", "")
        version = cls._extract_version_from_user_agent(user_agent)
        
        # Convert time_connected from milliseconds to seconds
        time_connected_ms = rpc_peer.get("time_connected", 0)
        connection_duration = time_connected_ms // 1000 if time_connected_ms else 0
        
        return cls(
            id=rpc_peer.get("id", ""),
            ip=ip,
            port=port,
            is_outbound=rpc_peer.get("is_outbound", True),
            is_ibd=rpc_peer.get("is_ibd_peer", False),
            connection_duration_seconds=connection_duration,
            ping_ms=ping_ms,
            version=version,
            user_agent=user_agent,
            protocol_version=rpc_peer.get("advertised_protocol_version", 0)
        )
    
    @classmethod
    def from_log_data(cls, log_peer: Dict[str, Any]) -> 'PeerInfo':
        """Create PeerInfo from log parser format.
        
        Args:
            log_peer: Peer data parsed from kaspad logs
            
        Returns:
            Normalized PeerInfo instance
        """
        # Parse address if provided as string
        address = log_peer.get("address", "")
        if ":" in address:
            ip, port_str = address.rsplit(":", 1)
            port = int(port_str) if port_str.isdigit() else 0
        else:
            ip = log_peer.get("ip", "")
            port = log_peer.get("port", 0)
        
        # Version might be in different formats
        version = log_peer.get("version", "")
        if version.startswith("Protocol v"):
            # Keep protocol version format for log-based peers
            pass
        elif version and not version.startswith("v"):
            version = f"v{version}"
        elif not version:
            version = "Unknown"
        
        return cls(
            id="",  # Logs don't provide peer IDs
            ip=ip,
            port=port,
            is_outbound=log_peer.get("is_outbound", log_peer.get("is_outbound", False)),
            is_ibd=log_peer.get("is_ibd", log_peer.get("is_ibd_peer", False)),
            connection_duration_seconds=log_peer.get("connected_time", 0),
            ping_ms=float(log_peer.get("ping", 0)),
            version=version,
            user_agent="",  # Not available in logs
            protocol_version=log_peer.get("protocol_version", 0)
        )
    
    @classmethod
    def from_mixed_format(cls, peer: Dict[str, Any]) -> 'PeerInfo':
        """Create PeerInfo from mixed format (RPC or log data).
        
        This method intelligently detects the format and calls the appropriate parser.
        
        Args:
            peer: Peer data in either RPC or log format
            
        Returns:
            Normalized PeerInfo instance
        """
        # Detect format based on key presence
        if "address" in peer and isinstance(peer["address"], dict):
            # RPC format (address is an object with ip/port)
            return cls.from_rpc_data(peer)
        else:
            # Log format or already transformed
            return cls.from_log_data(peer)
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert to API response format for frontend consumption.
        
        Returns:
            Dictionary formatted for API response
        """
        # Ensure version has 'v' prefix for frontend
        display_version = self.version
        if display_version and not display_version.startswith("v") and display_version != "Unknown":
            display_version = f"v{display_version}"
        
        return {
            "id": self.id,
            "address": self.address,
            "ping": self.ping_ms,
            "connected_time": self.connection_duration_seconds,
            "is_ibd": self.is_ibd,
            "is_outbound": self.is_outbound,
            "version": display_version,
            "protocol_version": self.protocol_version
        }
    
    def to_internal_format(self) -> Dict[str, Any]:
        """Convert to internal format used by existing code.
        
        This maintains backward compatibility with existing code.
        
        Returns:
            Dictionary in internal format with both camelCase and snake_case keys
        """
        return {
            # Identity
            "id": self.id,
            "address": self.address,
            "ip": self.ip,
            "port": self.port,
            
            # Connection (multiple formats for compatibility)
            "isOutbound": self.is_outbound,
            "is_outbound": self.is_outbound,
            "isIbdPeer": self.is_ibd,
            "is_ibd": self.is_ibd,
            "connectedTime": self.connection_duration_seconds,
            "connected_time": self.connection_duration_seconds,
            
            # Performance
            "ping": self.ping_ms,
            "lastPingDuration": self.ping_ms,  # Keep in milliseconds
            
            # Version
            "version": self.version,
            "userAgent": self.user_agent,
            "advertisedProtocolVersion": self.protocol_version,
            "protocol_version": self.protocol_version
        }
    
    @staticmethod
    def _extract_version_from_user_agent(user_agent: str) -> str:
        """Extract clean version string from user agent.
        
        Args:
            user_agent: Raw user agent string like "/kaspad:1.0.0/..."
            
        Returns:
            Clean version string like "1.0.0"
        """
        if not user_agent:
            return "Unknown"
        
        # Parse from format: "/kaspad:1.0.0/kaspad:1.0.0(kaspa-ng:1.0.1-2a36ea0)/"
        if user_agent.startswith("/"):
            try:
                parts = [p for p in user_agent.split("/") if p]
                for part in parts:
                    if "kaspad:" in part:
                        # Extract version after "kaspad:"
                        version = part.split("kaspad:")[1].split("(")[0].strip()
                        return version if version else "Unknown"
            except (IndexError, AttributeError):
                logger.debug(f"Failed to parse version from user agent: {user_agent}")
        
        return "Unknown"


class PeerInfoCollection:
    """Collection of PeerInfo objects with utility methods."""
    
    def __init__(self):
        self.peers: Dict[str, PeerInfo] = {}  # Keyed by address
    
    def add_peer(self, peer: PeerInfo):
        """Add or update a peer in the collection."""
        self.peers[peer.address] = peer
    
    def remove_peer(self, address: str):
        """Remove a peer from the collection."""
        self.peers.pop(address, None)
    
    def get_peer(self, address: str) -> Optional[PeerInfo]:
        """Get a peer by address."""
        return self.peers.get(address)
    
    @property
    def total_count(self) -> int:
        """Total number of peers."""
        return len(self.peers)
    
    @property
    def outbound_count(self) -> int:
        """Number of outbound peers."""
        return sum(1 for p in self.peers.values() if p.is_outbound)
    
    @property
    def inbound_count(self) -> int:
        """Number of inbound peers."""
        return sum(1 for p in self.peers.values() if not p.is_outbound)
    
    @property
    def ibd_count(self) -> int:
        """Number of IBD peers."""
        return sum(1 for p in self.peers.values() if p.is_ibd)
    
    @property
    def average_ping(self) -> float:
        """Calculate average ping across all peers."""
        pings = [p.ping_ms for p in self.peers.values() if p.ping_ms > 0]
        return round(sum(pings) / len(pings), 1) if pings else 0.0
    
    def to_api_response(self) -> Dict[str, Any]:
        """Convert collection to API response format."""
        peer_list = [peer.to_api_response() for peer in self.peers.values()]
        
        return {
            "peerCount": self.total_count,
            "peers": peer_list,
            "averagePing": self.average_ping,
            "ibdPeers": self.ibd_count,
            "outboundPeers": self.outbound_count,
            "inboundPeers": self.inbound_count
        }