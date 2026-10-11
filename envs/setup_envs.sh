#!/bin/zsh
# Create the Python environments that ./bench uses (envs/.venv-<name>).
#   .venv-eval      the system adapters (systems/) and GraphRAG-Bench scoring
#                   (its requirements.txt at the pinned commit). Python 3.10, as GraphRAG-Bench recommends.
#   .venv-lightrag  LightRAG v1.2.5, the version that GraphRAG-Bench Examples/README.md uses
#   .venv-extra     extra scorers that are not part of an official protocol (RAGAS, DeepEval)
#   .venv-erag      EnterpriseRAG-Bench scorer and the LangChain vector system
#   .venv-graphrag  Microsoft GraphRAG 3.3.0 (needs Python 3.11 to 3.13)
# Add a new environment here when a benchmark needs packages that conflict with these.
# Use `python -m pip`: the pip launcher scripts keep the absolute path of the folder they were made in.
#   envs/setup_envs.sh            all environments
#   envs/setup_envs.sh <name>     only envs/.venv-<name>
set -e
cd "${0:A:h}"
ONLY="${1:-}"
want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }
PY310="$HOME/.local/share/mise/installs/python/3.10.16/bin/python3.10"
PY311="$HOME/.local/share/mise/installs/python/3.11.13/bin/python3.11"
GRAPHRAG_BENCH="../benchmarks/graphrag-bench/upstream"

if want eval; then
[ -x .venv-eval/bin/python ] || "$PY310" -m venv .venv-eval
.venv-eval/bin/python -m pip install -q --upgrade pip
# requirements.txt does not pin the embedding stack; transformers 5 / sentence-transformers 6 crash
# (SIGSEGV) under the scorer's concurrent embed_query calls, so use the langchain-0.3-era versions.
.venv-eval/bin/python -m pip install -q -r "$GRAPHRAG_BENCH/requirements.txt" "langchain_community<0.4" \
  "sentence-transformers>=3,<4" "transformers>=4.45,<5" torch google-auth requests websockets \
  "boto3>=1.40" aws-bedrock-token-generator
.venv-eval/bin/python -m pip freeze > pip_freeze_eval.txt
echo "eval env ok"
fi

if want lightrag; then
[ -x .venv-lightrag/bin/python ] || "$PY310" -m venv .venv-lightrag
.venv-lightrag/bin/python -m pip install -q --upgrade pip
# lightrag-hku 1.2.5 (March 2025) declares no dependencies: these are its requirements.txt, with
# openai/transformers/datasets pinned to the major versions of that time.
.venv-lightrag/bin/python -m pip install -q "lightrag-hku==1.2.5" aiohttp configparser future nano-vectordb networkx \
  numpy pandas pipmaster pydantic python-dotenv setuptools tenacity tiktoken xxhash torch nest_asyncio tqdm \
  "openai>=1.60,<2" "httpx<0.29" "transformers>=4.45,<5" "datasets>=3,<4" \
  requests "boto3>=1.40" aws-bedrock-token-generator
.venv-lightrag/bin/python -m pip freeze > pip_freeze_lightrag.txt
echo "lightrag env ok"
fi

if want extra; then
[ -x .venv-extra/bin/python ] || "$PY310" -m venv .venv-extra
.venv-extra/bin/python -m pip install -q --upgrade pip
# ragas 0.4 imports langchain_community.chat_models.vertexai, which langchain_community 0.4 removed.
.venv-extra/bin/python -m pip install -q ragas deepeval "langchain_community<0.4" openai numpy requests \
  "boto3>=1.40" aws-bedrock-token-generator
.venv-extra/bin/python -m pip freeze > pip_freeze_extra.txt
echo "extra env ok"
fi

if want erag; then
[ -x .venv-erag/bin/python ] || "$PY310" -m venv .venv-erag
.venv-erag/bin/python -m pip install -q --upgrade pip
# EnterpriseRAG-Bench: the official scorer (its requirements.txt at the pinned commit) and the
# LangChain vector system (systems/setup_langchain.py, retrievers.langchain_vector).
.venv-erag/bin/python -m pip install -q -r ../benchmarks/enterpriserag-bench/upstream/requirements.txt tqdm requests \
  "boto3>=1.40" aws-bedrock-token-generator langchain-core langchain-openai langchain-community faiss-cpu numpy
.venv-erag/bin/python -m pip freeze > pip_freeze_erag.txt
echo "erag env ok"
fi

if want graphrag; then
[ -x .venv-graphrag/bin/python ] || "$PY311" -m venv .venv-graphrag
.venv-graphrag/bin/python -m pip install -q --upgrade pip
# Microsoft GraphRAG (systems/setup_graphrag.py; run_rag.py --retriever graphrag_local), fast (NLP) indexing method.
.venv-graphrag/bin/python -m pip install -q "graphrag==3.3.0" requests "boto3>=1.40" aws-bedrock-token-generator
.venv-graphrag/bin/python -m pip freeze > pip_freeze_graphrag.txt
echo "graphrag env ok"
fi

if want lightrag; then
echo "LightRAG also needs the GraphRAG-Bench context patch:"
echo "  ./bench graphrag-bench patch_lightrag lightrag patch_lightrag.py"
fi
