"""One tiny call each to Gemini 3.8 Flash and Gemini 4 Argon, both through SpendGuard.

Runtime models are Gemini since 21 Oct 2026. Claude Haiku 5.5 is called only if
ANTHROPIC_API_KEY is set; without it the Claude check is skipped, not blocked.

Usage: python scripts/smoke_models.py

Credentials come from .env (git-ignored): for Gemini either GOOGLE_API_KEY
(Developer API) or GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT (Vertex AI with gcloud
application-default credentials); optional ANTHROPIC_API_KEY for Claude. Keys are never printed. Each call is capped at 20 output tokens and
recorded in the ledger with role "smoke"; the script fails if the calls together cost more than $0.01.
Exit codes: 0 the Gemini calls succeeded, 2 Gemini is blocked on missing credentials, 1 a call failed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from dotenv import load_dotenv  # noqa: E402

from api.spend import SpendGuard  # noqa: E402

PROMPT = "Reply with the single word: ready"
MAX_SMOKE_USD = 0.01


def claude(guard: SpendGuard) -> tuple[str, dict | None]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "skipped: ANTHROPIC_API_KEY not set", None
    import anthropic

    client = anthropic.Anthropic()
    guard.check("smoke")
    msg = client.messages.create(model="claude-haiku-5-5", max_tokens=20,
                                 messages=[{"role": "user", "content": PROMPT}])
    u = msg.usage
    cache = getattr(u, "cache_read_input_tokens", 0) or 0
    row = guard.record("smoke", "claude-haiku-5-5", u.input_tokens, u.output_tokens, "smoke", "smoke", cache_read=cache)
    text = "".join(getattr(b, "text", "") for b in msg.content).strip()
    return f"ok: {text!r}", row


def gemini(guard: SpendGuard, model: str = "gemini-3.8-flash") -> tuple[str, dict | None]:
    from google import genai
    from google.genai import types

    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
    if vertex and os.environ.get("GOOGLE_CLOUD_PROJECT"):
        client = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                              location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))
        route = "vertex"
    elif os.environ.get("GOOGLE_API_KEY"):
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        route = "developer-api"
    else:
        return "blocked: neither GOOGLE_API_KEY nor GOOGLE_GENAI_USE_VERTEXAI + GOOGLE_CLOUD_PROJECT is set", None
    guard.check("smoke")
    # Argon thinks by default and its thoughts count against max_output_tokens, so it gets more room
    cfg = (types.GenerateContentConfig(max_output_tokens=20, thinking_config=types.ThinkingConfig(thinking_budget=0))
           if model == "gemini-3.8-flash" else types.GenerateContentConfig(max_output_tokens=200))
    resp = client.models.generate_content(model=model, contents=PROMPT, config=cfg)
    u = resp.usage_metadata
    tokens_out = (u.candidates_token_count or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
    row = guard.record("smoke", model, u.prompt_token_count or 0, tokens_out, "smoke", "smoke")
    return f"ok via {route}: {(resp.text or '').strip()!r}", row


def main() -> int:
    load_dotenv(ROOT / ".env")
    guard = SpendGuard()
    blocked = failed = False
    spent = 0.0
    calls = (("gemini-3.8-flash", gemini), ("gemini-4-argon", lambda g: gemini(g, "gemini-4-argon")),
             ("claude-haiku-5-5", claude))
    for name, call in calls:
        try:
            status, row = call(guard)
        except Exception as exc:  # noqa: BLE001 - report any provider error without a traceback full of headers
            status, row = f"failed: {type(exc).__name__}: {str(exc)[:300]}", None
            failed = True
            if "429" in str(exc):
                status += "  (rate limited)"
        blocked |= status.startswith("blocked")
        if row:
            spent += row["cost_usd"]
            print(f"{name}: {status}  tokens in {row['tokens_in']} out {row['tokens_out']}  cost ${row['cost_usd']:.6f}")
        else:
            print(f"{name}: {status}")
    print(f"smoke spend ${spent:.6f} (limit ${MAX_SMOKE_USD:.2f}); ledger {guard.ledger.relative_to(ROOT)}")
    if spent > MAX_SMOKE_USD:
        print("FAIL: smoke spend over the limit")
        return 1
    return 1 if failed else (2 if blocked else 0)


if __name__ == "__main__":
    sys.exit(main())
