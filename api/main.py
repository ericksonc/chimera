"""FastAPI backend for Chimera v4 Multi-Agent System.

Provides streaming chat endpoint using Vercel AI SDK Stream Protocol (VSP).
"""

import json
import logging
from typing import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
LOG_DIR = Path(__file__).parent
LOG_FILE = LOG_DIR / "requests.log"

# Configure file logger for requests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger(__name__)


# FastAPI app with lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Chimera backend server")
    yield
    # Shutdown
    print("Shutting down Chimera backend server")


app = FastAPI(title="Chimera v4 Backend", lifespan=lifespan)

# Add CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler for FastAPI request validation errors
@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log and return detailed request validation errors."""
    error_details = exc.errors()
    logger.error(f"Request Validation Error: {json.dumps(error_details, indent=2)}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": error_details,
            "body": "See server logs for request body"
        }
    )


# Exception handler for Pydantic validation errors
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Log and return detailed validation errors."""
    error_details = exc.errors()
    logger.error(f"Pydantic Validation Error: {json.dumps(error_details, indent=2)}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": error_details,
            "body": "See server logs for request body"
        }
    )


# Catch-all exception handler to see what we're missing
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Log any unhandled exceptions with their type."""
    exc_type = type(exc).__name__
    exc_module = type(exc).__module__

    logger.error(f"Unhandled Exception Type: {exc_module}.{exc_type}")
    logger.error(f"Exception Message: {str(exc)}")
    logger.error(f"Exception Details: {repr(exc)}")

    # If it has errors() method (validation-like), log those too
    if hasattr(exc, 'errors'):
        try:
            logger.error(f"Error details: {json.dumps(exc.errors(), indent=2)}")
        except:
            pass

    return JSONResponse(
        status_code=500,
        content={
            "error_type": f"{exc_module}.{exc_type}",
            "message": str(exc),
            "detail": "See server logs for full details"
        }
    )


# Middleware to log all requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests to file (headers and metadata only)."""
    # Log to file (don't consume body - it breaks FastAPI validation)
    logger.info(f"\n{'='*80}")
    logger.info(f"Request: {request.method} {request.url.path}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Content-Length: {request.headers.get('content-length', 'unknown')}")
    logger.info(f"{'='*80}\n")

    response = await call_next(request)
    return response


from typing import List, Dict, Any

class StreamRequest(BaseModel):
    """Request model for /stream endpoint.

    Client sends full ThreadProtocol history plus new user input.
    Server reconstructs state and streams VSP events back.
    """
    thread_protocol: List[Dict[str, Any]] = Field(
        ...,
        description="Array of ThreadProtocol event objects (JSONL lines as dicts). "
                    "First line must be thread_blueprint event."
    )
    user_input: str = Field(..., description="New user message to process")

    class Config:
        # Allow arbitrary types in dict values
        arbitrary_types_allowed = True


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "Chimera v4 backend is running"
    }


@app.post("/debug")
async def debug_endpoint(request: Request):
    """Raw debug endpoint to see what's actually being sent."""
    body = await request.body()
    body_str = body.decode('utf-8')

    try:
        body_json = json.loads(body_str)
        logger.info(f"DEBUG - Parsed JSON successfully")
        logger.info(f"DEBUG - Keys: {list(body_json.keys())}")
        logger.info(f"DEBUG - Types: thread_protocol={type(body_json.get('thread_protocol'))}, user_input={type(body_json.get('user_input'))}")

        # Try to manually validate with our model
        try:
            validated = StreamRequest(**body_json)
            logger.info(f"DEBUG - Manual validation SUCCESS")
            return {"status": "Would work!", "data": body_json}
        except Exception as e:
            logger.error(f"DEBUG - Manual validation FAILED: {e}")
            return {"status": "Validation failed", "error": str(e), "type": type(e).__name__}

    except json.JSONDecodeError as e:
        logger.error(f"DEBUG - JSON parse failed: {e}")
        return {"status": "Invalid JSON", "error": str(e)}


@app.post("/stream")
async def stream_chat(request: StreamRequest):
    """
    Streaming chat endpoint using Server-Sent Events.
    Follows Vercel AI SDK Stream Protocol.

    Expects ThreadProtocol JSONL from client (stateless paradigm).
    """
    try:
        # Import here to avoid circular dependency at module level
        from .stream_handler import generate_vsp

        # Extract ThreadProtocol and user input from validated request
        thread_jsonl = request.thread_protocol
        user_input = request.user_input

        if not thread_jsonl:
            raise ValueError("thread_protocol cannot be empty")

        return StreamingResponse(
            generate_vsp(thread_jsonl, user_input),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "x-vercel-ai-ui-message-stream": "v1"  # Required for Vercel AI SDK
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid request format. Error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=33003)
