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


# Request/Response models
class Message(BaseModel):
    role: str
    content: str


class StreamRequest(BaseModel):
    messages: list[Message]


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


async def generate_vsp(messages: list[Message]) -> AsyncIterator[str]:
    """
    Generate SSE stream following Vercel AI SDK Stream Protocol.

    TODO: Implement actual Pydantic AI integration with ThreadProtocol v0.0.5
    - Use agent.iter() to stream events
    - Convert Pydantic AI events to VSP format
    - Write events to ThreadProtocol JSONL
    - Include data-app-chimera mutation events

    For now, this is just a stub.
    """
    # Stub implementation - just yield a simple message
    yield f'data: {json.dumps({"type": "start", "messageId": "stub-msg-001"})}\n\n'
    yield f'data: {json.dumps({"type": "text-start", "id": "stub-text-001"})}\n\n'
    yield f'data: {json.dumps({"type": "text-delta", "id": "stub-text-001", "delta": "This is a stub response. "})}\n\n'
    yield f'data: {json.dumps({"type": "text-delta", "id": "stub-text-001", "delta": "Actual implementation coming soon."})}\n\n'
    yield f'data: {json.dumps({"type": "text-end", "id": "stub-text-001"})}\n\n'
    yield f'data: {json.dumps({"type": "finish"})}\n\n'
    yield 'data: [DONE]\n\n'


@app.post("/stream")
async def stream_chat(request: dict):
    """
    Streaming chat endpoint using Server-Sent Events.
    Follows Vercel AI SDK Stream Protocol.
    """
    try:
        # Parse request
        stream_request = StreamRequest(**request)

        return StreamingResponse(
            generate_vsp(stream_request.messages),
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
            detail=f"Invalid request format. Expected: {{'messages': [...]}}. Error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=33003)
