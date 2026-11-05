"""Durable one-at-a-time ComfyUI worker; run separately from HTTP process.

For scaled/multi-worker production, partition GPU nodes or add per-node concurrency locks.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.adapters.comfyui import (
    ComfyClient, ComfyError, compile_workflow, get_workflow,
    result_artifacts, select_node,
)
from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import GenerationJob, PromptVersion, ReferenceImage, utcnow

logger = logging.getLogger(__name__)


def claim_job(db: Session) -> str | None:
    """Claim pending work; SKIP LOCKED is supported on PostgreSQL."""
    job = db.scalar(
        select(GenerationJob).where(GenerationJob.status == "queued")
        .order_by(GenerationJob.created_at, GenerationJob.id)
        .with_for_update(skip_locked=True).limit(1)
    )
    if job is None:
        return None
    job.status = "submitting"
    job.attempts += 1
    job.started_at = utcnow()
    db.commit()
    return job.id


def _process(job_id: str, db: Session, settings: Settings) -> None:
    job = db.get(GenerationJob, job_id)
    if job is None:
        return
    node = select_node(job.node_id, job.workflow_id, settings)
    manifest, graph = get_workflow(job.workflow_id, settings)
    prompt = db.get(PromptVersion, job.prompt_version_id)
    if prompt is None:
        raise ComfyError("任务提示词版本不存在")
    client = ComfyClient(node)
    uploaded = []
    for image in prompt.manifest or []:
        reference = db.get(ReferenceImage, image["reference_id"])
        if reference is None or not reference.approved:
            raise ComfyError("分镜绑定的参考图未通过审核")
        path = Path(reference.path)
        if not path.is_file():
            raise ComfyError("参考图文件已丢失")
        uploaded.append(client.upload_image(path))
    compiled = compile_workflow(manifest, graph, prompt.compiled_prompt, uploaded, job.seed)
    if not job.comfy_prompt_id:
        job.comfy_prompt_id = client.submit(compiled, client_id=f"ai-director-{job.id}")
        job.status = "running"
        db.commit()
    deadline = time.monotonic() + settings.generation_timeout_seconds
    while time.monotonic() < deadline:
        history = client.history(job.comfy_prompt_id)
        if history is None:
            time.sleep(settings.generation_poll_seconds)
            continue
        status = history.get("status", {})
        if status.get("status_str") == "error":
            raise ComfyError("ComfyUI 执行失败，请检查 GPU 服务端日志")
        outputs = result_artifacts(history, [str(x) for x in manifest.get("output_nodes", [])])
        if not outputs:
            raise ComfyError("ComfyUI 任务结束，但未找到配置的输出节点文件")
        directory = Path(settings.generation_dir) / job.id
        directory.mkdir(parents=True, exist_ok=True)
        stored = []
        for index, output in enumerate(outputs):
            suffix = Path(output["filename"]).suffix.lower()
            if suffix not in {".mp4", ".webm", ".png", ".jpg", ".jpeg", ".gif"}:
                raise ComfyError("输出文件类型不允许")
            filename = f"result_{index}{suffix}"
            (directory / filename).write_bytes(client.download(output))
            stored.append(filename)
        job.result_files = stored
        job.status = "succeeded"
        job.finished_at = utcnow()
        db.commit()
        return
    raise ComfyError("任务执行超时；原 GPU 任务可能仍在运行，请检查节点")


def process_once(db: Session, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    job_id = claim_job(db)
    if not job_id:
        return False
    try:
        _process(job_id, db, settings)
    except Exception as exc:
        logger.exception("Generation job %s failed", job_id)
        job = db.get(GenerationJob, job_id)
        if job:
            job.status = "failed"
            job.error = str(exc)[:500] if isinstance(exc, ComfyError) else "生成任务内部异常"
            job.finished_at = utcnow()
            db.commit()
    return True


def recover_incomplete_jobs(db: Session) -> int:
    """Single-worker startup recovery, keeping external ComfyUI prompt IDs."""
    result = db.execute(
        update(GenerationJob)
        .where(GenerationJob.status.in_(("submitting", "running")))
        .values(status="queued", error="", finished_at=None)
    )
    db.commit()
    return int(result.rowcount or 0)


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    with SessionLocal() as db:
        recovered = recover_incomplete_jobs(db)
        if recovered:
            logger.warning("Recovered %s unfinished generation jobs", recovered)
    while True:
        with SessionLocal() as db:
            processed = process_once(db, settings)
        if not processed:
            time.sleep(settings.generation_worker_idle_seconds)


if __name__ == "__main__":
    run_forever()
