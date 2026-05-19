import socket
import threading
import time
from collections.abc import Callable
from typing import overload

import uvicorn
from fastapi import FastAPI
from pl_mocks_and_fakes import MockInUnitTests, MockReason
from pydantic import BaseModel


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _format_message(
    port: int,
    prompt: str,
    example_response: str | None,
    error: str | None = None,
) -> str:
    url = f"http://localhost:{port}/respond"
    example = example_response or "your input here"
    parts = [
        "\n[python-agent-input]",
        "The running script is waiting for your input:",
        f"\n  {prompt}",
    ]
    if error:
        parts.append(f"\nYour previous input was invalid: {error}")
    parts.append(
        f"\nTo respond:\n"
        f"  curl -s -X POST {url}"
        f""" -H 'Content-Type: application/json' -d '{{"input": "{example}"}}'"""
    )
    return "\n".join(parts)


class _RespondBody(BaseModel):
    input: str


def _start_server(app: FastAPI) -> tuple[int, uvicorn.Server, threading.Thread]:
    port = _find_open_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():  # pragma: no cover
            msg = f"Server failed to start on port {port}"
            raise OSError(msg)
        time.sleep(0.01)
    return port, server, thread


@overload
def agent_input(
    prompt: str,
    *,
    example_response: str | None = None,
) -> str: ...


@overload
def agent_input[T](
    prompt: str,
    *,
    example_response: str | None = None,
    validate: Callable[[str], T],
) -> T: ...


@MockInUnitTests(MockReason.UNMITIGATED_SIDE_EFFECT)
def agent_input[T](
    prompt: str,
    *,
    example_response: str | None = None,
    validate: Callable[[str], T] | None = None,
) -> str | T:
    response_holder: dict[str, str] = {}
    app = FastAPI()

    @app.post("/respond")
    async def respond(body: _RespondBody) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        response_holder["value"] = body.input
        return {"status": "ok"}

    port, server, thread = _start_server(app)

    print(
        _format_message(port, prompt, example_response),
        flush=True,
    )

    while True:
        while "value" not in response_holder:
            time.sleep(0.01)
        raw = response_holder.pop("value")
        if validate is None:
            server.should_exit = True
            thread.join()
            return raw
        try:
            result = validate(raw)
        except Exception as e:
            print(
                _format_message(port, prompt, example_response, error=str(e)),
                flush=True,
            )
        else:
            server.should_exit = True
            thread.join()
            return result
