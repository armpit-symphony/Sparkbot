"""
Sparkbot tool definitions and executors.

Each tool is declared in OpenAI function-calling format (litellm-compatible)
and has a corresponding async executor. Add new tools here — the dispatcher
and LLM definitions are updated automatically.
"""
import ast
import operator
import uuid
from datetime import datetime, timezone
from typing import Optional


# ─── Tool definitions (sent to the LLM) ──────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": (
                "Store a fact about the user for future conversations. "
                "Call this proactively when the user reveals their name, role, timezone, "
                "preferred language, an ongoing project, or any preference you should remember. "
                "Keep facts short, specific, and in third-person: 'User prefers Python over JavaScript'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "A concise, specific fact about the user (max 200 chars)",
                    }
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_fact",
            "description": "Remove a stored fact about the user by its ID. Use when the user asks you to forget something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "UUID of the memory to delete (shown in /memory list)",
                    }
                },
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. Use this for recent events, "
                "facts you are uncertain about, prices, news, or anything requiring "
                "up-to-date data beyond your training cutoff."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Concise search query (3-10 words is ideal)",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date and time (UTC). Use when the user asks what time or date it is.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a mathematical expression and return the result. "
                "Use for arithmetic, percentages, unit conversions, and simple formulas. "
                "Supports: +, -, *, /, **, ( )"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '(150 * 1.2) / 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]


# ─── Executors ────────────────────────────────────────────────────────────────

async def _web_search(query: str) -> str:
    from ddgs import DDGS
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=4))
        if not results:
            return f"No results found for: {query}"
        lines = []
        for r in results:
            title = r.get("title", "")
            body  = r.get("body", "")
            href  = r.get("href", "")
            lines.append(f"**{title}**\n{body}\n{href}")
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


async def _get_datetime() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("UTC: %A, %B %d %Y — %H:%M:%S")


# Safe math evaluator — no eval(), only whitelisted AST nodes
_OPS = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.Pow:  operator.pow,
    ast.Mod:  operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported: {ast.dump(node)}")

async def _calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree.body)
        # Format: strip unnecessary .0 for whole numbers
        if isinstance(result, float) and result.is_integer():
            return f"{expression} = {int(result)}"
        return f"{expression} = {result}"
    except Exception as e:
        return f"Could not evaluate '{expression}': {e}"


# ─── Memory tool executors ────────────────────────────────────────────────────

async def _remember_fact(fact: str, user_id: Optional[str], session) -> str:
    if not user_id or session is None:
        return "Memory unavailable (no session context)."
    from app.crud import add_user_memory
    mem = add_user_memory(session, uuid.UUID(user_id), fact)
    return f"Remembered: {mem.fact}"


async def _forget_fact(memory_id: str, user_id: Optional[str], session) -> str:
    if not user_id or session is None:
        return "Memory unavailable (no session context)."
    from app.crud import delete_user_memory
    ok = delete_user_memory(session, uuid.UUID(memory_id), uuid.UUID(user_id))
    return "Forgotten." if ok else "Memory not found or not yours."


# ─── Dispatcher ───────────────────────────────────────────────────────────────

async def execute_tool(
    name: str,
    args: dict,
    user_id: Optional[str] = None,
    session=None,
) -> str:
    """Execute a tool by name and return its string result."""
    if name == "remember_fact":
        return await _remember_fact(args.get("fact", ""), user_id, session)
    if name == "forget_fact":
        return await _forget_fact(args.get("memory_id", ""), user_id, session)
    if name == "web_search":
        return await _web_search(args.get("query", ""))
    if name == "get_datetime":
        return await _get_datetime()
    if name == "calculate":
        return await _calculate(args.get("expression", ""))
    return f"Unknown tool: {name}"
