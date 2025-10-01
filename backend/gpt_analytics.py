from __future__ import annotations
from dataclasses import dataclass
from datetime import date as DateOnly, datetime
import os
import json

from openai import OpenAI  # pip install openai
from database.database import Database
from database.services.reporting import ResultOrder
from gpt_classifier import OPENAI_API_KEY_FILE, DEFAULT_MODEL
# --- Model & client ---

if not os.getenv(OPENAI_API_KEY_FILE) and os.path.exists(OPENAI_API_KEY_FILE.lower()):
    with open(OPENAI_API_KEY_FILE.lower(), "r") as f:
        os.environ[OPENAI_API_KEY_FILE] = f.read().strip()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --- Helpers ---
def _iso_date(s: str) -> DateOnly:
    # Expect YYYY-MM-DD. Keep strict to avoid ambiguity.
    return datetime.fromisoformat(s).date()

def _serialize(obj: any) -> any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, DateOnly):
        return obj.isoformat()
    return obj

# --- Tool wrappers (READ-ONLY) ---
@dataclass
class ReadonlyDBTools:
    db: Database

    # 1) list recent expenses
    def list_expenses(self, limit: int = 50, offset: int = 0, since: str | None = None) -> list[dict]:
        since_d = _iso_date(since) if since else None
        rows = self.db.list_expenses(limit=limit, offset=offset, since=since_d)
        return rows

    # 2) Expenses between dates (optional category filter)
    def get_expenses_between(
        self,
        start_date: str,
        end_date: str,
        category: str | int | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: ResultOrder = ResultOrder.DESC,
    ) -> list[dict]:
        sd, ed = _iso_date(start_date), _iso_date(end_date)
        return self.db.get_expenses_between(
            sd, ed, category=category, limit=limit, offset=offset, order=order
        )

    # 3) Sum for a single category
    def sum_for_category_between(self, category: str | int, start_date: str, end_date: str) -> float:
        sd, ed = _iso_date(start_date), _iso_date(end_date)
        return float(self.db.sum_for_category_between(category, sd, ed))

    # 4) Totals by category
    def totals_by_category(
        self,
        start_date: str,
        end_date: str,
        only_active: bool = True,
        include_zero: bool = False,
        order: ResultOrder = ResultOrder.DESC,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        sd, ed = _iso_date(start_date), _iso_date(end_date)
        return self.db.totals_by_category(
            sd, ed, only_active=only_active, include_zero=include_zero,
            order=order, limit=limit, offset=offset
        )

    # 5) Category name helper (metadata only)
    def get_active_category_names_with_other(self, limit: int = 50) -> dict[str, any]:
        names, other_id = self.db.get_active_category_names_with_other(limit)
        return {"names": names, "other_id": other_id}


# --- Tool dispatcher (no writes!) ---
def _call_tool(tools: ReadonlyDBTools, name: str, arguments: dict[str, any]) -> any:
    if name == "list_expenses":
        return tools.list_expenses(**arguments)
    if name == "get_expenses_between":
        return tools.get_expenses_between(**arguments)
    if name == "sum_for_category_between":
        return tools.sum_for_category_between(**arguments)
    if name == "totals_by_category":
        return tools.totals_by_category(**arguments)
    if name == "get_active_category_names_with_other":
        return tools.get_active_category_names_with_other(**arguments)
    raise ValueError(f"Unknown or disallowed tool: {name}")

FUNCTIONS = [
    {
        "name": "list_expenses",
        "description": "List recent expenses (most recent first). Safe, read-only.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "since": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD", "default": None},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_expenses_between",
        "description": "Return expenses in [start_date, end_date], optional category filter.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "category": {"oneOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}], "default": None},
                "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 10000, "default": None},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "order": {"type": "string", "enum": ["asc", "desc"], "default": "asc"},
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "sum_for_category_between",
        "description": "Sum of amounts for a category within a date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["category", "start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "totals_by_category",
        "description": "Per-category totals within a date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "only_active": {"type": "boolean", "default": True},
                "include_zero": {"type": "boolean", "default": False},
                "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 10000, "default": None},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_active_category_names_with_other",
        "description": "Return active category names plus the 'Other' category id.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            },
            "additionalProperties": False,
        },
    },
]

def ask_expenses(db: Database, user_prompt: str) -> Dict[str, Any]:
    tools_impl = ReadonlyDBTools(db=db)

    messages: List[Dict[str, Any]] = [
        {"role": "system",
         "content": "You are a helpful financial assistant. Use only the provided tools. Never write to the database."},
        {"role": "user", "content": user_prompt},
    ]

    # 1) Let the model decide tools
    r1 = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
        tools=[{"type": "function", "function": f} for f in FUNCTIONS],
        tool_choice="auto",
        temperature=0.2,
    )
    choice = r1.choices[0]
    msg = choice.message

    # 2) If the model called tools, execute them and send results back
    if msg.tool_calls:
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": msg.tool_calls,
        })

        data_map: Dict[str, Any] = {}
        tools_used: List[str] = []

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            result = _call_tool(tools_impl, name, args)
            tools_used.append(name)
            data_map[name] = result

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": name,
                "content": json.dumps({"ok": True, "result": result}, default=_serialize),
            })

        # 3) Force a textual answer
        r2 = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            tools=[{"type": "function", "function": f} for f in FUNCTIONS],  # <— add this
            tool_choice="none",                                              # <— forces text, no more tool calls
            temperature=0,
        )
        final_text = (r2.choices[0].message.content or "").strip()
        return {"answer": final_text, "tools_used": tools_used, "data": data_map}

    # 4) No tools called
    final_text = (msg.content or "").strip()
    return {"answer": final_text, "tools_used": [], "data": None}

# --- Example usage ---
if __name__ == "__main__":
    db = Database(echo=False)  # uses sqlite:///expense.db by default
    examples = [
        "Show me total spend by category from 2023-01-01 to 2025-01-01.",
        # "How much did I spend on groceries in August 2025?",
        # "list my 20 most recent expenses.",
        "Between 2023-05-01 and 2025-01-01, list expenses for 'restaurants' sorted by date desc.",
        "What active categories do I have?"
    ]
    for q in examples:
        print(f"\nQ: {q}")
        out = ask_expenses(db, q)
        print("A:", out["answer"])
