"""
Kaspa Node Dashboard API Server

Refactored modular FastAPI application for monitoring Kaspa nodes.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import our modular components
from config import API_HOST, API_PORT, KASPAD_HOST, KASPAD_RPC_PORT, KASPAD_CONTAINER_NAME, CORS_ORIGINS, SYNC_CHECK_INTERVAL_SYNCING, SYNC_CHECK_INTERVAL_SYNCED
from rpc_client import KaspadRPCClient
from services import KaspadService, SyncProgressService
from routes import create_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global services
rpc_client: KaspadRPCClient = None
kaspad_service: KaspadService = None
sync_service: SyncProgressService = None
background_task: asyncio.Task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan with proper startup/shutdown."""
    global rpc_client, kaspad_service, sync_service, background_task
    
    # Startup
    logger.info("Starting Kaspa Node Dashboard API")
    
    # Initialize RPC client with session management
    rpc_client = KaspadRPCClient(KASPAD_HOST, KASPAD_RPC_PORT)
    async with rpc_client:
        # Initialize services
        kaspad_service = KaspadService(rpc_client, KASPAD_CONTAINER_NAME)
        sync_service = SyncProgressService(rpc_client, kaspad_service, KASPAD_CONTAINER_NAME)
        
        # Start background sync monitoring
        background_task = asyncio.create_task(monitor_sync_progress())
        
        yield
    
    # Shutdown
    logger.info("Shutting down Kaspa Node Dashboard API")
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass

# Create FastAPI app with lifespan management
app = FastAPI(
    title="Kaspa Node Dashboard API",
    description="API for monitoring Kaspa node status and sync progress",
    version="1.0.0",
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

async def monitor_sync_progress():
    """Background task to monitor kaspad sync progress."""
    global sync_service
    logger.info("Starting sync progress monitor")
    
    while True:
        try:
            await sync_service.update_sync_progress()
            current_progress = sync_service.get_current_progress()
            
            # Log progress updates
            if current_progress["is_syncing"]:
                logger.info(
                    f"Sync progress: {current_progress['percentage']}% - "
                    f"{current_progress['phase']} ({current_progress.get('sub_phase', 'N/A')})"
                )
                await asyncio.sleep(SYNC_CHECK_INTERVAL_SYNCING)
            else:
                logger.info("Kaspad is fully synced and ready")
                await asyncio.sleep(SYNC_CHECK_INTERVAL_SYNCED)
                
        except Exception as e:
            logger.warning(f"Error in sync progress monitor: {e}")
            await asyncio.sleep(SYNC_CHECK_INTERVAL_SYNCING)

# Include API routes
app.include_router(create_router())
            
def get_services():
    """Get initialized services for dependency injection."""
    return {
        "rpc_client": rpc_client,
        "kaspad_service": kaspad_service,
        "sync_service": sync_service
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info"
    )

 