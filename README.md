[![PyPI version](https://img.shields.io/pypi/v/python-agent-input)](https://pypi.org/project/python-agent-input/)
[![Python versions](https://img.shields.io/pypi/pyversions/python-agent-input)](https://pypi.org/project/python-agent-input/)
[![License](https://img.shields.io/pypi/l/python-agent-input)](./LICENSE)
[![Claude Dentist Rating](https://img.shields.io/badge/Claude%20Dentist%20Rating-10%2F10-blue)](https://github.com/Peter-Lavigne/claude-dentist)

# python-agent-input

`input()` for Claude Code agents.

Claude Code hangs on `input()` because it cannot write to stdin. `agent_input()` replaces `input()` with an HTTP server — it prints curl instructions to stdout and blocks until the agent responds.

**Important:** Since `agent_input()` blocks, the agent must run the script in the background with Bash, then use the `TaskOutput` tool with `block=false` to check its stdout for curl instructions.

## Usage

```python
from python_agent_input import agent_input

name = agent_input("What is your name?")
print(f"Hello, {name}!")
```

### Input validation

```python
from python_agent_input import agent_input


def celsius_or_kelvin(value: str) -> str:
    if value not in ("Celsius", "Kelvin"):
        raise ValueError(f"Expected 'Celsius' or 'Kelvin', got '{value}'")
    return value


temp = agent_input("Temperature in Fahrenheit?", example_response="72", validate=int)
unit = agent_input("Convert to Celsius or Kelvin?", validate=celsius_or_kelvin)

if unit == "Celsius":
    print(f"{(temp - 32) * 5 / 9:.1f}°C")
else:
    print(f"{(temp - 32) * 5 / 9 + 273.15:.1f}K")
```
