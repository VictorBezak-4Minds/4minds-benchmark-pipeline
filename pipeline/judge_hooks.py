"""Hooks for LLM-judge calls through langchain_openai.ChatOpenAI, installed in the scorer process.

The official scorers make their own ChatOpenAI judge. install() changes two things, in this
process only:
- usage: each finished call adds its token usage, because the official code does not report
  judge tokens. The totals go to a JSON file at exit and every SAVE_EVERY calls, so a stopped
  shard still leaves a count. A call that raises is not counted.
- drop: request fields that the judge backend refuses (llm_backends.json "judge_drop_params")
  are removed from each request body. All other settings of the scorer stay the same.
- extra_body (llm_backends.json "judge_extra_body"): fields added to each request body, for
  example {"thinking": {"type": "disabled"}} for a Claude judge.
- strip_fence (llm_backends.json "judge_strip_code_fence"): a reply that is not JSON but has a
  Markdown code fence (```json ... ```) with valid JSON inside is replaced by that JSON before the
  official parser reads it. The official calculate_factuality() parses with plain json.loads and
  returns 0.0 on failure without a log line, so a judge that fences its JSON gets factuality 0 for
  every answer. Counts: fences_removed (replies changed), prose_dropped (of these, replies with
  text outside the fence, for example a comment after it).
- not_json_replies: replies that are still not JSON (after the fix, if on). The statement step
  has its own fallback parser, but for the factuality and faithfulness steps such a reply is a 0.
- truncated_replies: replies that stopped at the output-token limit (finish_reason "length").

score.py gives these to score_launcher.py in the environment (JUDGE_USAGE_FILE, JUDGE_DROP_PARAMS,
JUDGE_STRIP_CODE_FENCE, JUDGE_EXTRA_BODY as JSON).
"""
import atexit
import json
import re
import threading
from pathlib import Path

import requests

SAVE_EVERY = 25
_SAVES = []
# A JSON string cannot hold a raw newline, so "\n```" cannot be inside the fenced JSON.
FENCE = re.compile(r"```[A-Za-z]*[ \t]*\n(.*?)\n[ \t]*```", re.S)
USAGE_KEYS = ("calls", "prompt_tokens", "completion_tokens", "total_tokens", "fences_removed", "prose_dropped",
              "not_json_replies", "truncated_replies")
# The judge settings of GraphRAG-Bench generation_eval.py at commit fdbab59 (ChatOpenAI arguments).
OFFICIAL_SETTINGS = {"temperature": 0.0, "top_p": 1, "seed": 42, "presence_penalty": 0, "frequency_penalty": 0}


def preflight(backend, drop=True):
    """One small request with the official settings (less the dropped ones, if drop) and the
    backend's judge_extra_body. Returns the snapshot that served it and the rate-limit headers.
    Exits with the judge's error if it fails."""
    settings = {k: v for k, v in OFFICIAL_SETTINGS.items() if not (drop and k in backend.judge_drop_params)}
    settings.update(backend.judge_extra_body)
    response = requests.post(f"{backend.base_url}/chat/completions", timeout=60,
                             headers={"Authorization": f"Bearer {backend.api_key()}"},
                             json={"model": backend.model, "messages": [{"role": "user", "content": "Say OK."}],
                                   "max_tokens": 16, **settings})
    limits = {k.lower(): v for k, v in response.headers.items() if "ratelimit" in k.lower()}
    if response.status_code != 200:
        raise SystemExit(f"Judge {backend.name} refused the request with settings {settings}: "
                         f"HTTP {response.status_code} {response.text[:500]}")
    return {"snapshot": response.json().get("model"), "settings_sent": settings, "rate_limits": limits}


def is_json(text):
    try:
        json.loads(text)
        return True
    except (TypeError, ValueError):
        return False


def unfence(text):
    """(JSON inside the first code fence, True if text outside the fence was dropped), or None if
    the reply is already JSON or has no fence with valid JSON inside."""
    if not isinstance(text, str) or is_json(text):
        return None
    match = FENCE.search(text)
    if not match or not is_json(match.group(1)):
        return None
    return match.group(1), bool((text[:match.start()] + text[match.end():]).strip())


def install(usage_file=None, drop_params=(), strip_fence=False, extra_body=None):
    from langchain_openai import ChatOpenAI

    extra_body = dict(extra_body or {})
    totals = {**dict.fromkeys(USAGE_KEYS, 0), "dropped_params": sorted(drop_params), "strip_code_fence": strip_fence,
              "extra_body": extra_body}
    lock = threading.Lock()
    payload_of, generate = ChatOpenAI._get_request_payload, ChatOpenAI._agenerate

    def save():
        if usage_file:
            Path(usage_file).write_text(json.dumps(totals, indent=1))

    def request_payload(self, *args, **kwargs):
        payload = payload_of(self, *args, **kwargs)
        for name in drop_params:
            payload.pop(name, None)
        if extra_body:
            payload["extra_body"] = {**(payload.get("extra_body") or {}), **extra_body}
        return payload

    async def counted(self, *args, **kwargs):
        result = await generate(self, *args, **kwargs)
        usage = (result.llm_output or {}).get("token_usage") or {}
        counts = dict.fromkeys(("fences_removed", "prose_dropped", "not_json_replies", "truncated_replies"), 0)
        for generation in result.generations:
            counts["truncated_replies"] += (generation.generation_info or {}).get("finish_reason") == "length"
            fixed = unfence(generation.message.content) if strip_fence else None
            if fixed:
                generation.message.content = generation.text = fixed[0]
                counts["fences_removed"] += 1
                counts["prose_dropped"] += fixed[1]
            counts["not_json_replies"] += not is_json(generation.message.content)
        with lock:
            totals["calls"] += 1
            for key, value in counts.items():
                totals[key] += value
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                totals[key] += usage.get(key) or 0
            if totals["calls"] % SAVE_EVERY == 0:
                save()
        return result

    ChatOpenAI._get_request_payload = request_payload
    ChatOpenAI._agenerate = counted
    atexit.register(save)
    _SAVES.append(save)
    save()
    return totals


def flush():
    """Write the usage files now (for a process that reads them before it exits)."""
    for save in _SAVES:
        save()


def read_usage(files):
    """Sum the usage files of several processes (shards, reruns)."""
    out = dict.fromkeys(USAGE_KEYS, 0)
    for path in files:
        data = json.loads(Path(path).read_text())
        for key in out:
            out[key] += data.get(key) or 0
    return out
