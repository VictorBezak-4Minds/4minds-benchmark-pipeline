#!/bin/zsh
# Create the Python environments that ./bench uses (envs/.venv-<name>).
#   .venv-eval      the system adapters (systems/) and GraphRAG-Bench scoring
#                   (its requirements.txt at the pinned commit). Python 3.10, as GraphRAG-Bench recommends.
#   .venv-lightrag  LightRAG v1.2.5, the version that GraphRAG-Bench Examples/README.md uses
# Add a new environment here when a benchmark needs packages that conflict with these.
# Use `python -m pip`: the pip launcher scripts keep the absolute path of the folder they were made in.
set -e
cd "${0:A:h}"
PY310="$HOME/.local/share/mise/installs/python/3.10.16/bin/python3.10"
GRAPHRAG_BENCH="../benchmarks/graphrag-bench/upstream"

[ -x .venv-eval/bin/python ] || "$PY310" -m venv .venv-eval
.venv-eval/bin/python -m pip install -q --upgrade pip
# requirements.txt does not pin the embedding stack; transformers 5 / sentence-transformers 6 crash
# (SIGSEGV) under the scorer's concurrent embed_query calls, so use the langchain-0.3-era versions.
.venv-eval/bin/python -m pip install -q -r "$GRAPHRAG_BENCH/requirements.txt" "langchain_community<0.4" \
  "sentence-transformers>=3,<4" "transformers>=4.45,<5" torch google-auth requests websockets
.venv-eval/bin/python -m pip freeze > pip_freeze_eval.txt
echo "eval env ok"

[ -x .venv-lightrag/bin/python ] || "$PY310" -m venv .venv-lightrag
.venv-lightrag/bin/python -m pip install -q --upgrade pip
# lightrag-hku 1.2.5 (March 2025) declares no dependencies: these are its requirements.txt, with
# openai/transformers/datasets pinned to the major versions of that time.
.venv-lightrag/bin/python -m pip install -q "lightrag-hku==1.2.5" aiohttp configparser future nano-vectordb networkx \
  numpy pandas pipmaster pydantic python-dotenv setuptools tenacity tiktoken xxhash torch nest_asyncio tqdm \
  "openai>=1.60,<2" "httpx<0.29" "transformers>=4.45,<5" "datasets>=3,<4"
.venv-lightrag/bin/python -m pip freeze > pip_freeze_lightrag.txt
echo "lightrag env ok"
echo "LightRAG also needs the GraphRAG-Bench context patch:"
echo "  ./bench graphrag-bench patch_lightrag lightrag patch_lightrag.py"
