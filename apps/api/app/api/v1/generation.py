"""Authenticated generation jobs. Cloud service owns GPU credentials and storage."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.comfyui import (
    ComfyError, available_workflows, get_workflow, load_nodes, select_node,
)
from app.api.v1.business import dto, must_get, require_token
from app.config import Settings, get_settings
from app.database import get_db
from app.models import GenerationJob, PromptVersion, Project, Shot

router = APIRouter(dependencies=[Depends(require_token)], tags=["generation"])


class GenerateBody(BaseModel):
    shot_id: str
    prompt_version_id: str
    workflow_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    node_id: str | None = None
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


def safe_job(job: GenerationJob) -> dict:
    result = dto(job)
    result["result_files"] = [
        {"index": i, "filename": Path(name).name}
        for i, name in enumerate(job.result_files or [])
    ]
    return result


@router.get("/gpu-nodes")
def gpu_nodes(settings: Settings = Depends(get_settings)):
    try:
        return [{
            "id": node.id, "name": node.name, "models": node.models,
            "enabled": node.enabled,
        } for node in load_nodes(settings)]
    except ComfyError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/workflows")
def workflows(settings: Settings = Depends(get_settings)):
    try:
        return available_workflows(settings)
    except (ComfyError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/generation-jobs", status_code=201)
def create_job(
    body: GenerateBody, db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    shot = must_get(db, Shot, body.shot_id)
    prompt = must_get(db, PromptVersion, body.prompt_version_id)
    if prompt.owner_kind != "shot" or prompt.owner_id != shot.id:
        raise HTTPException(422, "提示词不属于当前分镜")
    if prompt.purpose != "shot_video":
        raise HTTPException(422, "视频生成需要 shot_video 提示词")
    if prompt.constraints_snapshot != shot.constraints:
        raise HTTPException(409, "镜头空间约束已变更，请重新生成并审核提示词")
    if not prompt.approved:
        raise HTTPException(409, "请先审核通过提示词")
    try:
        get_workflow(body.workflow_id, settings)
        node = select_node(body.node_id, body.workflow_id, settings)
    except ComfyError as exc:
        raise HTTPException(422, str(exc)) from exc
    job = GenerationJob(
        project_id=shot.project_id, shot_id=shot.id,
        prompt_version_id=prompt.id, workflow_id=body.workflow_id,
        node_id=node.id, seed=body.seed, status="queued", result_files=[],
    )
    db.add(job)
    db.commit()
    return safe_job(job)


@router.get("/projects/{project_id}/generation-jobs")
def list_jobs(project_id: str, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    rows = db.scalars(
        select(GenerationJob).where(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.created_at.desc()).limit(100)
    )
    return [safe_job(job) for job in rows]


@router.get("/generation-jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return safe_job(must_get(db, GenerationJob, job_id))


@router.post("/generation-jobs/{job_id}/retry")
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = must_get(db, GenerationJob, job_id)
    if job.status != "failed":
        raise HTTPException(409, "只能重试失败的任务")
    job.status = "queued"
    job.error = ""
    job.comfy_prompt_id = None
    job.result_files = []
    job.started_at = None
    job.finished_at = None
    db.commit()
    return safe_job(job)


@router.get("/generation-jobs/{job_id}/files/{index}")
def get_generated_file(
    job_id: str, index: int, db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    job = must_get(db, GenerationJob, job_id)
    paths = job.result_files or []
    if job.status != "succeeded" or index < 0 or index >= len(paths):
        raise HTTPException(404, "结果文件不存在")
    root = Path(settings.generation_dir).resolve()
    path = (root / job.id / paths[index]).resolve()
    if not path.is_relative_to(root / job.id) or not path.is_file():
        raise HTTPException(404, "结果文件不存在")
    return FileResponse(path, filename=path.name)
