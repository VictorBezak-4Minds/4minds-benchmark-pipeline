"""Microsoft GraphRAG in the hub (environment `graphrag`): configuration and in-memory LiteLLM hooks.

config() makes a GraphRagConfig in memory: the GraphRAG defaults, the models of two
pipeline/llm_backends.json entries, and the folders under one index folder. No key goes to a
file or an environment variable: the embedding key stays in the config object, and the chat
key (the short-lived Bedrock token) is set on each call by the hook.

install_hooks() wraps litellm.completion, acompletion, embedding and aembedding (GraphRAG calls
them through the litellm module):
- a chat call to the chat backend gets backend.api_key() (a fresh Bedrock token);
- <reasoning>...</reasoning> is removed from each chat reply (GPT-OSS on Bedrock puts its
  reasoning in the answer text). LiteLLM's own JSON-schema check runs before the hook can remove
  it, so the hook turns that check off for each request (graphrag_llm sets the global flag to True
  when it loads); GraphRAG still parses the cleaned reply into its pydantic model;
- the tokens of every real call are added to USAGE (per model). Calls that GraphRAG answers from
  its cache do not reach litellm, so USAGE counts only paid calls.
Streaming chat calls are refused: the hub never streams, and a stream cannot be cleaned.

It also wraps graphrag_llm's structure_completion_response (the JSON parse of a structured reply,
after the cache, so cached replies are repaired too) with repair_json(). Repairs and replies that
stay invalid are counted in NOT_JSON (first 5 invalid replies kept).
"""
import json
import re
import threading
from pathlib import Path

import llm_backends

USAGE = {}
NOT_JSON = {"count": 0, "repaired": 0, "samples": []}
DOUBLE_OPEN = re.compile(r"\A\{\s*(?=\{)")
_lock = threading.Lock()
CHAT_MODEL_ID = "default_completion_model"
EMBEDDING_MODEL_ID = "default_embedding_model"


def _count(model, usage):
    usage = usage if isinstance(usage, dict) else (usage.model_dump() if hasattr(usage, "model_dump") else {})
    with _lock:
        row = USAGE.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
        row["calls"] += 1
        row["prompt_tokens"] += usage.get("prompt_tokens") or 0
        row["completion_tokens"] += usage.get("completion_tokens") or 0


def repair_json(content):
    """Valid JSON is returned as it is. Else two repairs, alone and together, if the result is JSON:
    remove a '{' in front of the model's own object ('{\\n{...}': Bedrock's JSON mode for GPT-OSS),
    and accept raw control characters (tabs, line breaks) in strings (json.loads strict=False)."""
    for candidate in (content, DOUBLE_OPEN.sub("", content, count=1)):
        for strict in (True, False):
            try:
                parsed = json.loads(candidate, strict=strict)
            except ValueError:
                continue
            if candidate == content and strict:
                return content
            with _lock:
                NOT_JSON["repaired"] += 1
            return json.dumps(parsed)
    with _lock:
        NOT_JSON["count"] += 1
        if len(NOT_JSON["samples"]) < 5:
            NOT_JSON["samples"].append(content[:4000])
    return content


def install_hooks(chat_backend):
    import litellm
    if getattr(litellm, "_hub_hooks", None):
        return
    chat_model = f"openai/{chat_backend.model}"
    original = {name: getattr(litellm, name) for name in ("completion", "acompletion", "embedding", "aembedding")}

    def before(kwargs):
        if kwargs.get("stream"):
            raise ValueError("graphrag_hooks: streaming chat calls are not supported")
        if kwargs.get("model") == chat_model:
            kwargs["api_key"] = chat_backend.api_key()
        kwargs["enable_json_schema_validation"] = False
        return kwargs

    def after(kwargs, response):
        for choice in getattr(response, "choices", None) or []:
            message = getattr(choice, "message", None)
            if message is not None and isinstance(message.content, str):
                message.content = llm_backends.REASONING_TAGS.sub("", message.content).strip()
        _count(kwargs.get("model", "?"), getattr(response, "usage", None))
        return response

    def completion(*args, **kwargs):
        kwargs = before(kwargs)
        return after(kwargs, original["completion"](*args, **kwargs))

    async def acompletion(*args, **kwargs):
        kwargs = before(kwargs)
        return after(kwargs, await original["acompletion"](*args, **kwargs))

    def embedding(*args, **kwargs):
        response = original["embedding"](*args, **kwargs)
        _count(kwargs.get("model", "?"), getattr(response, "usage", None))
        return response

    async def aembedding(*args, **kwargs):
        response = await original["aembedding"](*args, **kwargs)
        _count(kwargs.get("model", "?"), getattr(response, "usage", None))
        return response

    litellm.completion, litellm.acompletion = completion, acompletion
    litellm.embedding, litellm.aembedding = embedding, aembedding
    litellm._hub_hooks = True

    import graphrag_llm.completion.lite_llm_completion as lite_llm_completion
    structure = lite_llm_completion.structure_completion_response
    lite_llm_completion.structure_completion_response = lambda response, model: structure(repair_json(response), model)


def config(index_dir, chat_backend, embedding_backend, concurrency, chat_call_args=None):
    """GraphRAG defaults, with the two backends and the folders of index_dir."""
    from graphrag.config.models.graph_rag_config import GraphRagConfig
    index_dir = Path(index_dir)
    retry = {"type": "exponential_backoff"}
    return GraphRagConfig(**{
        "completion_models": {CHAT_MODEL_ID: {
            "model_provider": "openai", "model": chat_backend.model, "api_base": chat_backend.base_url,
            "api_key": "set-on-each-call", "retry": retry, "call_args": dict(chat_call_args or {})}},
        "embedding_models": {EMBEDDING_MODEL_ID: {
            "model_provider": "openai", "model": embedding_backend.model, "api_base": embedding_backend.base_url,
            "api_key": embedding_backend.api_key(), "retry": retry}},
        "concurrent_requests": concurrency,
        "input_storage": {"type": "file", "base_dir": str(index_dir / "input")},
        "output_storage": {"type": "file", "base_dir": str(index_dir / "output")},
        "cache": {"type": "json", "storage": {"type": "file", "base_dir": str(index_dir / "cache")}},
        "reporting": {"type": "file", "base_dir": str(index_dir / "logs")},
        "vector_store": {"type": "lancedb", "db_uri": str(index_dir / "output" / "lancedb")},
    })


def cost(usage, chat_backend, embedding_backend):
    total = 0.0
    for model, row in usage.items():
        backend = chat_backend if model == f"openai/{chat_backend.model}" else embedding_backend
        total += backend.cost({"prompt_tokens": row["prompt_tokens"], "completion_tokens": row["completion_tokens"]}) or 0
    return round(total, 4)
