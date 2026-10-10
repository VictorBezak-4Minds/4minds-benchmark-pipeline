"""Named LLM backends (pipeline/llm_backends.json) for the system adapters.

A backend is an OpenAI-compatible Chat Completions endpoint with its own authentication,
model, generation settings and list prices. Runners take --llm <name>; settings() goes into
run_config.json, so a run folder cannot mix two backends.

Authentication types:
  api_key_file       ~/.config/<provider>/api_key, read with bench_common.load_key()
  aws_bedrock_token  a short-term Bedrock bearer token made in memory from the AWS profile's
                     credentials (boto3). It is never written to disk and is made again
                     every TOKEN_REFRESH_S, so long runs do not use an expired token.
"""
import json
import re
import sys
import threading
import time
from pathlib import Path

import requests

import bench_common as bc

CONFIG = Path(__file__).with_name("llm_backends.json")
RETRYABLE_HTTP = {0, 408, 409, 429, 500, 502, 503, 504}
TOKEN_REFRESH_S = 1800
# GPT-OSS on Bedrock can put its reasoning in the message content between these tags.
REASONING_TAGS = re.compile(r"<reasoning>.*?</reasoning>", re.S)


def load_all():
    return json.loads(CONFIG.read_text())


def names():
    return sorted(load_all())


class Backend:
    def __init__(self, name):
        configs = load_all()
        if name not in configs:
            sys.exit(f"Unknown LLM backend {name!r}. Backends in {CONFIG.name}: {', '.join(sorted(configs))}")
        self.name, self.config = name, configs[name]
        self.auth = self.config["auth"]
        self.base_url = self.config["base_url"].format(region=self.auth.get("region", "")).rstrip("/")
        self.model = self.config["model"]
        self.params = dict(self.config.get("params") or {})
        self.prices = self.config.get("price_usd_per_1m") or {}
        self.max_concurrency = self.config.get("max_concurrency", 4)
        self._key, self._key_time = None, 0.0
        self._lock = threading.Lock()

    def settings(self):
        """The backend part of run_config.json (no secrets)."""
        return {"llm_backend": self.name, "llm_base_url": self.base_url, "llm_model": self.model,
                "llm_params": self.params, "llm_auth": {k: v for k, v in self.auth.items()}}

    def api_key(self):
        with self._lock:
            if self.auth["type"] == "api_key_file":
                if self._key is None:
                    self._key = bc.load_key(self.auth["provider"])
            elif self.auth["type"] == "aws_bedrock_token":
                if self._key is None or time.monotonic() - self._key_time > TOKEN_REFRESH_S:
                    self._key, self._key_time = self._bedrock_token(), time.monotonic()
            else:
                sys.exit(f"Backend {self.name}: unknown auth type {self.auth['type']!r}")
            return self._key

    def _bedrock_token(self):
        import boto3
        from aws_bedrock_token_generator import BedrockTokenGenerator
        credentials = boto3.Session(profile_name=self.auth["profile"]).get_credentials()
        if credentials is None:
            sys.exit(f"Backend {self.name}: no AWS credentials for profile {self.auth['profile']!r}. Run aws login.")
        return BedrockTokenGenerator().get_token(credentials.get_frozen_credentials(), self.auth["region"])

    def request_body(self, messages):
        return {"model": self.model, "messages": messages, **self.params}

    def chat(self, messages, timeout):
        """One request. Returns (result, error, retryable); result has answer, usage, finish_reason, raw."""
        try:
            response = requests.post(f"{self.base_url}/chat/completions", json=self.request_body(messages),
                                     headers={"Authorization": f"Bearer {self.api_key()}"}, timeout=timeout)
        except requests.RequestException as e:
            return None, {"code": "network", "message": str(e)[:500]}, True
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": {"message": response.text[:500]}}
        if response.status_code != 200 or "error" in payload:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {"message": str(payload)[:500]}
            error["http_status"] = response.status_code
            if response.status_code in (401, 403) and self.auth["type"] == "aws_bedrock_token":
                with self._lock:
                    self._key = None
                return None, error, True
            return None, error, response.status_code in RETRYABLE_HTTP
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        answer = REASONING_TAGS.sub("", message.get("content") or "").strip()
        result = {"answer": answer, "finish_reason": choice.get("finish_reason"), "usage": payload.get("usage") or {},
                  "raw": payload}
        if not answer:
            return None, {"code": "empty_answer", "finish_reason": choice.get("finish_reason"),
                          "usage": result["usage"]}, True
        return result, None, False

    def cost(self, tokens):
        if not self.prices:
            return None
        prompt = tokens.get("prompt_tokens", 0)
        # Gemini's OpenAI endpoint counts thinking tokens only in total_tokens.
        output = max(tokens.get("completion_tokens", 0), tokens.get("total_tokens", 0) - prompt)
        return (prompt * self.prices.get("input", 0) + output * self.prices.get("output", 0)) / 1e6
