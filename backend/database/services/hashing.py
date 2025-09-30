import json, hashlib


def normalize_for_hash(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def hash(text: str | dict) -> str:
    normalized_text = normalize_for_hash(text) if isinstance(text, dict) else text
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
