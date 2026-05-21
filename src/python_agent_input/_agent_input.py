import socket
import threading
import time
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI
from pl_mocks_and_fakes import MockInUnitTests, MockReason
from pydantic import BaseModel


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _curl_snippet(port: int, example_response: str | None) -> str:
    url = f"http://localhost:{port}/respond"
    example = example_response or "your input here"
    return (
        f"  curl -s -X POST {url}"
        f""" -H 'Content-Type: application/json' -d '{{"input": "{example}"}}'"""
    )


def _format_prompt(
    port: int,
    prompt: str,
    example_response: str | None,
) -> str:
    parts = [
        "\n[python-agent-input]",
        "The running script is waiting for your input:",
        f"\n  {prompt}",
        f"\nTo respond:\n{_curl_snippet(port, example_response)}",
    ]
    return "\n".join(parts)


def _format_validation_error(
    port: int,
    example_response: str | None,
    error: str,
) -> str:
    parts = [
        "\n[python-agent-input]",
        "Input received. However, your input failed validation checks.",
        f"\nValidation failure message:\n```\n{error}\n```",
        f"\nPlease try again. To respond:\n{_curl_snippet(port, example_response)}",
    ]
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


@MockInUnitTests(MockReason.UNMITIGATED_SIDE_EFFECT)
def agent_input[T](
    prompt: str,
    *,
    example_response: str | None = None,
    validate: Callable[[str], T] = str,
) -> T:
    response_holder: str | None = None
    app = FastAPI()

    @app.post("/respond")
    async def respond(body: _RespondBody) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        nonlocal response_holder
        response_holder = body.input
        return {"status": "ok"}

    port, server, thread = _start_server(app)

    print(
        _format_prompt(port, prompt, example_response),
        flush=True,
    )

    while True:
        while response_holder is None:
            time.sleep(0.01)
        try:
            result = validate(response_holder)
            break
        except Exception as e:
            response_holder = None
            print(
                _format_validation_error(port, example_response, error=str(e)),
                flush=True,
            )

    print("\n[python-agent-input]\nInput received.\n", flush=True)
    server.should_exit = True
    thread.join()
    return result
