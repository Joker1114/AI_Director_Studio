"""Authentication, cloud failure and immutable storyboard safeguards."""
import json

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.adapters.qwen import LLMFailure, QwenCloudAdapter
from app.config import Settings, get_settings
from app.contracts import PolishResult
from app.database import Base, get_db
from app.main import app
from app.models import LLMCall


def test_token_is_required_when_local_bypass_disabled():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def isolated_db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_api_token="valid-unit-test-token", app_allow_local_no_token=False
    )
    try:
        with TestClient(app) as http:
            assert http.get("/api/projects").status_code == 401
            assert http.get("/api/projects", headers={"X-API-Token": "wrong"}).status_code == 401
            assert http.get("/api/projects", headers={"X-API-Token": "valid-unit-test-token"}).status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_invalid_cloud_json_has_audit_entry():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def response(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({"wrong_field": "bad"})}, "finish_reason": "stop"}]
        })

    settings = Settings(
        dashscope_api_key="test", dashscope_base_url="https://localhost.invalid/compatible-mode/v1"
    )
    with httpx.Client(transport=httpx.MockTransport(response)) as client, Session(engine) as session:
        qwen = QwenCloudAdapter(settings=settings, client=client)
        try:
            qwen.call_json(task="asset_image_prompt", system_prompt="test", user_data={}, schema=PolishResult, session=session)
        except LLMFailure as exc:
            assert "JSON" in str(exc)
        else:
            raise AssertionError("invalid schema must fail")
        assert session.scalar(select(LLMCall)).status == "failed"
