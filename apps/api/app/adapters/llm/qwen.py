"""Qwen cloud adapter using real HTTP Chat Completions and strict JSON Schema.

Only tests inject a mock HTTP transport. In production, requests go to the
configured Alibaba Cloud Model Studio workspace HTTPS endpoint.
"""
from copy import deepcopy
import hashlib
import json
import logging
from time import perf_counter, sleep
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import LLMCall

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMFailure(Exception):
    """Safe-to-display error without credentials or private script content."""


def strict_json_schema(spec: dict) -> dict:
    """Force closed objects/required properties for compatible strict schema output."""
    cloned = deepcopy(spec)

    def visit(node: object) -> None:
        if isinstance(node, dict):
            # The provider supports a restricted JSON Schema subset.
            # Pydantic still enforces these constraints after parsing.
            for unsupported in ("default", "examples", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "pattern", "format"):
                node.pop(unsupported, None)
            if node.get("type") == "object" and isinstance(node.get("properties"), dict):
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(cloned)
    return cloned


class QwenCloudAdapter:
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self._client = client

    def _check_config(self) -> None:
        if not self.settings.dashscope_api_key:
            raise LLMFailure("尚未配置 DASHSCOPE_API_KEY；请在服务端 .env 中填写百炼 API Key。")
        url = self.settings.dashscope_base_url
        if not url or "YOUR_WORKSPACE_ID" in url or not url.startswith("https://"):
            raise LLMFailure("DASHSCOPE_BASE_URL 未配置为有效的百炼 HTTPS 业务空间地址。")

    def _request(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.settings.dashscope_api_key}", "Content-Type": "application/json"}
        url = self.settings.dashscope_base_url.rstrip("/") + "/chat/completions"
        transient = {408, 429, 500, 502, 503, 504}
        for attempt in range(max(0, self.settings.qwen_max_retries) + 1):
            try:
                client = self._client or httpx.Client(timeout=self.settings.qwen_timeout_seconds)
                try:
                    result = client.post(url, headers=headers, json=payload)
                finally:
                    if self._client is None:
                        client.close()
                if result.status_code in transient and attempt < self.settings.qwen_max_retries:
                    sleep(min(2**attempt, 4))
                    continue
                if result.status_code >= 400:
                    raise LLMFailure(f"百炼返回 HTTP {result.status_code}；请检查地域、模型授权及额度。")
                return result.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < self.settings.qwen_max_retries:
                    sleep(min(2**attempt, 4))
                    continue
                raise LLMFailure(f"百炼网络连接失败：{type(exc).__name__}") from exc
        raise LLMFailure("百炼请求重试次数已用尽。")

    def call_json(
        self, *, task: str, system_prompt: str, user_data: dict,
        schema: type[T], session: Session, project_id: str | None = None,
    ) -> T:
        model = self.settings.model_for(task)
        body = json.dumps(user_data, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256((task + system_prompt + body).encode("utf-8")).hexdigest()
        start = perf_counter()
        input_tokens: int | None = None
        output_tokens: int | None = None
        failure: str | None = None
        status = "failed"
        try:
            self._check_config()
            response = self._request({
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__.lower(),
                        "strict": True,
                        "schema": strict_json_schema(schema.model_json_schema()),
                    },
                },
            })
            choices = response.get("choices") or []
            if not choices:
                raise LLMFailure("模型返回空候选。")
            choice = choices[0]
            if choice.get("finish_reason") not in (None, "stop"):
                raise LLMFailure("模型未正常完成生成，请缩短输入或调整配额。")
            content = choice.get("message", {}).get("content")
            if not content or not isinstance(content, str):
                raise LLMFailure("模型没有返回预期的 JSON 文本。")
            usage = response.get("usage") or {}
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            parsed = schema.model_validate_json(content)
            status = "success"
            return parsed
        except LLMFailure as exc:
            failure = str(exc)
            raise
        except (ValidationError, ValueError, KeyError) as exc:
            failure = "模型返回内容不符合约定的 JSON 结构"
            raise LLMFailure(failure) from exc
        except Exception as exc:
            failure = f"云端请求异常：{type(exc).__name__}"
            logger.exception("Qwen task failed: %s", task)
            raise LLMFailure(failure) from exc
        finally:
            session.add(LLMCall(
                project_id=project_id, task=task, model=model,
                status=status, request_hash=digest,
                elapsed_ms=int((perf_counter() - start) * 1000),
                input_tokens=input_tokens, output_tokens=output_tokens,
                error=failure or "",
            ))
            session.commit()


def get_llm() -> QwenCloudAdapter:
    return QwenCloudAdapter()
