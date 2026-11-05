"""Verify actual HTTP request contract via mock transport, without cloud credentials."""
import json

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters.qwen import LLMFailure, QwenCloudAdapter
from app.config import Settings
from app.contracts import ExtractResult
from app.database import Base
from app.models import LLMCall


def test_cloud_adapter_conforms_and_records_audit():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    inspected = {}

    def receive(request: httpx.Request) -> httpx.Response:
        inspected["url"] = str(request.url)
        inspected["auth"] = request.headers["Authorization"]
        inspected["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({"assets": [], "beats": []})}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 81, "completion_tokens": 20},
        })

    settings = Settings(
        dashscope_api_key="fake-for-unit-test",
        dashscope_base_url="https://localhost.invalid/compatible-mode/v1",
    )
    with httpx.Client(transport=httpx.MockTransport(receive)) as client:
        cloud = QwenCloudAdapter(settings=settings, client=client)
        with Session(engine) as session:
            result = cloud.call_json(task="script_extract", system_prompt="extract", user_data={"script": "text"}, schema=ExtractResult, session=session)
            assert result.assets == []
            assert inspected["url"].endswith("/chat/completions")
            assert inspected["auth"].startswith("Bearer ")
            assert inspected["body"]["model"] == "qwen3.8-max"
            spec = inspected["body"]["response_format"]["json_schema"]["schema"]
            assert spec["additionalProperties"] is False
            assert spec["$defs"]["ExtractedAsset"]["additionalProperties"] is False
            assert session.scalar(select(LLMCall)).status == "success"
            assert session.scalar(select(LLMCall)).input_tokens == 81


def test_missing_credentials_fail_with_actionable_message_and_audit():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    cloud = QwenCloudAdapter(settings=Settings(dashscope_api_key="", dashscope_base_url=""))
    with Session(engine) as session:
        with pytest.raises(LLMFailure, match="DASHSCOPE_API_KEY"):
            cloud.call_json(task="script_extract", system_prompt="a", user_data={}, schema=ExtractResult, session=session)
        assert session.scalar(select(LLMCall)).status == "failed"
