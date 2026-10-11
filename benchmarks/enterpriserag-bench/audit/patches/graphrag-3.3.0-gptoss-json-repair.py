# In-memory changes to Microsoft GraphRAG 3.3.0 (graphrag_llm) for GPT-OSS-120B on Amazon Bedrock.
# Source: systems/graphrag_hooks.py install_hooks(). The installed package is not changed.
#
# 1. Each litellm chat call gets enable_json_schema_validation=False. graphrag_llm sets
#    litellm.enable_json_schema_validation = True when it loads, and LiteLLM checks the reply
#    before the hub can remove "<reasoning>...</reasoning>", so every structured reply failed
#    (7 retries each). GraphRAG still parses each reply into its pydantic model.
#
# 2. graphrag_llm.completion.lite_llm_completion.structure_completion_response is replaced by:
DOUBLE_OPEN = re.compile(r"\A\{\s*(?=\{)")

def repair_json(content):
    for candidate in (content, DOUBLE_OPEN.sub("", content, count=1)):
        for strict in (True, False):
            try:
                parsed = json.loads(candidate, strict=strict)
            except ValueError:
                continue
            if candidate == content and strict:
                return content
            NOT_JSON["repaired"] += 1
            return json.dumps(parsed)
    NOT_JSON["count"] += 1
    return content

lite_llm_completion.structure_completion_response = lambda response, model: structure(repair_json(response), model)
#
# Why: in the 20-document test, 42 of 45 community-report replies were '{' + a complete JSON
# object ('{\n{ ... }'), which Bedrock's JSON mode makes. In the 500-document test, about 1% of
# replies had raw tabs or line breaks inside JSON strings. Without the repair, GraphRAG skips
# the report of that community (a WARNING "No report found for community"). Replies that stay
# invalid after the repair are still skipped; index_manifest.json counts them
# (not_json_replies, reports_missing).
