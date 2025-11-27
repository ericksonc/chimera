"""FastAPI backend for Chimera v4 Multi-Agent System.

Provides streaming chat endpoint using Vercel AI SDK Stream Protocol (VSP).
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

# Load environment variables
load_dotenv()

# Setup logging
LOG_DIR = Path(__file__).parent
LOG_FILE = LOG_DIR / "requests.log"

# Configure file logger for requests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),  # Also log to console
    ],
)
logger = logging.getLogger(__name__)


# FastAPI app with lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Chimera backend server")

    # Initialize model registry (warm cache)
    try:
        from chimera_core.models import initialize_registry

        model_count = await initialize_registry()
        print(f"Model registry initialized with {model_count} models")
    except Exception as e:
        print(f"Warning: Model registry initialization failed: {e}")
        # Non-fatal - API will work without pre-cached models

    yield

    # Shutdown
    print("Shutting down Chimera backend server")

    # Close cache connections
    try:
        from chimera_core.cache.redis_client import close_cache_client

        await close_cache_client()
    except Exception:
        pass


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
        content={"detail": error_details, "body": "See server logs for request body"},
    )


# Exception handler for Pydantic validation errors
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Log and return detailed validation errors."""
    error_details = exc.errors()
    logger.error(f"Pydantic Validation Error: {json.dumps(error_details, indent=2)}")
    return JSONResponse(
        status_code=422,
        content={"detail": error_details, "body": "See server logs for request body"},
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
    if hasattr(exc, "errors"):
        try:
            logger.error(f"Error details: {json.dumps(exc.errors(), indent=2)}")
        except Exception:
            pass

    return JSONResponse(
        status_code=500,
        content={
            "error_type": f"{exc_module}.{exc_type}",
            "message": str(exc),
            "detail": "See server logs for full details",
        },
    )


# Middleware to log all requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests to file (headers and metadata only)."""
    # Log to file (don't consume body - it breaks FastAPI validation)
    logger.info(f"\n{'=' * 80}")
    logger.info(f"Request: {request.method} {request.url.path}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Content-Length: {request.headers.get('content-length', 'unknown')}")
    logger.info(f"{'=' * 80}\n")

    response = await call_next(request)
    return response


from typing import Any, Dict, List, Literal  # noqa: E402

# Import user input types from core (single source of truth)
from chimera_core.types import UserInput, UserInputMessage  # noqa: E402


class StreamRequest(BaseModel):
    """Request model for /stream endpoint.

    Client sends full ThreadProtocol history plus new user input.
    Server reconstructs state and streams VSP events back.

    user_input can be either:
    - UserInputMessage: Standard user message (kind="message")
    - UserInputDeferredTools: Deferred tool approvals/results (kind="deferred_tools")
    - str: Convenience - automatically converted to UserInputMessage
    """

    thread_protocol: List[Dict[str, Any]] = Field(
        ...,
        description="Array of ThreadProtocol event objects (JSONL lines as dicts). "
        "First line must be thread_blueprint event.",
    )
    user_input: UserInput = Field(
        ..., description="User input - either a message or deferred tool results"
    )

    @field_validator("user_input", mode="before")
    @classmethod
    def convert_str_to_message(cls, v):
        """Convert string input to UserInputMessage for convenience."""
        if isinstance(v, str):
            return UserInputMessage(kind="message", content=v)
        return v

    class Config:
        # Allow arbitrary types in dict values
        arbitrary_types_allowed = True


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Chimera v4 backend is running"}


@app.post("/debug")
async def debug_endpoint(request: Request):
    """Raw debug endpoint to see what's actually being sent."""
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        body_json = json.loads(body_str)
        logger.info("DEBUG - Parsed JSON successfully")
        logger.info(f"DEBUG - Keys: {list(body_json.keys())}")
        logger.info(
            f"DEBUG - Types: thread_protocol={type(body_json.get('thread_protocol'))}, user_input={type(body_json.get('user_input'))}"
        )

        # Try to manually validate with our model
        try:
            StreamRequest(**body_json)
            logger.info("DEBUG - Manual validation SUCCESS")
            return {"status": "Would work!", "data": body_json}
        except Exception as e:
            logger.error(f"DEBUG - Manual validation FAILED: {e}")
            return {"status": "Validation failed", "error": str(e), "type": type(e).__name__}

    except json.JSONDecodeError as e:
        logger.error(f"DEBUG - JSON parse failed: {e}")
        return {"status": "Invalid JSON", "error": str(e)}


class HaltRequest(BaseModel):
    """Request model for /halt endpoint."""

    thread_id: str = Field(..., description="Thread ID to halt/cancel")


@app.post("/halt")
async def halt_execution(request: HaltRequest):
    """
    Halt/cancel an active thread execution.

    When the user clicks the stop button, the client calls this endpoint
    to cancel the running thread task. This will:
    1. Cancel the asyncio task running the thread
    2. Stop active LLM inference (Pydantic AI handles this when task is cancelled)
    3. Emit error event to client with "Execution halted by user" message

    Returns:
        JSON response indicating success or failure
    """
    from .stream_handler import task_registry

    thread_id = request.thread_id

    # Try to cancel the task
    cancelled = await task_registry.cancel(thread_id)

    if cancelled:
        logger.info(f"[HALT] Successfully cancelled thread {thread_id}")
        return {"status": "cancelled", "thread_id": thread_id, "message": "Thread execution halted"}
    else:
        # Task not found or already completed
        logger.warning(f"[HALT] Thread {thread_id} not found or already completed")
        return {
            "status": "not_found",
            "thread_id": thread_id,
            "message": "Thread not active or already completed",
        }


@app.post("/stream")
async def stream_chat(stream_request: StreamRequest, raw_request: Request):
    """
    Streaming chat endpoint using Server-Sent Events.
    Follows Vercel AI SDK Stream Protocol.

    Expects ThreadProtocol JSONL from client (stateless paradigm).
    """
    # TEMPORARY LOGGING - Dump entire request to temp_requests.log
    temp_log_path = Path(__file__).parent / "temp_requests.log"

    # Log the validated request (already parsed by FastAPI)
    with open(temp_log_path, "a") as f:
        f.write(f"\n{'=' * 80}\n")
        f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")
        f.write(f"METHOD: {raw_request.method}\n")
        f.write(f"URL: {raw_request.url}\n")
        f.write(f"HEADERS:\n{json.dumps(dict(raw_request.headers), indent=2)}\n")
        f.write("VALIDATED REQUEST:\n")
        f.write(f"  user_input type: {type(stream_request.user_input)}\n")
        f.write(f"  user_input: {stream_request.user_input}\n")
        f.write(f"  thread_protocol length: {len(stream_request.thread_protocol)}\n")
        if stream_request.thread_protocol:
            f.write("  Last 3 events in thread_protocol:\n")
            for event in stream_request.thread_protocol[-3:]:
                f.write(f"    {event.get('type')}: {event}\n")
        f.write(f"{'=' * 80}\n\n")

    # Use the validated request
    request = stream_request

    try:
        # Import here to avoid circular dependency at module level
        from .stream_handler import generate_vsp

        # Extract ThreadProtocol and user input from validated request
        thread_jsonl = request.thread_protocol
        # Pass typed UserInput model directly (discriminated union: UserInputMessage | UserInputDeferredTools)
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
                "x-vercel-ai-ui-message-stream": "v1",  # Required for Vercel AI SDK
            },
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid request format. Error: {str(e)}")


