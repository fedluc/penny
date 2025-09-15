# classifier.py
import os
import json
from typing import Dict, List, Tuple, Optional

import openai
from database import Database

DEFAULT_MODEL = "gpt-4.1-mini"
OPENAI_API_KEY_FILE = "OPENAI_API_KEY"


class GPTClassifier:
    def __init__(
        self,
        db: Optional[Database] = None,
        client: Optional[openai.OpenAI] = None,
        model: str = DEFAULT_MODEL,
        api_key_filepath: str = OPENAI_API_KEY_FILE.lower(),
    ):
        self.db = db or Database()
        self._load_api_key_from_file(api_key_filepath)
        self.client = client or openai.OpenAI(
            api_key=os.environ.get(OPENAI_API_KEY_FILE)
        )
        self.model = model

    # Load api key from file if not in env
    def _load_api_key_from_file(self, filepath: str) -> None:
        if not os.getenv(OPENAI_API_KEY_FILE) and os.path.exists(filepath):
            with open(filepath, "r") as f:
                os.environ[OPENAI_API_KEY_FILE] = f.read().strip()

    # Cache fast path
    def _lookup_cache(self, tx: Dict) -> Optional[int]:
        return self.db.cache_lookup(tx)

    # Categories + ensure 'other'
    def _fetch_categories_with_other(self, limit: int = 50) -> Tuple[List[str], int]:
        return self.db.get_active_category_names_with_other(limit=limit)

    # Prompt builder
    def _build_system_prompt(self, categories: List[str]) -> str:
        return (
            "Classify the bank transaction into exactly ONE of the allowed categories. "
            "Choose ONLY from the provided list. If unsure, pick the closest match.\n\n"
            "Allowed categories:\n" + "\n".join(f"- {c}" for c in categories)
        )

    # Model call using Tools API
    def _request_model_choice(self, tx: Dict, categories: List[str]) -> str:
        system_prompt = self._build_system_prompt(categories)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "categorize_transaction",
                    "description": "Assign the transaction to one of the predefined categories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string", "enum": categories}
                        },
                        "required": ["category"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Transaction: {json.dumps(tx, separators=(',', ':'))}",
                    },
                ],
                tools=tools,
                tool_choice={
                    "type": "function",
                    "function": {"name": "categorize_transaction"},
                },
                temperature=0,
            )
        except Exception:
            return "other"
        return self._extract_category_from_tool_calls(resp, categories) or "other"

    # Dedicated parser for tool calls
    def _extract_category_from_tool_calls(
        self, resp, categories: List[str]
    ) -> Optional[str]:
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return None
        msg = getattr(choices[0], "message", None)
        calls = getattr(msg, "tool_calls", None) or []
        for call in calls:
            if getattr(call, "type", None) != "function":
                continue
            fn = getattr(call, "function", None)
            if not fn or getattr(fn, "name", None) != "categorize_transaction":
                continue
            args_raw = getattr(fn, "arguments", None)
            args = None
            if isinstance(args_raw, dict):
                args = args_raw
            elif isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except Exception:
                    continue
            if not args:
                continue
            cat = args.get("category")
            if isinstance(cat, str) and cat in categories:
                return cat
        return None

    # Resolve + cache
    def _resolve_and_cache(
        self, tx: Dict, chosen_name: str, fallback_other_id: int
    ) -> int:
        cat_id = self.db.resolve_category_id(
            chosen_name, fallback_other_id=fallback_other_id
        )
        self.db.cache_write(tx, cat_id)
        return cat_id

    # Public API
    def classify(self, tx: Dict) -> int:
        cached = self._lookup_cache(tx)
        if cached is not None:
            return cached
        categories, other_id = self._fetch_categories_with_other()
        chosen_name = self._request_model_choice(tx, categories)
        return self._resolve_and_cache(tx, chosen_name, other_id)

    def classify_batch(self, txs: List[Dict]) -> List[int]:
        return [self.classify(tx) for tx in txs]
