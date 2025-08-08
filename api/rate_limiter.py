"""
Simple in-memory rate limiter for API endpoints.
"""
import time
from typing import Dict, Optional
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

class RateLimiter:
    """Simple token bucket rate limiter."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_minute / 60
        self.buckets: Dict[str, Dict] = {}
        self.cleanup_interval = 300  # Clean up old entries every 5 minutes
        self.last_cleanup = time.time()
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # Use X-Forwarded-For if behind proxy, otherwise use client host
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return client_ip
    
    def _cleanup_old_buckets(self):
        """Remove old bucket entries to prevent memory growth."""
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            # Remove buckets not accessed in the last hour
            cutoff_time = current_time - 3600
            old_clients = [
                client for client, bucket in self.buckets.items()
                if bucket["last_access"] < cutoff_time
            ]
            for client in old_clients:
                del self.buckets[client]
            
            if old_clients:
                print(f"Cleaned up {len(old_clients)} old rate limit buckets")
            
            self.last_cleanup = current_time
    
    def check_rate_limit(self, request: Request) -> bool:
        """Check if request is within rate limit."""
        client_id = self._get_client_id(request)
        current_time = time.time()
        
        # Periodic cleanup
        self._cleanup_old_buckets()
        
        if client_id not in self.buckets:
            # Initialize bucket for new client
            self.buckets[client_id] = {
                "tokens": float(self.requests_per_minute),
                "last_refill": current_time,
                "last_access": current_time
            }
            return True
        
        bucket = self.buckets[client_id]
        
        # Calculate tokens to add based on time elapsed
        time_elapsed = current_time - bucket["last_refill"]
        tokens_to_add = time_elapsed * self.requests_per_second
        
        # Refill bucket (cap at max)
        bucket["tokens"] = min(
            bucket["tokens"] + tokens_to_add,
            float(self.requests_per_minute)
        )
        bucket["last_refill"] = current_time
        bucket["last_access"] = current_time
        
        # Check if we have tokens available
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        
        return False
    
    async def __call__(self, request: Request):
        """Middleware function for FastAPI."""
        if not self.check_rate_limit(request):
            # Calculate retry after time
            client_id = self._get_client_id(request)
            bucket = self.buckets.get(client_id, {})
            tokens_needed = 1 - bucket.get("tokens", 0)
            retry_after = int(tokens_needed / self.requests_per_second) + 1
            
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)}
            )

# Global rate limiter instance (60 requests per minute default)
rate_limiter = RateLimiter(requests_per_minute=60)

# More aggressive limiter for expensive endpoints
expensive_rate_limiter = RateLimiter(requests_per_minute=20)