# ============================================================================
# Multi-Thread Streaming Endpoint
# ============================================================================

from chimera_api.transports.multi_thread import MultiThreadChatRequest, handle_multi_thread_chat  # noqa: E402, I001


@app.post("/api/chat/threads")
async def multi_thread_chat(request: MultiThreadChatRequest):
    """
    Multi-thread streaming endpoint.

    Accepts multiple thread IDs and streams their concurrent execution.
    Each thread receives the same user input and executes independently.
    Events are multiplexed with round-robin interleaving and annotated
    with thread_id for client-side demultiplexing.

    This enables the frontend to display multiple concurrent conversations
    through a single HTTP connection, improving efficiency and enabling
    server-side coordination.

    Request format:
    {
        "thread_ids": ["thread-1", "thread-2"],
        "messages": [{"role": "user", "content": "Hello"}],
        "user_input": {
            "type": "message",
            "message": {"role": "user", "content": "Hello"}
        }
    }

    Returns:
        EventSourceResponse with multiplexed SSE stream containing
        thread_id annotations on all events
    """
    return await handle_multi_thread_chat(request)


# ============================================================================
# Utility Endpoint - Stateless single-shot LLM utilities
# ============================================================================


class UtilRequest(BaseModel):
    """Request model for /util endpoint.

    Provides stateless, single-shot LLM utilities like title generation,
    tag suggestions, grammar checks, etc.
    """

    task: Literal["generate_title"] = Field(..., description="The utility task to perform")
    model: str = Field(
        default="meta-llama/llama-4-scout",
        description="Model to use (default: fast Llama 4 Scout for simple tasks)",
    )
    input: Dict[str, Any] = Field(..., description="Task-specific input data")


