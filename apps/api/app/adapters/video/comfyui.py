"""Config-driven ComfyUI adapter. No GPU server URL is accepted from the client."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings


class ComfyError(Exception):
    """A safe-to-display ComfyUI integration failure."""


@dataclass(frozen=True)
class GpuNode:
    id: str
    name: str
    base_url: str
    models: tuple[str, ...]
    enabled: bool
    timeout_seconds: float


def load_nodes(settings: Settings | None = None) -> list[GpuNode]:
    settings = settings or get_settings()
    path = Path(settings.comfyui_nodes_file)
    if not path.is_file():
        raise ComfyError(f"GPU 节点配置不存在：{path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        nodes: list[GpuNode] = []
        used: set[str] = set()
        for item in raw.get("nodes", []):
            url = item["base_url"].rstrip("/")
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("GPU 节点地址必须是 HTTP(S) URL")
            identifier = item["id"]
            if identifier in used:
                raise ValueError(f"重复 GPU 节点 ID：{identifier}")
            used.add(identifier)
            nodes.append(GpuNode(
                id=identifier,
                name=item.get("name", identifier),
                base_url=url,
                models=tuple(item.get("models", [])),
                enabled=bool(item.get("enabled", True)),
                timeout_seconds=float(item.get("timeout_seconds", 60)),
            ))
        return nodes
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ComfyError("GPU 节点 JSON 配置无效") from exc


def select_node(node_id: str | None, workflow_id: str, settings: Settings) -> GpuNode:
    matches = [
        item for item in load_nodes(settings)
        if item.enabled and workflow_id in item.models
    ]
    if node_id:
        matches = [item for item in matches if item.id == node_id]
    if not matches:
        raise ComfyError("没有启用且支持该工作流的 GPU 节点，请检查配置")
    return matches[0]


def workflow_root(settings: Settings) -> Path:
    return Path(settings.comfyui_workflow_root).resolve()


def available_workflows(settings: Settings) -> list[dict[str, Any]]:
    directory = workflow_root(settings) / "manifests"
    result = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        filename = workflow_root(settings) / data["workflow_file"]
        result.append({
            "id": data["id"],
            "name": data.get("name", data["id"]),
            "ready": filename.is_file(),
            "max_images": len(data.get("image_load_nodes", [])),
        })
    return result


def get_workflow(workflow_id: str, settings: Settings) -> tuple[dict, dict]:
    # Workflow name is a simple identifier, not a path supplied by a user.
    if not workflow_id or not all(c.isalnum() or c in "_-" for c in workflow_id):
        raise ComfyError("非法工作流 ID")
    path = workflow_root(settings) / "manifests" / (workflow_id + ".json")
    if not path.is_file():
        raise ComfyError(f"找不到工作流映射：{workflow_id}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("id") != workflow_id:
        raise ComfyError("工作流映射 ID 不匹配")
    workflow_file = (workflow_root(settings) / manifest["workflow_file"]).resolve()
    if not workflow_file.is_relative_to(workflow_root(settings)):
        raise ComfyError("工作流文件超出允许目录")
    if not workflow_file.is_file():
        raise ComfyError("请先在 ComfyUI 中导出 API 格式 workflow_api.json")
    graph = json.loads(workflow_file.read_text(encoding="utf-8"))
    if "nodes" in graph or not isinstance(graph, dict):
        raise ComfyError("工作流不是 API 格式（请使用 Export Workflow API）")
    return manifest, graph


def compile_workflow(
    manifest: dict, graph: dict, prompt: str,
    image_names: list[str], seed: int | None = None,
) -> dict:
    """Bind approved references to configured LoadImage nodes and prompt input."""
    output = copy.deepcopy(graph)
    prompt_node = str(manifest["prompt_node"])
    prompt_field = manifest.get("prompt_field", "prompt")
    try:
        output[prompt_node]["inputs"][prompt_field] = prompt
        image_slots = [str(n) for n in manifest.get("image_load_nodes", [])]
        if len(image_names) > len(image_slots):
            raise ComfyError("参考图数量超过该工作流支持的输入槽位")
        for index, name in enumerate(image_names):
            output[image_slots[index]]["inputs"]["image"] = name
        if seed is not None:
            for mapping in manifest.get("seed_bindings", []):
                output[str(mapping["node_id"])]["inputs"][mapping["field"]] = seed
    except (KeyError, TypeError) as exc:
        raise ComfyError("工作流节点 ID 或字段与映射文件不一致") from exc
    return output


class ComfyClient:
    def __init__(self, node: GpuNode, client: httpx.Client | None = None):
        self.node = node
        self._client = client

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not path.startswith("/") or path.startswith("//"):
            raise ComfyError("非法 ComfyUI 接口路径")
        client = self._client or httpx.Client(timeout=self.node.timeout_seconds)
        try:
            response = client.request(method, self.node.base_url + path, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, ValueError) as exc:
            raise ComfyError(f"ComfyUI 请求失败：{type(exc).__name__}") from exc
        finally:
            if self._client is None:
                client.close()

    def upload_image(self, path: Path) -> str:
        with path.open("rb") as stream:
            response = self.request(
                "POST", "/upload/image",
                files={"image": (path.name, stream, "image/jpeg")},
                data={"overwrite": "false"},
            )
        data = response.json()
        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise ComfyError("ComfyUI 未返回上传文件名")
        return name

    def submit(self, graph: dict, client_id: str) -> str:
        data = self.request(
            "POST", "/prompt", json={"prompt": graph, "client_id": client_id}
        ).json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            details = str(data.get("node_errors", {}))[:500]
            raise ComfyError("ComfyUI 拒绝工作流：" + details)
        return str(prompt_id)

    def history(self, prompt_id: str) -> dict | None:
        data = self.request("GET", f"/history/{prompt_id}").json()
        return data.get(prompt_id)

    def download(self, output: dict) -> bytes:
        params = {
            "filename": output["filename"],
            "subfolder": output.get("subfolder", ""),
            "type": output.get("type", "output"),
        }
        return self.request("GET", "/view", params=params).content


def result_artifacts(history: dict, output_nodes: list[str]) -> list[dict]:
    results = []
    for node_id, info in history.get("outputs", {}).items():
        if output_nodes and node_id not in output_nodes:
            continue
        for key in ("videos", "gifs", "images", "audio"):
            for item in info.get(key, []):
                if isinstance(item, dict) and item.get("filename"):
                    results.append(item)
    return results
