"""Isolated in-memory API test database; no cloud requests or personal secrets."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.qwen import get_llm
from app.config import Settings, get_settings
from app.contracts import (
    ExtractResult, ExtractedAsset, ExtractedBeat, PolishResult,
    StoryboardResult, ShotDraft, Camera, SpatialConstraint, StateFact,
)
from app.database import Base, get_db
from app.main import app


class FakeLLM:
    def __init__(self):
        self.settings = Settings(
            qwen_model_complex="qwen3.8-max", qwen_model_fast="qwen3.8-flash",
        )
        self.calls = []

    def call_json(self, *, task, system_prompt, user_data, schema, session, project_id):
        self.calls.append(task)
        if schema is ExtractResult:
            return ExtractResult(assets=[
                ExtractedAsset(kind="character", name="女孩", description="在公交站等车", source_quote="女孩坐在长椅上", aliases=["她"], facts=["坐在长椅上"]),
                ExtractedAsset(kind="scene", name="公交站", description="雨夜公交站", source_quote="公交站", aliases=[], facts=["雨夜"]),
                ExtractedAsset(kind="prop", name="雨伞", description="黑伞", source_quote="黑伞", aliases=[], facts=["黑色"]),
                ExtractedAsset(kind="prop", name="臆造道具", description="不存在", source_quote="剧本中绝对不存在的片段", aliases=[], facts=[]),
            ], beats=[ExtractedBeat(narrative="女孩发现男人", source_quote="看到远处的男人", scene_name="公交站")])
        if schema is StoryboardResult:
            return StoryboardResult(shots=[
                ShotDraft(
                    narrative="女孩注意到远处男人",duration_seconds=5,
                    camera=Camera(shot_size="extreme_wide",angle="eye_level",movement="static",axis="bus_stop_A"),
                    constraints=[
                        SpatialConstraint(type="screen_side",subject="公交站",relation="screen_side",value="right"),
                        SpatialConstraint(type="scale",subject="男人",relation="height_fraction",value="0.10"),
                        SpatialConstraint(type="contact",subject="男人.右手",relation="grips",target="雨伞.伞柄",value="持续接触"),
                    ],
                    asset_names=["女孩", "公交站", "雨伞"],
                    start_state=[StateFact(subject="女孩",attribute="pose",value="sitting")],
                    end_state=[StateFact(subject="女孩",attribute="pose",value="sitting")],
                    transition="eyeline_match",
                )
            ])
        if schema is PolishResult:
            return PolishResult(creative_prompt="电影质感的雨夜公交站，人物神情自然，远处的伞与右手保持接触。", notes=["保持空间事实"])
        raise AssertionError(task)


@pytest.fixture()
def client() -> Iterator[tuple[TestClient, FakeLLM]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    fake = FakeLLM()

    def override_db():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm] = lambda: fake
    app.dependency_overrides[get_settings] = lambda: Settings(app_allow_local_no_token=True, app_api_token="")
    with TestClient(app) as test_client:
        yield test_client, fake
    app.dependency_overrides.clear()
    engine.dispose()
