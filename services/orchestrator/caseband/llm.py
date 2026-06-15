"""Thin OpenAI runner. Loads OPENAI_API_KEY from the environment (or a gitignored
.env walked up from here), and exposes a single deterministic-ish JSON call used
by the live authoring agents. The LLM only AUTHORS; the reducer still owns state."""
from __future__ import annotations
import json
import os

_KEY_CACHE: str | None = None


def _load_dotenv() -> None:
    """Walk up from this file to find a .env and load KEY=VALUE lines (no deps)."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        path = os.path.join(d, ".env")
        if os.path.isfile(path):
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()  # .env wins
            return
        d = os.path.dirname(d)


def require_key() -> str:
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    _load_dotenv()  # project .env takes precedence over a stale shell key
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Export it or put it in a gitignored .env "
            "at the repo root (see .env.example)."
        )
    _KEY_CACHE = key
    return key


def _is_reasoning_model(model: str) -> bool:
    """Reasoning models (gpt-5, o-series) use a different param surface than 4o:
    they require `max_completion_tokens`, reject `temperature` overrides, and burn
    completion budget on hidden reasoning tokens."""
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def complete_json(system: str, user: str, model: str, max_tokens: int = 600) -> dict:
    """One JSON-mode chat completion, normalized across the 4o and reasoning model
    families. Deterministic where the model allows (temperature=0 on 4o)."""
    from openai import OpenAI

    org = os.environ.get("OPENAI_ORG_ID")
    # max_retries=0 => one logical call is exactly one HTTP request (no SDK retries).
    kwargs = {"api_key": require_key(), "max_retries": 0}
    if org:
        kwargs["organization"] = org
    client = OpenAI(**kwargs)

    params: dict = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    if _is_reasoning_model(model):
        # leave headroom: reasoning tokens are billed against this ceiling, so a
        # 200-token answer budget would be consumed before any content is emitted.
        params["max_completion_tokens"] = max(max_tokens, 4000)
        params["reasoning_effort"] = "minimal"
    else:
        params["max_completion_tokens"] = max_tokens
        params["temperature"] = 0

    resp = client.chat.completions.create(**params)
    return json.loads(resp.choices[0].message.content)
