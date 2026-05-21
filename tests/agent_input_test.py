import contextlib
import io
import re
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Generator
from pathlib import Path

import httpx
import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_dentist import claude_dentist
from python_agent_input import agent_input

FETCH_TEMPERATURE = Path(__file__).parent / "fetch_temperature.py"
TIMEOUT = 2.0


@contextlib.contextmanager
def _advancement_timeout(msg: str) -> Generator[Callable[[], bool]]:
    deadline = time.monotonic() + TIMEOUT

    def poll() -> bool:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
        return True

    yield poll
    if time.monotonic() >= deadline:
        raise TimeoutError(msg)


class Session:
    def __init__(
        self,
        thread: threading.Thread,
        stdout: io.StringIO,
    ) -> None:
        self._thread = thread
        self._stdout = stdout
        self._curl_count = 0

    @property
    def stdout(self) -> str:
        return self._stdout.getvalue()

    def curl(self, value: str) -> None:
        self._curl_count += 1
        url = self._wait_for_curl_url(occurrence=self._curl_count)
        with httpx.Client() as client:
            client.post(url, json={"input": value})
        self._wait_for_script_to_advance()

    def _wait_for_curl_url(self, occurrence: int) -> str:
        with _advancement_timeout(
            f"Curl URL occurrence {occurrence} not found within {TIMEOUT}s"
        ) as poll:
            while poll():
                matches = re.findall(
                    r"curl -s -X POST (http://\S+)", self._stdout.getvalue()
                )
                if len(matches) >= occurrence:
                    return matches[occurrence - 1]
        msg = "unreachable"
        raise AssertionError(msg)

    def _wait_for_script_to_advance(self) -> None:
        expected = self._curl_count
        with _advancement_timeout("Script did not advance within timeout") as poll:
            while poll():
                if not self._thread.is_alive():
                    return
                if self._stdout.getvalue().count("Input received.") >= expected:
                    break
        time.sleep(0.5)


def _normalize_stdout(stdout: str) -> str:
    return re.sub(r"localhost:\d+", "localhost:PORT", stdout)


def run(script: Callable[[], object]) -> Session:
    stdout_capture = io.StringIO()

    def target() -> None:
        old_stdout = sys.stdout
        sys.stdout = stdout_capture
        try:
            script()
        finally:
            sys.stdout = old_stdout

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return Session(thread, stdout_capture)


def test_confirms_input_received() -> None:
    def script() -> None:
        agent_input("What is your name?")

    session = run(script)
    session.curl("Alice")

    assert "Input received." in session.stdout


def test_inputs_string() -> None:
    def script() -> None:
        name = agent_input("What is your name?")
        print(f"Hello, {name}!")

    session = run(script)
    session.curl("Alice")

    assert "Hello, Alice!" in session.stdout


def test_blocks_until_response() -> None:
    def script() -> None:
        name = agent_input("What is your name?")
        print(f"Hello, {name}!")
        answer = agent_input("What's 2+2?", validate=int)
        print(f"The answer is {answer}")

    session = run(script)
    session.curl("Alice")

    assert "Hello, Alice!" in session.stdout
    assert "The answer is" not in session.stdout

    session.curl("4")

    assert "The answer is 4" in session.stdout


def test_prints_prompt_to_stdout() -> None:
    def script() -> None:
        agent_input("What is your name?")

    session = run(script)
    session.curl("Alice")

    assert "What is your name?" in session.stdout


def test_prints_usage_instructions() -> None:
    def script() -> None:
        agent_input("Say something")

    session = run(script)
    session.curl("hi")

    output = _normalize_stdout(session.stdout)
    assert (
        "curl -s -X POST http://localhost:PORT/respond"
        """ -H 'Content-Type: application/json'"""
        """ -d '{"input": "your input here"}'"""
    ) in output


def test_prints_custom_example_response() -> None:
    def script() -> None:
        agent_input("What's 2+2?", example_response="4")

    session = run(script)
    session.curl("4")

    output = _normalize_stdout(session.stdout)
    assert """-d '{"input": "4"}'""" in output


def test_validate_returns_transformed_value() -> None:
    def script() -> None:
        answer = agent_input("What's 2+2?", validate=int)
        print(f"Doubled: {answer * 2}")

    session = run(script)
    session.curl("4")

    assert "Doubled: 8" in session.stdout


def test_retries_on_validation_failure() -> None:
    def script() -> None:
        answer = agent_input("What's 2+2?", validate=int)
        print(f"The answer is {answer}")

    session = run(script)
    session.curl("not a number")
    session.curl("4")

    assert "The answer is 4" in session.stdout


def test_displays_validation_error() -> None:
    def script() -> None:
        agent_input("What's 2+2?", validate=int)

    session = run(script)
    session.curl("abc")
    session.curl("4")

    output = _normalize_stdout(session.stdout)
    assert output.strip() == textwrap.dedent("""\
        [python-agent-input]
        The running script is waiting for your input:

          What's 2+2?

        To respond:
          curl -s -X POST http://localhost:PORT/respond -H 'Content-Type: application/json' -d '{"input": "your input here"}'

        [python-agent-input]
        Input received. However, your input failed validation checks.

        Validation failure message:
        ```
        invalid literal for int() with base 10: 'abc'
        ```

        Please try again. To respond:
          curl -s -X POST http://localhost:PORT/respond -H 'Content-Type: application/json' -d '{"input": "your input here"}'

        [python-agent-input]
        Input received.""")


@pytest.mark.agent_experience
@pytest.mark.anyio
async def test_agent_experience() -> None:
    await claude_dentist(
        runs=10,
        min_passes=9,
        prompt=textwrap.dedent(f"""\
            Always run {FETCH_TEMPERATURE} in the background with
            `uv run python {FETCH_TEMPERATURE}`, then use TaskOutput
            with block=false to check its stdout.

            Your task is to run {FETCH_TEMPERATURE.name} and complete it
            by responding to each prompt it gives you. Do not read any
            other files in this project.
        """),
        max_turns=15,
        deadline_seconds=300,
        options=ClaudeAgentOptions(
            allowed_tools=["Bash"],
            disallowed_tools=["Read", "Edit", "Write", "Glob", "Grep"],
            cwd=str(FETCH_TEMPERATURE.parent.parent),
        ),
    )
