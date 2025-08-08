"""
Error message sanitization for production environments.
"""
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ErrorSanitizer:
    """Sanitizes error messages to prevent information disclosure."""
    
    # Patterns that might reveal sensitive information
    SENSITIVE_PATTERNS = [
        (r'(ws://|wss://|http://|https://)[\w\.\-:]+', r'\1[REDACTED]'),  # URLs with credentials
        (r':\d{4,5}', ':[PORT]'),  # Port numbers
        (r'/[\w/\-\.]+/logs/[\w\-\.]+', '/[LOG_PATH]'),  # Log file paths
        (r'/home/[\w\-]+/', '/[USER_HOME]/'),  # User home directories
        (r'/Users/[\w\-]+/', '/[USER_HOME]/'),  # macOS user directories
        (r'[a-fA-F0-9]{64}', '[HASH]'),  # SHA256 hashes
        (r'[a-fA-F0-9]{40}', '[HASH]'),  # SHA1 hashes
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP_ADDRESS]'),  # IP addresses
        (r'kaspad-[\w\-]+', 'kaspad-[INSTANCE]'),  # Container names
        (r'api-[\w\-]+', 'api-[INSTANCE]'),  # API container names
    ]
    
    @classmethod
    def sanitize_error_message(cls, message: str, is_production: bool = True) -> str:
        """
        Sanitize error message for safe display.
        
        Args:
            message: The error message to sanitize
            is_production: Whether we're in production mode (more aggressive sanitization)
            
        Returns:
            Sanitized error message
        """
        if not is_production:
            # In development, return the original message
            return message
            
        if not message:
            return "An error occurred"
            
        sanitized = str(message)
        
        # Apply all sanitization patterns
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        
        # Remove any stack trace information
        if 'Traceback' in sanitized:
            sanitized = sanitized.split('Traceback')[0].strip()
            
        # Limit message length to prevent excessive logging
        if len(sanitized) > 500:
            sanitized = sanitized[:497] + "..."
            
        return sanitized
    
    @classmethod
    def sanitize_error_dict(cls, error_dict: Dict[str, Any], is_production: bool = True) -> Dict[str, Any]:
        """
        Sanitize error dictionary for API responses.
        
        Args:
            error_dict: Dictionary containing error information
            is_production: Whether we're in production mode
            
        Returns:
            Sanitized error dictionary
        """
        if not is_production:
            return error_dict
            
        sanitized = {}
        
        for key, value in error_dict.items():
            if key in ['traceback', 'stack_trace', 'exc_info']:
                # Skip sensitive debugging information in production
                continue
            elif key in ['error', 'message', 'detail']:
                # Sanitize error messages
                sanitized[key] = cls.sanitize_error_message(str(value), is_production)
            elif isinstance(value, str):
                # Sanitize string values
                sanitized[key] = cls.sanitize_error_message(value, is_production)
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = cls.sanitize_error_dict(value, is_production)
            else:
                # Keep other types as-is
                sanitized[key] = value
                
        return sanitized
    
    @classmethod
    def create_safe_error_response(cls, 
                                  error: Exception,
                                  status_code: int = 500,
                                  is_production: bool = True,
                                  context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a safe error response for API endpoints.
        
        Args:
            error: The exception that occurred
            status_code: HTTP status code
            is_production: Whether we're in production mode
            context: Additional context to include (will be sanitized)
            
        Returns:
            Safe error response dictionary
        """
        error_type = type(error).__name__
        
        # Map error types to user-friendly messages
        error_messages = {
            'ConnectionError': 'Connection to the service failed',
            'TimeoutError': 'Request timed out',
            'ValueError': 'Invalid request data',
            'KeyError': 'Required data not found',
            'FileNotFoundError': 'Required resource not found',
            'PermissionError': 'Permission denied',
            'asyncio.TimeoutError': 'Operation timed out',
            'aiohttp.ClientError': 'Network communication error',
        }
        
        # Get user-friendly message or use generic one
        if is_production:
            message = error_messages.get(error_type, 'An internal error occurred')
        else:
            message = cls.sanitize_error_message(str(error), is_production)
        
        response = {
            'error': True,
            'message': message,
            'status_code': status_code
        }
        
        # Add error type in development mode
        if not is_production:
            response['error_type'] = error_type
            response['details'] = str(error)
        
        # Add sanitized context if provided
        if context:
            response['context'] = cls.sanitize_error_dict(context, is_production)
            
        return response

# Global instance for easy access
sanitizer = ErrorSanitizer()