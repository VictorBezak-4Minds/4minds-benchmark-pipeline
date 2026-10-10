"""Offline test of pipeline/judge_hooks.py (no API call): fence removal and the patched ChatOpenAI.

    ./bench graphrag-bench test_judge_hooks eval pipeline/test_judge_hooks.py
"""
import asyncio
import json

import judge_hooks
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

U = judge_hooks.unfence
assert U('```json\n{"TP": []}\n```') == ('{"TP": []}', False)
assert U('  ```\n[1, 2]\n```  \n') == ('[1, 2]', False)
assert U('```json\n{"a": "x ```y``` z"}\n```') == ('{"a": "x ```y``` z"}', False)
assert U('```json\n{"TP": []}\n```\n\nNote: the third match is a judgment call.') == ('{"TP": []}', True)
assert U('Here is the JSON:\n```json\n{}\n```') == ('{}', True)
assert U('```json\n{"TP": [}\n```') is None
assert U('{"TP": []}') is None
assert U('no json here') is None
assert U(None) is None

REPLIES = ['```json\n{"TP": [], "FP": [], "FN": []}\n```',
           '```json\n{"TP": [], "FP": [], "FN": []}\n```\nA comment after the fence.',
           '{"TP": [], "FP": [], "FN": []}',
           'I cannot classify these statements.']


async def fake(self, *a, **k):
    content = REPLIES.pop(0)
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content), generation_info={"finish_reason": "stop"})],
                      llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}})

ChatOpenAI._agenerate = fake
totals = judge_hooks.install(None, ["temperature"], strip_fence=True, extra_body={"thinking": {"type": "disabled"}})
llm = ChatOpenAI(model="x", api_key="not-a-key", base_url="http://127.0.0.1:9", temperature=0.0)
payload = llm._get_request_payload("hi")
assert "temperature" not in payload and payload["extra_body"] == {"thinking": {"type": "disabled"}}, payload
replies = [asyncio.run(llm.ainvoke("hi")).content for _ in range(4)]
assert all(json.loads(r) == {"TP": [], "FP": [], "FN": []} for r in replies[:3]), replies
assert replies[3] == 'I cannot classify these statements.'
expected = {"calls": 4, "completion_tokens": 28, "fences_removed": 2, "prose_dropped": 1, "not_json_replies": 1,
            "truncated_replies": 0}
assert all(totals[k] == v for k, v in expected.items()), totals
print("PASS", totals)
