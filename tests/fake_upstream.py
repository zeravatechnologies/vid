"""A fake model for tests: OpenAI-compatible and Anthropic formats, streaming
included, with a fixed delay between streamed pieces so tests can tell a
relayed stream from a buffered one."""

from __future__ import annotations

import asyncio
import json
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

PIECES = ["Hello", ", ", "Vid", "!"]
STREAM_DELAY_S = 0.25
# A harmless, obviously-fake key shape, to test that Vid shows leaks in a reply.
FAKE_SECRET = "sk-ant-" + "A" * 28
LEAK_PIECES = ["Sure, the key is ", FAKE_SECRET, " — keep it safe."]


def pieces_for(data: dict) -> list:
    return LEAK_PIECES if data.get("model") == "leak-key" else PIECES


class Recorder:
    def __init__(self):
        self.requests: list[dict] = []

    def last(self) -> dict:
        return self.requests[-1]


def build_fake(recorder: Recorder) -> Starlette:
    async def remember(request: Request) -> dict:
        body = await request.body()
        recorder.requests.append({"path": request.url.path, "headers": dict(request.headers), "body": body})
        return json.loads(body) if body else {}

    async def models(request: Request):
        await remember(request)
        return JSONResponse({"object": "list", "data": [{"id": "fake-1", "object": "model", "created": 0, "owned_by": "test"}]})

    async def chat(request: Request):
        data = await remember(request)
        if data.get("model") == "fail-500":
            return JSONResponse({"error": {"message": "upstream exploded", "type": "server_error"}}, status_code=500)
        pieces = pieces_for(data)
        text = "".join(pieces)
        if not data.get("stream"):
            return JSONResponse({
                "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": data["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            })

        async def events():
            for i, piece in enumerate(pieces):
                chunk = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 0, "model": data["model"],
                         "choices": [{"index": 0, "delta": ({"role": "assistant", "content": piece} if i == 0 else {"content": piece}), "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(STREAM_DELAY_S)
            end = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 0, "model": data["model"],
                   "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(end)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    async def messages(request: Request):
        data = await remember(request)
        pieces = pieces_for(data)
        text = "".join(pieces)
        if not data.get("stream"):
            return JSONResponse({
                "id": "msg_1", "type": "message", "role": "assistant", "model": data["model"],
                "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 3, "output_tokens": 4},
            })

        def ev(name: str, payload: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(payload)}\n\n"

        async def events():
            yield ev("message_start", {"type": "message_start", "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": data["model"], "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 3, "output_tokens": 0}}})
            yield ev("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
            for piece in pieces:
                yield ev("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": piece}})
                await asyncio.sleep(STREAM_DELAY_S)
            yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
            yield ev("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 4}})
            yield ev("message_stop", {"type": "message_stop"})

        return StreamingResponse(events(), media_type="text/event-stream")

    return Starlette(routes=[
        Route("/v1/models", models, methods=["GET"]),
        Route("/v1/chat/completions", chat, methods=["POST"]),
        Route("/v1/messages", messages, methods=["POST"]),
    ])
