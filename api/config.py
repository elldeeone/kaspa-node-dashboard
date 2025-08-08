"""
Configuration management for the Kaspa Node Dashboard API.
"""
import os
from typing import Dict, Any

# Application Configuration
API_HOST = "0.0.0.0"
API_PORT = 8000

# Kaspad Configuration
KASPAD_HOST = os.getenv("KASPAD_HOST", "kaspad")
KASPAD_RPC_PORT = int(os.getenv("KASPAD_RPC_PORT", "18110"))
KASPAD_GRPC_PORT = int(os.getenv("KASPAD_GRPC_PORT", "16110"))
KASPAD_CONTAINER_NAME = os.getenv("KASPAD_CONTAINER_NAME", "kaspad")

# Sync Progress Configuration
SYNC_PHASE_PERCENTAGES = {
    "negotiation_start": 5,
    "negotiation_chain": 10,
    "negotiation_zoom": 12,
    "headers_proof_start": 15,
    "headers_proof_received": 20,
    "anticone_download": 25,
    "utxo_download": 30,
    "utxo_complete": 35,
    "trusted_blocks_start": 40,
    "trusted_blocks_complete": 55,
    "sanity_check": 60,
    "staging_commit": 65,
    "block_search": 70,
    "block_headers": (70, 85),  # Range based on completion
    "block_bodies": (85, 90),   # Range based on completion
    "post_processing": 95,
    "complete": 100
}

# API Configuration
CORS_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080"
]

# Environment Configuration
IS_PRODUCTION = os.getenv("PRODUCTION", "false").lower() in ["true", "1", "yes"]
DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ["true", "1", "yes"] and not IS_PRODUCTION

# Connection Configuration (with environment variable overrides)
CONNECTION_TIMEOUT = int(os.getenv("CONNECTION_TIMEOUT", "60"))  # Total connection timeout in seconds
SOCKET_READ_TIMEOUT = int(os.getenv("SOCKET_READ_TIMEOUT", "30"))  # Socket read timeout in seconds
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))  # WebSocket heartbeat interval
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30.0"))  # Individual request timeout
CLEANUP_INTERVAL = float(os.getenv("CLEANUP_INTERVAL", "60.0"))  # Cleanup old requests interval
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))  # Health check interval
ONESHOT_TIMEOUT = float(os.getenv("ONESHOT_TIMEOUT", "10.0"))  # Timeout for oneshot RPC calls
MAX_ONESHOT_RETRIES = int(os.getenv("MAX_ONESHOT_RETRIES", "2"))  # Maximum retries for oneshot calls

# Retry Configuration
INITIAL_RETRY_DELAY = int(os.getenv("INITIAL_RETRY_DELAY", "5"))  # Initial reconnection delay
MAX_RETRY_DELAY = int(os.getenv("MAX_RETRY_DELAY", "60"))  # Maximum reconnection delay
RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", "1.5"))  # Exponential backoff multiplier
SUBSCRIPTION_RETRY_DELAY = int(os.getenv("SUBSCRIPTION_RETRY_DELAY", "30"))  # Initial subscription retry delay
MAX_SUBSCRIPTION_RETRY_DELAY = int(os.getenv("MAX_SUBSCRIPTION_RETRY_DELAY", "300"))  # Max subscription retry delay

# Circuit Breaker Configuration
MAX_CONNECTION_FAILURES = int(os.getenv("MAX_CONNECTION_FAILURES", "10"))  # Max failures before circuit breaker
CIRCUIT_BREAKER_COOLDOWN = int(os.getenv("CIRCUIT_BREAKER_COOLDOWN", "300"))  # Cooldown period in seconds

# Connection Pool Configuration
CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE", "3"))  # Number of connections in pool
CONNECTION_POOL_TIMEOUT = int(os.getenv("CONNECTION_POOL_TIMEOUT", "30"))  # Timeout for getting connection

# Monitoring Configuration
SYNC_CHECK_INTERVAL_SYNCING = 10  # seconds
SYNC_CHECK_INTERVAL_SYNCED = 30   # seconds
DOCKER_LOG_TAIL_LINES = 200
PEER_DISPLAY_LIMIT = 10

# Default responses for when kaspad is not ready
DEFAULT_KASPAD_INFO = {
    "isSynced": False,
    "version": "unknown",
    "hasUtxoIndex": False,
    "mempoolSize": 0,
    "networkName": "kaspa-mainnet",
    "p2pId": "syncing...",
    "status": "syncing"
}

DEFAULT_BLOCKDAG_INFO = {
    "blockCount": 0,
    "headerCount": 0,
    "tipHashes": [],
    "difficulty": 0,
    "pastMedianTime": 0,
    "virtualParentHashes": [],
    "prunedBlockCount": 0,
    "virtualDaaScore": 0,
    "status": "syncing"
}

DEFAULT_NETWORK_INFO = {
    "connectedPeers": 0,
    "mempoolSize": 0,
    "networkName": "kaspa-mainnet",
    "status": "syncing"
}

DEFAULT_PEER_INFO = {
    "peerCount": 0,
    "peers": [],
    "averagePing": 0,
    "ibdPeers": 0,
    "outboundPeers": 0,
    "inboundPeers": 0,
    "peerVersions": {},
    "status": "syncing"
}