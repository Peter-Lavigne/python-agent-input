from python_agent_input import agent_input


def fahrenheit_or_celsius(value: str) -> str:
    if value not in ("Fahrenheit", "Celsius"):
        msg = f"Expected 'Fahrenheit' or 'Celsius', got '{value}'"
        raise ValueError(msg)
    return value


city = agent_input("What city should we get weather for?", example_response="Paris")
unit = agent_input(
    "Fahrenheit or Celsius?",
    example_response="Celsius",
    validate=fahrenheit_or_celsius,
)

temperatures = {"Fahrenheit": "72°F", "Celsius": "22°C"}
print(f"Current temperature in {city}: {temperatures[unit]}")
