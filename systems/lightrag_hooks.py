"""In-memory hooks for LightRAG 1.2.5 (environment `lightrag`), used by systems/run_lightrag.py.

- install_create_hook(): every LightRAG LLM call goes through openai AsyncCompletions.create.
  The hook counts the tokens per call into the USAGE context variable. With a backend from
  pipeline/llm_backends.json it also sets the key again before each call (a Bedrock token is
  made again before it expires), adds the backend generation params at query time only, and
  removes <reasoning>...</reasoning> from the reply (GPT-OSS on Bedrock puts its reasoning in
  the content, and LightRAG would parse it as entities, keywords or answer text).
- enable_delimiter_repair(): GPT-OSS often writes the tuple delimiter <|> as |>, <|, <> or |<,
  breaks a record over lines, or leaves out its parentheses; LightRAG then drops the record.
  The record split of entity extraction repairs these. The same repair as
  benchmarks/graphrag-bench/scripts/run_lightrag_bench.py.
- install_doc_id_hook(): records the full_doc_id of every text chunk that LightRAG puts into
  the query context (local and global paths), in the DOC_IDS context variable, so a runner
  can report the retrieved documents. The chunks and their order do not change.
"""
import contextvars
import inspect
import re

import llm_backends

USAGE = contextvars.ContextVar("usage", default=None)
DOC_IDS = contextvars.ContextVar("doc_ids", default=None)
QUERY_PARAMS = {}

_installed = {}


def install_create_hook(backend=None):
    from openai.resources.chat.completions import AsyncCompletions

    original = _installed.setdefault("create", AsyncCompletions.create)

    async def create(self, *args, **kwargs):
        if backend is not None:
            self._client.api_key = backend.api_key()
        if QUERY_PARAMS:
            kwargs = {**kwargs, **QUERY_PARAMS}
        response = await original(self, *args, **kwargs)
        if backend is not None:
            for choice in getattr(response, "choices", None) or []:
                message = getattr(choice, "message", None)
                if message is not None and isinstance(message.content, str):
                    message.content = llm_backends.REASONING_TAGS.sub("", message.content).strip()
        counter = USAGE.get()
        usage = getattr(response, "usage", None)
        if counter is not None and usage is not None:
            counter["calls"] = counter.get("calls", 0) + 1
            counter["prompt_tokens"] = counter.get("prompt_tokens", 0) + (usage.prompt_tokens or 0)
            counter["completion_tokens"] = counter.get("completion_tokens", 0) + (usage.completion_tokens or 0)
            details = getattr(usage, "completion_tokens_details", None)
            reasoning = getattr(details, "reasoning_tokens", None) if details else None
            counter["reasoning_tokens"] = counter.get("reasoning_tokens", 0) + (reasoning or 0)
        return response

    AsyncCompletions.create = create


def enable_delimiter_repair(patch_file):
    import lightrag.operate as operate
    from lightrag.prompt import PROMPTS

    tuple_delimiter = PROMPTS["DEFAULT_TUPLE_DELIMITER"]
    record_markers = [PROMPTS["DEFAULT_RECORD_DELIMITER"], PROMPTS["DEFAULT_COMPLETION_DELIMITER"]]
    damaged = re.compile(r"(?<!<)\|>|<\|(?!>)|<>|\|<")
    original = _installed.setdefault("split", operate.split_string_by_multi_markers)

    def repairing_split(content, markers):
        records = original(content, markers)
        if markers != record_markers:
            return records
        repaired = []
        for record in records:
            record = damaged.sub(tuple_delimiter, record.replace("\\\n", " ").replace("\n", " "))
            if "(" not in record and re.match(r'\s*"(entity|relationship)"', record):
                record = f"({record.strip()})"
            repaired.append(record)
        return repaired

    operate.split_string_by_multi_markers = repairing_split
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text("# lightrag.operate.split_string_by_multi_markers is replaced in memory by:\n"
                          f"DAMAGED_DELIMITER = re.compile({damaged.pattern!r})\n\n" + inspect.getsource(repairing_split))
    return patch_file


def install_doc_id_hook():
    import lightrag.operate as operate

    def recording(name):
        original = _installed.setdefault(name, getattr(operate, name))

        async def wrapper(*args, **kwargs):
            chunks = await original(*args, **kwargs)
            found = DOC_IDS.get()
            if found is not None:
                found += [c.get("full_doc_id") for c in chunks or [] if isinstance(c, dict) and c.get("full_doc_id")]
            return chunks

        setattr(operate, name, wrapper)

    recording("_find_most_related_text_unit_from_entities")
    recording("_find_related_text_unit_from_relationships")
