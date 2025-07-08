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