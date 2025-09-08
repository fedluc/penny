# classifier.py
import os
import json
from typing import Dict, List, Tuple, Optional

import openai
from database import Database

DEFAULT_MODEL = "gpt-4.1-mini"


class GPTClassifier:
    def __init__(
        self,
        db: Optional[Database] = None,
        client: Optional[openai.OpenAI] = None,
        model: str = DEFAULT_MODEL,
    ):
        self.db = db or Database()
        self.client = client or openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model

    # ---- Step 1: cache fast path
    def _lookup_cache(self, tx: Dict) -> Optional[int]:
        return self.db.cache_lookup(tx)

    # ---- Step 2: categories + ensure 'other'
    def _fetch_categories_with_other(self, limit: int = 50) -> Tuple[List[str], int]:
        return self.db.get_active_category_names_with_other(limit=limit)

    # ---- Step 3: prompt + model call
    @staticmethod
    def _build_system_prompt(categories: List[str]) -> str:
        return (
            "Classify the bank transaction into exactly ONE of the allowed categories. "
            "Choose ONLY from the provided list. If unsure, pick the closest match.\n\n"
            "Allowed categories:\n" + "\n".join(f"- {c}" for c in categories)
        )

    def _request_model_choice(self, tx: Dict, categories: List[str]) -> str:
        system_prompt = self._build_system_prompt(categories)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Transaction: {json.dumps(tx, separators=(',', ':'))}"},
            ],
            functions=[
                {
                    "name": "categorize_transaction",
                    "description": "Assign the transaction to one of the predefined categories.",
                    "parameters": {
                        "type": "object",
                        "properties": {"category": {"type": "string", "enum": categories}},
                        "required": ["category"],
                    },
                }
            ],
            function_call={"name": "categorize_transaction"},
            temperature=0,
        )
        try:
            fc = resp.choices[0].message.function_call
            args_raw = fc.arguments if fc else None
            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            chosen = args.get("category")
            if isinstance(chosen, str) and chosen.strip():
                return chosen
        except Exception:
            pass
        return "other"

    # ---- Step 4: resolve + cache
    def _resolve_and_cache(self, tx: Dict, chosen_name: str, fallback_other_id: int) -> int:
        cat_id = self.db.resolve_category_id(chosen_name, fallback_other_id=fallback_other_id)
        self.db.cache_write(tx, cat_id)
        return cat_id

    # ---- Public API
    def classify(self, tx: Dict) -> int:
        """
        Classify a single transaction -> category_id (int).
        """
        cached = self._lookup_cache(tx)
        if cached is not None:
            return cached

        categories, other_id = self._fetch_categories_with_other()
        chosen_name = self._request_model_choice(tx, categories)
        return self._resolve_and_cache(tx, chosen_name, other_id)

    def classify_batch(self, txs: List[Dict]) -> List[int]:
        """
        Convenience method for batch classification with per-item caching.
        """
        results: List[int] = []
        categories: Optional[List[str]] = None
        other_id: Optional[int] = None

        for tx in txs:
            cached = self._lookup_cache(tx)
            if cached is not None:
                results.append(cached)
                continue

            if categories is None or other_id is None:
                categories, other_id = self._fetch_categories_with_other()

            chosen_name = self._request_model_choice(tx, categories)
            cat_id = self._resolve_and_cache(tx, chosen_name, other_id)
            results.append(cat_id)

        return results
