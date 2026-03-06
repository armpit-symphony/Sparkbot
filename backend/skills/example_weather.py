"""
Example Sparkbot skill: get_weather

Drop any .py file in backend/skills/ and it auto-loads on next restart.
Uses the free wttr.in JSON API — no API key required.
"""
import httpx

DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get real-time current weather for a city or location. Always call this tool for weather questions — do not answer from training data.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location, e.g. 'London' or 'New York'",
                }
            },
            "required": ["location"],
        },
    },
}

# Optional — omit to get read/allow defaults
POLICY = {
    "scope": "read",
    "resource": "web",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    location = args.get("location", "").strip()
    if not location:
        return "Error: location is required."
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://wttr.in/{location}",
                params={"format": "j1"},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            d = r.json()["current_condition"][0]
            desc = d["weatherDesc"][0]["value"]
            return (
                f"Weather in {location}: {desc}, {d['temp_C']}°C / {d['temp_F']}°F "
                f"(feels like {d['FeelsLikeC']}°C), humidity {d['humidity']}%"
            )
    except Exception as exc:
        return f"Could not fetch weather for '{location}': {exc}"
