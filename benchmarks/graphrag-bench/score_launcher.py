"""Run the official Evaluation.generation_eval unchanged, with torch kept off the Apple MPS device.

generation_eval.py calls embed_query from several threads at once; on MPS this crashes the
process (SIGSEGV). sentence-transformers picks MPS when torch reports it, so hide it and use CPU.
Run with cwd = the GraphRAG-Benchmark repo and the generation_eval.py arguments.
"""
import os
import runpy
import sys

import torch

def _no_mps():
    return False


_no_mps.__wrapped__ = getattr(torch.backends.mps.is_available, "__wrapped__", torch.backends.mps.is_available)
torch.backends.mps.is_available = _no_mps
sys.path.insert(0, os.getcwd())
sys.argv = ["Evaluation/generation_eval.py", *sys.argv[1:]]
runpy.run_module("Evaluation.generation_eval", run_name="__main__", alter_sys=True)