class UtilResponse(BaseModel):
    """Response model for /util endpoint."""

    result: str = Field(..., description="The utility result")
    model_used: str = Field(..., description="Model that was used")


@app.post("/util")
async def util_query(request: UtilRequest) -> UtilResponse:
    """Stateless single-shot LLM utilities.

    Examples:
    - generate_title: Create a conversation title from user's first message

    This endpoint is for simple, one-off LLM queries that don't require
    conversation history or complex orchestration. For multi-turn conversations,
    use /stream instead.
    """
    try:
        # Import here to avoid issues if not needed
        from pydantic_ai import Agent

        from chimera_core.models import create_model

        # Create the model
        model = create_model(request.model)
        agent = Agent(model)

        # Task dispatch
        if request.task == "generate_title":
            # Extract user prompt from input
            user_prompt = request.input.get("user_prompt")
            if not user_prompt:
                raise HTTPException(
                    status_code=400, detail="generate_title requires 'user_prompt' in input"
                )

            # Create a prompt for title generation
            prompt = f"""Generate a concise, descriptive title (3-6 words) for a conversation that begins with this user message:

"{user_prompt}"

Return ONLY the title text, no quotes or explanation."""

            # Run the agent
            result = await agent.run(prompt)

            return UtilResponse(result=result.output.strip(), model_used=request.model)

        # Future tasks would go here
        # elif request.task == "suggest_tags":
        #     ...

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Util query error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Utility processing failed: {str(e)}")


# ============================================================================
# Model Registry Endpoints
# ============================================================================

from typing import Optional  # noqa: E402

from chimera_core.models import ModelMetadata, Provider, get_registry_service  # noqa: E402
from chimera_core.models.registry import ModelListResponse, ModelsByCapabilityResponse  # noqa: E402


@app.get("/api/v1/models", response_model=ModelListResponse)
async def list_models(
    provider: Optional[str] = None,
    capability: Optional[str] = None,
):
    """List all available models.

    Optionally filter by provider or capability.

    Query params:
        provider: Filter by provider (openrouter, gemini, kimi)
        capability: Filter by capability (e.g., image_input, function_calling)

    Returns:
        ModelListResponse with models list and metadata
    """
    service = get_registry_service()

    if capability:
        models = await service.get_models_by_capability(capability)
    elif provider:
        try:
            provider_enum = Provider(provider.lower())
            models = await service.get_models_by_provider(provider_enum)
        except ValueError:
            models = []
    else:
        models = await service.get_all_models()

    return ModelListResponse(
        models=models,
        total=len(models),
        cached_at=service._last_refresh,
    )


@app.get("/api/v1/models/capabilities")
async def list_models_by_capability(capability: str) -> ModelsByCapabilityResponse:
    """Get models that support a specific capability.

    Path params:
        capability: Capability name (e.g., image_input, function_calling, streaming)

    Returns:
        ModelsByCapabilityResponse with matching models
    """
    service = get_registry_service()
    models = await service.get_models_by_capability(capability)

    return ModelsByCapabilityResponse(
        capability=capability,
        models=models,
        total=len(models),
    )


@app.get("/api/v1/models/{model_id:path}", response_model=Optional[ModelMetadata])
async def get_model(model_id: str):
    """Get metadata for a specific model.

    Path params:
        model_id: Model identifier (e.g., "openrouter:anthropic/claude-3.5-sonnet"
                  or "anthropic/claude-3.5-sonnet")

    Returns:
        ModelMetadata if found, 404 if not found
    """
    service = get_registry_service()
    model = await service.get_model(model_id)

    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    return model


@app.post("/api/v1/models/refresh")
async def refresh_models():
    """Force refresh the model registry cache.

    Admin endpoint to manually trigger cache refresh.
    Useful when new models are deployed.

    Returns:
        Number of models fetched

    TODO: Add authentication/authorization and rate limiting before production.
          This endpoint could be abused for DoS if left unprotected.
    """
    service = get_registry_service()
    count = await service.refresh_cache()
    return {"status": "refreshed", "model_count": count}


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Chimera v4 Backend API")
    parser.add_argument(
        "--port", type=int, default=33003, help="Port to run the server on (default: 33003)"
    )
    parser.add_argument(
        "--embedded",
        action="store_true",
        help="Running as embedded desktop backend (optional flag for future use)",
    )

    args = parser.parse_args()

    logger.info(f"Starting Chimera backend on port {args.port}")
    if args.embedded:
        logger.info("Running in embedded desktop mode")

    uvicorn.run(app, host="0.0.0.0", port=args.port)
