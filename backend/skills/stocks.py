"""
Sparkbot skill: stocks

Real-time stock quotes, price history, and portfolio tracking.
Uses Yahoo Finance unofficial JSON API — no API key required.

Tools:
  stock_quote(symbols)                          — current price for one or more tickers
  stock_history(symbol, period="1mo")           — price history chart summary
  portfolio_add(symbol, shares, cost_basis=0)   — add to your portfolio
  portfolio_view(user_id)                       — view portfolio with current values
  portfolio_remove(symbol)                      — remove from portfolio

Storage: data/portfolio/portfolio.db
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

_YAHOO_QUOTE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_YAHOO_SPARK = "https://query1.finance.yahoo.com/v7/finance/quote"


def _db_path() -> Path:
    root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    base = Path(root).expanduser() if root else Path(__file__).resolve().parents[1] / "data"
    d = base / "portfolio"
    d.mkdir(parents=True, exist_ok=True)
    return d / "portfolio.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL DEFAULT '',
            symbol      TEXT NOT NULL,
            shares      REAL NOT NULL,
            cost_basis  REAL NOT NULL DEFAULT 0,
            added_at    TEXT NOT NULL,
            UNIQUE(user_id, symbol)
        )
    """)
    c.commit()
    return c


async def _fetch_quotes(symbols: list[str]) -> dict:
    syms = ",".join(s.upper() for s in symbols)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            _YAHOO_SPARK,
            params={"symbols": syms, "fields": "regularMarketPrice,regularMarketChange,regularMarketChangePercent,shortName,currency"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
    if r.status_code != 200:
        return {}
    return {q["symbol"]: q for q in r.json().get("quoteResponse", {}).get("result", [])}


async def _stock_quote(args: dict, **_) -> str:
    symbols_raw = (args.get("symbols") or "").strip()
    if not symbols_raw:
        return "Error: symbols required (e.g. 'AAPL' or 'AAPL,TSLA,MSFT')."
    symbols = [s.strip().upper() for s in symbols_raw.replace(",", " ").split() if s.strip()]
    quotes = await _fetch_quotes(symbols)
    if not quotes:
        return f"Could not fetch quotes for {', '.join(symbols)}. Check the ticker symbols."
    lines = [f"**Stock Quotes** — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ""]
    for sym in symbols:
        q = quotes.get(sym)
        if not q:
            lines.append(f"• **{sym}** — not found")
            continue
        price  = q.get("regularMarketPrice", 0)
        change = q.get("regularMarketChange", 0)
        pct    = q.get("regularMarketChangePercent", 0)
        name   = q.get("shortName", sym)
        cur    = q.get("currency", "USD")
        arrow  = "▲" if change >= 0 else "▼"
        color  = "+" if change >= 0 else ""
        lines.append(f"• **{sym}** ({name}): {cur} {price:.2f}  {arrow} {color}{change:.2f} ({color}{pct:.2f}%)")
    return "\n".join(lines)


async def _stock_history(args: dict, **_) -> str:
    symbol = (args.get("symbol") or "").strip().upper()
    period = (args.get("period") or "1mo").strip()
    if not symbol:
        return "Error: symbol is required."
    valid_periods = {"1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"}
    if period not in valid_periods:
        period = "1mo"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            _YAHOO_QUOTE.format(symbol=symbol),
            params={"range": period, "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
    if r.status_code != 200:
        return f"Could not fetch history for {symbol}."
    data = r.json().get("chart", {}).get("result", [{}])[0]
    meta = data.get("meta", {})
    closes = (data.get("indicators", {}).get("quote", [{}]) or [{}])[0].get("close", [])
    closes = [c for c in closes if c is not None]
    if not closes:
        return f"No price data found for {symbol}."
    start_price = closes[0]
    end_price   = closes[-1]
    high        = max(closes)
    low         = min(closes)
    change_pct  = ((end_price - start_price) / start_price * 100) if start_price else 0
    currency    = meta.get("currency", "USD")
    arrow = "▲" if change_pct >= 0 else "▼"
    return (
        f"**{symbol}** — {period} summary\n"
        f"  Current: {currency} {end_price:.2f}\n"
        f"  Period change: {arrow} {change_pct:+.2f}%\n"
        f"  High: {high:.2f}  ·  Low: {low:.2f}\n"
        f"  Data points: {len(closes)} trading days"
    )


def _portfolio_add_sync(args: dict, user_id: str) -> str:
    symbol     = (args.get("symbol") or "").strip().upper()
    shares     = float(args.get("shares") or 0)
    cost_basis = float(args.get("cost_basis") or 0)
    if not symbol or shares <= 0:
        return "Error: symbol and positive shares are required."
    conn = _conn()
    conn.execute(
        "INSERT INTO portfolio(id,user_id,symbol,shares,cost_basis,added_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(user_id,symbol) DO UPDATE SET shares=excluded.shares, cost_basis=excluded.cost_basis",
        (str(uuid.uuid4()), user_id, symbol, shares, cost_basis, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return f"✅ Portfolio updated: **{symbol}** × {shares} shares" + (f" @ ${cost_basis:.2f}" if cost_basis else "")


async def _portfolio_view(args: dict, user_id: str) -> str:
    conn = _conn()
    rows = conn.execute("SELECT symbol, shares, cost_basis FROM portfolio WHERE user_id=? ORDER BY symbol", (user_id,)).fetchall()
    if not rows:
        return "Your portfolio is empty. Add positions with `portfolio_add`."
    symbols = [r["symbol"] for r in rows]
    quotes = await _fetch_quotes(symbols)
    lines = ["**Portfolio**", ""]
    total_value = 0.0
    total_cost  = 0.0
    for row in rows:
        sym   = row["symbol"]
        sh    = row["shares"]
        cost  = row["cost_basis"]
        q     = quotes.get(sym, {})
        price = q.get("regularMarketPrice", 0)
        value = price * sh
        gain  = value - (cost * sh) if cost else None
        gain_str = f"  P&L: {'+' if gain and gain >= 0 else ''}{gain:.2f}" if gain is not None else ""
        total_value += value
        total_cost  += cost * sh if cost else 0
        lines.append(f"• **{sym}**: {sh} shares × ${price:.2f} = **${value:.2f}**{gain_str}")
    lines += ["", f"**Total: ${total_value:.2f}**" + (f"  ·  P&L: ${total_value - total_cost:+.2f}" if total_cost else "")]
    return "\n".join(lines)


def _portfolio_remove_sync(args: dict, user_id: str) -> str:
    symbol = (args.get("symbol") or "").strip().upper()
    if not symbol:
        return "Error: symbol is required."
    conn = _conn()
    conn.execute("DELETE FROM portfolio WHERE user_id=? AND symbol=?", (user_id, symbol))
    conn.commit()
    return f"Removed **{symbol}** from portfolio."


DEFINITIONS = [
    {"type": "function", "function": {"name": "stock_quote", "description": "Get real-time stock price and daily change for one or more ticker symbols.", "parameters": {"type": "object", "properties": {"symbols": {"type": "string", "description": "Ticker symbol(s), comma or space separated. e.g. 'AAPL MSFT TSLA'"}}, "required": ["symbols"]}}},
    {"type": "function", "function": {"name": "stock_history", "description": "Get price history summary for a stock over a period.", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "period": {"type": "string", "description": "1d,5d,1mo,3mo,6mo,1y,2y,5y,ytd,max (default 1mo)"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "portfolio_add", "description": "Add or update a stock position in your personal portfolio.", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "shares": {"type": "number"}, "cost_basis": {"type": "number", "description": "Cost per share (for P&L tracking)"}}, "required": ["symbol", "shares"]}}},
    {"type": "function", "function": {"name": "portfolio_view", "description": "View your stock portfolio with current prices and P&L.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "portfolio_remove", "description": "Remove a position from your portfolio.", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
]

POLICIES = {
    "stock_quote":      {"scope": "read",  "resource": "web",           "default_action": "allow", "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "stock_history":    {"scope": "read",  "resource": "web",           "default_action": "allow", "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "portfolio_add":    {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "portfolio_view":   {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "portfolio_remove": {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["stock_quote"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await _stock_quote(args)


def _register_extra(registry) -> None:
    async def _quote(args, *, user_id=None, room_id=None, session=None): return await _stock_quote(args)
    async def _hist(args, *, user_id=None, room_id=None, session=None):  return await _stock_history(args)
    async def _padd(args, *, user_id=None, room_id=None, session=None):  return await asyncio.to_thread(_portfolio_add_sync, args, user_id or "")
    async def _pview(args, *, user_id=None, room_id=None, session=None): return await _portfolio_view(args, user_id or "")
    async def _prem(args, *, user_id=None, room_id=None, session=None):  return await asyncio.to_thread(_portfolio_remove_sync, args, user_id or "")

    _fns = {"stock_quote": _quote, "stock_history": _hist, "portfolio_add": _padd, "portfolio_view": _pview, "portfolio_remove": _prem}
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _fns[name]
