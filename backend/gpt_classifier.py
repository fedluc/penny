import os
import json
import openai
from typing import Dict

from database import Database

api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)
MODEL = "gpt-4.1-mini"


def classify_transaction(tx: Dict) -> int:
    """
    Returns a category_id (int). Uses DB categories to constrain the model via function-calling.
    Caches by transaction hash.
    """
    db = Database()
    key = db.tx_key(tx)
    cached = db.get_cached_category_id(key)
    if cached is not None:
        return cached

    categories = db.get_active_category_names()
    if not categories:
        categories = [db.ensure_other_exists().name]

    hints = "\n".join(f"- {name}" for name in categories[:50])

    system_prompt = (
        "Classify the bank transaction into exactly ONE of the allowed categories. "
        "Choose ONLY from the provided list. If unsure, pick the closest match."
        "\n\nAllowed categories:\n" + (hints if hints else "- other")
    )

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transaction: {json.dumps(tx)}"},
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

    args = json.loads(resp.choices[0].message.function_call.arguments)
    chosen_name = args["category"]
    row = db.get_category_by_name(chosen_name) or db.ensure_other_exists()

    db.put_cached_category_id(key, tx, row.id)
    return row.id
