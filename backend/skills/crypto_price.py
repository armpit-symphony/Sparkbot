"""
Sparkbot skill: crypto_price

Fetches real-time cryptocurrency prices via the CoinGecko public API.
No API key required — completely free tier.
"""
import httpx

_COINGECKO_API = "https://api.coingecko.com/api/v3"

# Common name → CoinGecko ID mapping for popular coins
_COIN_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "avax": "avalanche-2",
    "dot": "polkadot",
    "link": "chainlink",
    "matic": "matic-network",
    "doge": "dogecoin",
    "shib": "shiba-inu",
    "ltc": "litecoin",
    "uni": "uniswap",
    "atom": "cosmos",
    "near": "near",
    "algo": "algorand",
    "xlm": "stellar",
    "fil": "filecoin",
    "icp": "internet-computer",
}

DEFINITION = {
    "type": "function",
    "function": {
        "name": "crypto_price",
        "description": (
            "Get real-time cryptocurrency prices and market data from CoinGecko. "
            "Use for questions like 'what is Bitcoin worth', 'ETH price', "
            "'crypto prices', or 'how is Solana doing'. "
            "Always call this for crypto questions — do not use training-data prices."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "coins": {
                    "type": "string",
                    "description": (
                        "Comma-separated coin names or tickers to look up, "
                        "e.g. 'bitcoin,ethereum' or 'btc,eth,sol'. "
                        "Default: bitcoin,ethereum,solana"
                    ),
                },
                "vs_currency": {
                    "type": "string",
                    "description": "Quote currency (default: usd). E.g. usd, eur, gbp, btc.",
                },
            },
            "required": [],
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


def _resolve_id(name: str) -> str:
    """Map ticker/alias → CoinGecko ID, fall back to the raw name."""
    cleaned = name.strip().lower()
    return _COIN_ALIASES.get(cleaned, cleaned)


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    raw_coins = (args.get("coins") or "bitcoin,ethereum,solana").strip()
    vs_currency = (args.get("vs_currency") or "usd").strip().lower()

    coin_ids = [_resolve_id(c) for c in raw_coins.split(",") if c.strip()]
    if not coin_ids:
        return "Error: no coins specified."

    ids_param = ",".join(coin_ids)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Price + 24h change
            resp = await client.get(
                f"{_COINGECKO_API}/simple/price",
                params={
                    "ids": ids_param,
                    "vs_currencies": vs_currency,
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        if not data:
            return f"No price data found for: {raw_coins}"

        lines = [f"🪙 Crypto Prices (vs {vs_currency.upper()}):"]
        for coin_id in coin_ids:
            coin_data = data.get(coin_id)
            if not coin_data:
                lines.append(f"• {coin_id}: not found")
                continue
            price = coin_data.get(vs_currency)
            change = coin_data.get(f"{vs_currency}_24h_change")
            mcap = coin_data.get(f"{vs_currency}_market_cap")

            # Format price: show more decimals for sub-$1 coins
            if price is not None and price < 1:
                price_str = f"{price:.6f}"
            elif price is not None:
                price_str = f"{price:,.2f}"
            else:
                price_str = "N/A"

            change_str = ""
            if change is not None:
                arrow = "▲" if change >= 0 else "▼"
                change_str = f"  {arrow} {abs(change):.2f}% (24h)"

            mcap_str = ""
            if mcap:
                if mcap >= 1_000_000_000:
                    mcap_str = f"  Mkt cap: ${mcap / 1_000_000_000:.1f}B"
                elif mcap >= 1_000_000:
                    mcap_str = f"  Mkt cap: ${mcap / 1_000_000:.1f}M"

            lines.append(f"• **{coin_id.title()}**: {vs_currency.upper()} {price_str}{change_str}{mcap_str}")

        return "\n".join(lines)

    except Exception as exc:
        return f"Could not fetch crypto prices: {exc}"
