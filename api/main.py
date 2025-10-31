"""FastAPI backend for Chimera v4 Multi-Agent System.

Provides streaming chat endpoint using Vercel AI SDK Stream Protocol (VSP).
"""

import json
from typing import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "Chimera v4 backend is running"
    }


@app.post("/stream")
async def stream_chat(request: dict):
    """
    Streaming chat endpoint using Server-Sent Events.
    Follows Vercel AI SDK Stream Protocol.

    Expects ThreadProtocol JSONL from client (stateless paradigm).
    """
    try:
        # Import here to avoid circular dependency at module level
        from api.stream_handler import generate_vsp

        # Extract ThreadProtocol and user input
        thread_jsonl = request.get("thread_protocol", [])
        user_input = request.get("user_input", "")

        if not thread_jsonl:
            raise ValueError("thread_protocol is required")

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
