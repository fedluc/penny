import json, hashlib

def normalize_for_hash(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

def hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()