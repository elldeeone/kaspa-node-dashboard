"""
Kaspa Node Dashboard API Server

FastAPI application with persistent WebSocket connection for monitoring Kaspa nodes.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import our components
from config import API_HOST, API_PORT, KASPAD_HOST, KASPAD_RPC_PORT, CORS_ORIGINS
from persistent_rpc_client import PersistentKaspadRPCClient
from routes import create_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global persistent client
persistent_client: PersistentKaspadRPCClient = None
refresh_task: asyncio.Task = None

async def periodic_refresh():
    """Periodically refresh cached data with intelligent intervals."""
    global persistent_client
    
    while True:
        try:
            if persistent_client:
                # Determine refresh interval based on sync status
                is_synced = persistent_client.is_synced()
                is_connected = persistent_client.connected
                
                if not is_connected:
                    # During IBD or disconnected, refresh every 5 seconds
                    await persistent_client._refresh_cached_data()
                    logger.debug("Cache refresh attempted (disconnected/IBD mode)")
                    refresh_interval = 5
                elif not is_synced:
                    # While syncing but connected, refresh every 10 seconds
                    await persistent_client._refresh_cached_data()
                    logger.debug("Cache refresh completed (syncing)")
                    refresh_interval = 10
                else:
                    # When fully synced, refresh less frequently (60 seconds)
                    # Events will trigger updates, this is just backup
                    await persistent_client._refresh_cached_data()
                    logger.debug("Periodic cache refresh completed (synced)")
                    refresh_interval = 60
                
                await asyncio.sleep(refresh_interval)
            else:
                await asyncio.sleep(5)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic refresh: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan with persistent WebSocket connection."""
    global persistent_client, refresh_task
    
    # Startup
    logger.info("Starting Kaspa Node Dashboard API with Persistent WebSocket")
    
    # Initialize persistent RPC client
    persistent_client = PersistentKaspadRPCClient(KASPAD_HOST, KASPAD_RPC_PORT)
    
    # Establish persistent connection
    connected = await persistent_client.connect()
    if connected:
        logger.info("Successfully connected to kaspad with persistent WebSocket")
    else:
        logger.warning("Failed initial connection to kaspad - will retry automatically")
    
    # Start periodic refresh task
    refresh_task = asyncio.create_task(periodic_refresh())
    
    yield
    
    # Shutdown
    logger.info("Shutting down Kaspa Node Dashboard API")
    
    if refresh_task:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
    
    if persistent_client:
        await persistent_client.close()

# Create FastAPI app with lifespan management
app = FastAPI(
    title="Kaspa Node Dashboard API",
    description="API with persistent WebSocket connection and real-time event subscriptions",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,  # More secure
    allow_methods=["GET"],    # Only GET methods needed
    allow_headers=["*"],
)

# Include API routes
app.include_router(create_router())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info"
    )

 