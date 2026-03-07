"""
Sparkbot skill: currency_convert

Converts between currencies using the free Open Exchange Rates API (no key needed).
Falls back to exchangerate.host if the primary source is unavailable.
"""
import httpx

_PRIMARY_API = "https://open.er-api.com/v6/latest/{base}"
_FALLBACK_API = "https://api.exchangerate-api.com/v4/latest/{base}"

DEFINITION = {
    "type": "function",
    "function": {
        "name": "currency_convert",
        "description": (
            "Convert an amount from one currency to another using live exchange rates. "
            "Use for questions like 'how much is 100 USD in EUR', 'convert 500 GBP to JPY', "
            "or 'what is the EUR/USD rate'. Always call this for currency conversions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to convert (e.g. 100)",
                },
                "from_currency": {
                    "type": "string",
                    "description": "Source currency code (e.g. USD, EUR, GBP, JPY)",
                },
                "to_currency": {
                    "type": "string",
                    "description": "Target currency code (e.g. EUR, USD, CAD, BTC)",
                },
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    },
}

POLICY = {
    "scope": "read",
    "resource": "web",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    try:
        amount = float(args.get("amount") or 0)
    except (TypeError, ValueError):
        return "Error: amount must be a number."

    from_cur = (args.get("from_currency") or "").strip().upper()
    to_cur = (args.get("to_currency") or "").strip().upper()

    if not from_cur or not to_cur:
        return "Error: from_currency and to_currency are required."
    if amount == 0:
        return "Error: amount must be non-zero."

    for api_url in (_PRIMARY_API, _FALLBACK_API):
        try:
            url = api_url.format(base=from_cur)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            rates = data.get("rates", {})
            if not rates:
                continue

            rate = rates.get(to_cur)
            if rate is None:
                return f"Currency '{to_cur}' not found. Check the currency code."

            converted = amount * float(rate)
            rate_str = f"{float(rate):.6f}".rstrip("0").rstrip(".")
            return (
                f"💱 {amount:,.2f} {from_cur} = **{converted:,.4f} {to_cur}**\n"
                f"Rate: 1 {from_cur} = {rate_str} {to_cur}"
            )
        except Exception:
            continue

    return f"Could not fetch exchange rate for {from_cur} → {to_cur}. Try again later."
