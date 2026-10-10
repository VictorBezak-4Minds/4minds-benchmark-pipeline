#!/usr/bin/env python3
"""Apply the GraphRAG-Bench Examples/README.md change to LightRAG v1.2.5 in envs/.venv-lightrag.

    ./bench graphrag-bench patch_lightrag lightrag patch_lightrag.py


README: kg_query returns (response, context), and LightRAG.aquery returns them. The README
shows only the final return; this patch also changes the early returns of kg_query (cache
hit and "fail_response"), which otherwise break the tuple unpacking in aquery. Those paths
return context None. Safe to run again. The diff goes to audit/patches/.
"""
import difflib
import sys
from pathlib import Path

import bench_common as bc

PKG = bc.HUB / "envs" / ".venv-lightrag" / "lib" / "python3.10" / "site-packages" / "lightrag"
MARK = "# graphrag-bench context patch"


def function_slice(text, header):
    start = text.index(header)
    end = text.find("\nasync def ", start + 1)
    end2 = text.find("\n    async def ", start + 1)
    candidates = [e for e in (end, end2) if e != -1]
    return start, min(candidates) if candidates else len(text)


def patch_operate(text):
    start, end = function_slice(text, "async def kg_query(")
    body = text[start:end]
    body = body.replace(") -> str | AsyncIterator[str]:",
                        f") -> tuple[str, str] | tuple[AsyncIterator[str], str]:  {MARK}", 1)
    body = body.replace("        return cached_response\n", "        return cached_response, None\n", 1)
    body = body.replace('return PROMPTS["fail_response"]\n', 'return PROMPTS["fail_response"], None\n')
    body = body.replace("        return context\n", "        return context, context\n", 1)
    body = body.replace("        return sys_prompt\n", "        return sys_prompt, context\n", 1)
    head, sep, tail = body.rpartition("    return response\n")
    if not sep:
        sys.exit("kg_query: final 'return response' not found")
    body = head + "    return response, context\n" + tail
    return text[:start] + body + text[end:]


def patch_lightrag(text):
    start, end = function_slice(text, "    async def aquery(")
    body = text[start:end]
    body = body.replace('        if param.mode in ["local", "global", "hybrid"]:\n',
                        f'        context = None  {MARK}\n        if param.mode in ["local", "global", "hybrid"]:\n', 1)
    body = body.replace("            response = await kg_query(", "            response, context = await kg_query(", 1)
    head, sep, tail = body.rpartition("        return response\n")
    if not sep:
        sys.exit("aquery: final 'return response' not found")
    body = head + "        return response, context\n" + tail
    return text[:start] + body + text[end:]


def main():
    out = bc.AUDIT_DIR / "patches" / "lightrag-1.2.5-context-return.diff"
    out.parent.mkdir(parents=True, exist_ok=True)
    diffs = []
    for name, fn in (("operate.py", patch_operate), ("lightrag.py", patch_lightrag)):
        path = PKG / name
        original = path.read_text()
        if MARK in original:
            print(f"{name}: already patched")
            backup = path.with_suffix(".py.orig")
            if backup.exists():
                original_text = backup.read_text()
                diffs += difflib.unified_diff(original_text.splitlines(True), original.splitlines(True),
                                              f"a/lightrag/{name}", f"b/lightrag/{name}")
            continue
        patched = fn(original)
        path.with_suffix(".py.orig").write_text(original)
        path.write_text(patched)
        diffs += difflib.unified_diff(original.splitlines(True), patched.splitlines(True),
                                      f"a/lightrag/{name}", f"b/lightrag/{name}")
        print(f"{name}: patched")
    out.write_text("".join(diffs))
    bc.audit("lightrag_patch", diff=str(out), sha256=bc.sha256(out))
    print(f"diff -> {out}")


if __name__ == "__main__":
    main()
