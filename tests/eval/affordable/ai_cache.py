"""
Cache for the eval's AI calls, so a rerun only pays for documents whose
request changed.

    stats = install(cache_dir)          # wraps ai_extraction.call_forced_tool
    ... run the eval ...
    stats["hits"], stats["misses"]      # [{"tool", "input_tokens", "output_tokens", "key"}]

The key is a sha256 of everything that decides the answer: model, system
prompt, user content (the document text), tool schema and max_tokens. Change
any of them -- a prompt edit, a new field, different OCR text -- and that
document is a miss and is sent again. Code that runs after the response
(flattening tables, cleanup, cross-checks) reruns on the cached copy for free.

Eval only: the app never reads this. Entries hold the model's tool input and
token usage for public documents, no tenant data; they are committed so other
worktrees reuse them.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


def request_key(*, model, system, user_content, tool, max_tokens) -> str:
    blob = json.dumps({"model": model, "system": system, "user_content": user_content, "tool": tool,
                       "max_tokens": max_tokens}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _response(entry, tool_name):
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=tool_name, input=entry["tool_input"])],
        usage=SimpleNamespace(**entry["usage"]),
        stop_reason=entry.get("stop_reason", "tool_use"),
    )


def install(cache_dir: Path, *, write: bool = True, use_cache: bool = True, offline: bool = False) -> dict:
    """Wrap whatever ai_extraction.call_forced_tool currently is (the real
    call, or the --estimate stub) with the cache. `write=False` for estimate
    runs: their stubbed answers must never be stored. `use_cache=False`
    (--no-cache) sends every request but still stores the answers.
    `offline=True` (no API key): a miss raises AIExtractionError, the same
    failure the app shows, and nothing is sent."""
    from app import ai_extraction

    cache_dir = Path(cache_dir)
    inner = ai_extraction.call_forced_tool
    if offline:
        def inner(**_):
            raise ai_extraction.AIExtractionError("not in the eval AI cache (cache-only run, nothing sent)")
    stats = {"hits": [], "misses": []}

    def cached_call(*, system, user_content, tool, model=None, max_tokens=ai_extraction.MAX_TOKENS, **kw):
        model = model or ai_extraction.DEFAULT_MODEL
        key = request_key(model=model, system=system, user_content=user_content, tool=tool, max_tokens=max_tokens)
        path = cache_dir / f"{key}.json"
        if use_cache and path.exists():
            entry = json.loads(path.read_text())
            stats["hits"].append({"tool": tool["name"], "key": key, **entry["usage"]})
            return _response(entry, tool["name"])
        response = inner(system=system, user_content=user_content, tool=tool, model=model, max_tokens=max_tokens, **kw)
        usage = {"input_tokens": getattr(response.usage, "input_tokens", None) or 0,
                 "output_tokens": getattr(response.usage, "output_tokens", None) or 0}
        stats["misses"].append({"tool": tool["name"], "key": key, **usage})
        tool_use = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        if write and tool_use is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "model": model,
                "tool": tool["name"],
                "max_tokens": max_tokens,
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "usage": usage,
                "stop_reason": getattr(response, "stop_reason", None),
                "tool_input": tool_use.input,
            }, indent=1, ensure_ascii=False) + "\n")
        return response

    ai_extraction.call_forced_tool = cached_call
    return stats
