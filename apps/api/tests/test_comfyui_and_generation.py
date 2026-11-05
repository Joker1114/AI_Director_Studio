"""Workflow compilation, API queue, recovery, and mocked GPU execution."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.comfyui import (
    ComfyClient, ComfyError, GpuNode, compile_workflow,
    get_workflow, result_artifacts, select_node,
)
from app.config import Settings, get_settings
from app.database import Base, get_db
from app.engines.spatial.guard import PromptConstraintError, validate_creative_prompt
from app.main import app
from app.models import (
    Asset, GenerationJob, Project, PromptVersion, ReferenceImage,
    ScriptVersion, Shot,
)
from app.workers import generation


def create_configuration(tmp_path: Path) -> Settings:
    nodes_file = tmp_path / "gpu_nodes.json"
    nodes_file.write_text(json.dumps({"nodes": [{
        "id": "gpu-test", "name": "GPU Test", "base_url": "http://127.0.0.1:8188",
        "enabled": True, "models": ["minimax_h3"],
    }]}), encoding="utf8")
    root = tmp_path / "workflows"
    (root / "manifests").mkdir(parents=True)
    (root / "videos").mkdir()
    (root / "manifests" / "minimax_h3.json").write_text(json.dumps({
        "id": "minimax_h3", "workflow_file": "videos/api.json",
        "prompt_node": "10", "prompt_field": "text", "image_load_nodes": ["11"],
        "seed_bindings": [{"node_id": "12", "field": "seed"}],
        "output_nodes": ["364"],
    }), encoding="utf8")
    (root / "videos" / "api.json").write_text(json.dumps({
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "11": {"class_type": "LoadImage", "inputs": {"image": ""}},
        "12": {"class_type": "KSampler", "inputs": {"seed": 0}},
    }), encoding="utf8")
    return Settings(
        comfyui_nodes_file=str(nodes_file),
        comfyui_workflow_root=str(root),
        generation_dir=str(tmp_path / "results"),
        app_api_token="test-token", app_allow_local_no_token=False,
    )


def test_workflow_compiler_and_node_config(tmp_path):
    settings = create_configuration(tmp_path)
    node = select_node(None, "minimax_h3", settings)
    assert node.id == "gpu-test"
    manifest, graph = get_workflow("minimax_h3", settings)
    output = compile_workflow(manifest, graph, "雨夜公交站", ["reference.jpg"], 1234)
    assert output["10"]["inputs"]["text"] == "雨夜公交站"
    assert output["11"]["inputs"]["image"] == "reference.jpg"
    assert output["12"]["inputs"]["seed"] == 1234
    assert graph["11"]["inputs"]["image"] == ""
    with pytest.raises(ComfyError):
        compile_workflow(manifest, graph, "test", ["a.jpg", "b.jpg"])


def test_comfyui_http_client_mocked():
    requests = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/prompt":
            data = json.loads(request.content)
            assert data["prompt"]["10"]["inputs"]["text"] == "Test"
            return httpx.Response(200, json={"prompt_id": "comfy-123"})
        if request.url.path.startswith("/history/"):
            return httpx.Response(200, json={"comfy-123": {"outputs": {
                "364": {"gifs": [{"filename": "demo.mp4", "type": "output", "subfolder": ""}]}
            }}})
        if request.url.path == "/view":
            return httpx.Response(200, content=b"mock-video-bytes")
        return httpx.Response(404)

    node = GpuNode("gpu-test", "mock", "https://gpu.invalid", ("minimax_h3",), True, 5)
    with httpx.Client(transport=httpx.MockTransport(responder)) as http:
        client = ComfyClient(node, client=http)
        assert client.submit({"10": {"inputs": {"text": "Test"}}}, "client") == "comfy-123"
        history = client.history("comfy-123")
        files = result_artifacts(history, ["364"])
        assert client.download(files[0]) == b"mock-video-bytes"
    assert ("POST", "/prompt") in requests


def test_generation_api_and_worker_with_mock_gpu(tmp_path, monkeypatch):
    settings = create_configuration(tmp_path)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    image_path = tmp_path / "reference.jpg"
    image_path.write_bytes(b"mock-image")

    with sessions() as db:
        project = Project(title="悬疑短剧", style_guide="写实")
        db.add(project); db.flush()
        script = ScriptVersion(project_id=project.id, version=1, text="女孩坐在站台上，远处站着男人。")
        db.add(script); db.flush()
        asset = Asset(project_id=project.id, kind="scene", name="站台", locked_fields={})
        db.add(asset); db.flush()
        reference = ReferenceImage(
            asset_id=asset.id, path=str(image_path), original_filename="reference.jpg",
            role="environment", mime_type="image/jpeg", checksum="abc", approved=True,
        )
        db.add(reference); db.flush()
        shot = Shot(
            project_id=project.id, script_id=script.id, ordinal=1, narrative="男人远景",
            asset_ids=[asset.id], reference_ids=[reference.id], constraints=[],
            camera={}, start_state=[], end_state=[],
        )
        db.add(shot); db.flush()
        prompt = PromptVersion(
            owner_kind="shot", owner_id=shot.id, purpose="shot_video", version=1,
            raw_prompt="远处男人", compiled_prompt="画面右侧是站台", model="test", approved=True,
            manifest=[{"slot": 1, "reference_id": reference.id, "asset_id": asset.id,
                       "asset_name": asset.name, "role": "environment"}],
            constraints_snapshot=[],
        )
        db.add(prompt); db.commit()
        shot_id, prompt_id, project_id = shot.id, prompt.id, project.id

    def dependency():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as http:
            headers = {"X-API-Token": "test-token"}
            assert http.get("/api/v1/gpu-nodes", headers=headers).status_code == 200
            assert http.get("/api/v1/workflows", headers=headers).json()[0]["ready"]
            response = http.post("/api/v1/generation-jobs", headers=headers, json={
                "shot_id": shot_id, "prompt_version_id": prompt_id,
                "workflow_id": "minimax_h3", "seed": 3,
            })
            assert response.status_code == 201, response.text
            job_id = response.json()["id"]
            assert response.json()["status"] == "queued"
    finally:
        app.dependency_overrides.clear()

    class FakeComfy:
        def __init__(self, node):
            assert node.id == "gpu-test"

        def upload_image(self, path):
            assert path.read_bytes() == b"mock-image"
            return "comfy_uploaded.jpg"

        def submit(self, graph, client_id):
            assert graph["11"]["inputs"]["image"] == "comfy_uploaded.jpg"
            assert graph["10"]["inputs"]["text"] == "画面右侧是站台"
            return "gpu-prompt-001"

        def history(self, prompt_id):
            return {"outputs": {"364": {"gifs": [{"filename": "render.mp4"}]}}}

        def download(self, output):
            return b"video-result"

    monkeypatch.setattr(generation, "ComfyClient", FakeComfy)
    with sessions() as db:
        assert generation.process_once(db, settings)
        job = db.get(GenerationJob, job_id)
        assert job.status == "succeeded"
        assert job.result_files == ["result_0.mp4"]
        assert (Path(settings.generation_dir) / job_id / "result_0.mp4").read_bytes() == b"video-result"

    with sessions() as db:
        row = db.get(GenerationJob, job_id)
        row.status = "running"
        db.commit()
        assert generation.recover_incomplete_jobs(db) == 1
        assert row.status == "queued"
    engine.dispose()


def test_prompt_guard_rejects_locked_scene_and_umbrella_errors():
    with pytest.raises(PromptConstraintError):
        validate_creative_prompt("公交站位于画面左侧，女孩坐在长椅上", [("公交站", {"screen_side": "right"})])
    with pytest.raises(PromptConstraintError):
        validate_creative_prompt("男人手指僵直，雨伞悬空漂浮在头顶", [], [
            {"type": "contact", "subject": "男人右手", "target": "伞柄", "locked": True}
        ])
    validate_creative_prompt("公交站位于画面右侧。男人站在远景，右手握住伞柄。", [
        ("公交站", {"screen_side": "right"})
    ])
