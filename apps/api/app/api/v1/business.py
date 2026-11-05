"""HTTP API for the first runnable release (script -> assets -> storyboard -> prompts)."""
from io import BytesIO
from pathlib import Path
import hashlib
import secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.qwen import QwenCloudAdapter, get_llm
from app.engines.spatial.guard import PromptConstraintError
from app.config import Settings, get_settings
from app.contracts import (
    AssetCreate, AssetPromptRequest, AssetUpdate, CandidateDecision,
    ExtractRequest, ProjectCreate, PromptApprove, ReferenceApprove,
    ScriptCreate, ShotCreate, ShotPlanRequest, ShotPromptRequest, ShotUpdate,
)
from app.database import get_db
from app.models import (
    Asset, Candidate, ExtractionRun, LLMCall, Project, PromptVersion,
    ReferenceImage, ScriptVersion, Shot, StoryBeat,
)
from app.services.prompts import polish_asset, polish_shot, reference_manifest
from app.services.script import approve_candidate, extract_script
from app.services.spatial import validate_asset_locks, validate_shot
from app.services.storyboard import create_storyboard

router = APIRouter()


def require_token(request: Request, settings: Settings = Depends(get_settings), x_api_token: str | None = Header(default=None)):
    host = request.client.host if request.client else ""
    if settings.app_allow_local_no_token and host in {"127.0.0.1", "::1", "testclient"}:
        return
    if not settings.app_api_token:
        raise HTTPException(503, "服务未配置 APP_API_TOKEN；请先设置强随机令牌。")
    if not x_api_token or not secrets.compare_digest(settings.app_api_token, x_api_token):
        raise HTTPException(401, "访问令牌无效。")


protected = APIRouter(dependencies=[Depends(require_token)])


def must_get(session: Session, model, identifier: str):
    obj = session.get(model, identifier)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} 不存在")
    return obj


def dto(obj) -> dict:
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


@router.get("/health")
def health(settings: Settings = Depends(get_settings)):
    return {"status": "ok", "version": "1.0.0", "qwen_configured": bool(settings.dashscope_api_key and settings.dashscope_base_url)}


@protected.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    return [dto(row) for row in db.scalars(select(Project).order_by(Project.created_at.desc()))]


@protected.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    obj = Project(**body.model_dump())
    db.add(obj)
    db.commit()
    return dto(obj)


@protected.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    return dto(must_get(db, Project, project_id))


@protected.get("/projects/{project_id}/scripts")
def list_scripts(project_id: str, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    return [dto(row) for row in db.scalars(select(ScriptVersion).where(ScriptVersion.project_id == project_id).order_by(ScriptVersion.version.desc()))]


@protected.post("/projects/{project_id}/scripts", status_code=201)
def add_script(project_id: str, body: ScriptCreate, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    version = db.scalar(select(func.max(ScriptVersion.version)).where(ScriptVersion.project_id == project_id)) or 0
    obj = ScriptVersion(project_id=project_id, version=version + 1, text=body.text)
    db.add(obj)
    db.commit()
    return dto(obj)


@protected.post("/scripts/{script_id}/extract")
def run_extraction(script_id: str, body: ExtractRequest, db: Session = Depends(get_db), llm: QwenCloudAdapter = Depends(get_llm)):
    script = must_get(db, ScriptVersion, script_id)
    run = extract_script(db, llm, script, force=body.force)
    return extraction_payload(db, run)


def extraction_payload(db: Session, run: ExtractionRun):
    return {
        "run": dto(run),
        "candidates": [dto(c) for c in db.scalars(select(Candidate).where(Candidate.run_id == run.id).order_by(Candidate.created_at, Candidate.id))],
        "beats": [dto(b) for b in db.scalars(select(StoryBeat).where(StoryBeat.run_id == run.id).order_by(StoryBeat.source_start))],
    }


@protected.get("/scripts/{script_id}/extraction")
def get_extraction(script_id: str, db: Session = Depends(get_db)):
    must_get(db, ScriptVersion, script_id)
    run = db.scalar(select(ExtractionRun).where(ExtractionRun.script_id == script_id).order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc()))
    return extraction_payload(db, run) if run else {"run": None, "candidates": [], "beats": []}


@protected.post("/candidates/{candidate_id}/approve")
def approve(candidate_id: str, body: CandidateDecision, db: Session = Depends(get_db)):
    candidate = must_get(db, Candidate, candidate_id)
    existing = None
    if body.existing_asset_id:
        existing = must_get(db, Asset, body.existing_asset_id)
        run = must_get(db, ExtractionRun, candidate.run_id)
        source_script = must_get(db, ScriptVersion, run.script_id)
        if existing.project_id != source_script.project_id:
            raise HTTPException(400, "跨项目资产不能合并。")
    try:
        asset = approve_candidate(db, candidate, existing, body.name_override)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return dto(asset)


@protected.post("/candidates/{candidate_id}/reject")
def reject(candidate_id: str, db: Session = Depends(get_db)):
    obj = must_get(db, Candidate, candidate_id)
    if obj.status == "approved":
        raise HTTPException(409, "已审核的候选不可直接拒绝，请使用资产归档。")
    obj.status = "rejected"
    db.commit()
    return dto(obj)


@protected.get("/projects/{project_id}/assets")
def list_assets(project_id: str, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    return [dto(a) for a in db.scalars(select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at, Asset.id))]


@protected.post("/projects/{project_id}/assets", status_code=201)
def manual_asset(project_id: str, body: AssetCreate, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    obj = Asset(project_id=project_id, **body.model_dump())
    db.add(obj)
    db.commit()
    return dto(obj)


@protected.get("/assets/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    return dto(must_get(db, Asset, asset_id))


@protected.patch("/assets/{asset_id}")
def edit_asset(asset_id: str, body: AssetUpdate, db: Session = Depends(get_db)):
    asset = must_get(db, Asset, asset_id)
    if body.revision != asset.revision:
        raise HTTPException(409, "资产已由其他操作修改，请刷新后重试。")
    changes = body.model_dump(exclude_unset=True, exclude={"revision"})
    for key, value in changes.items():
        setattr(asset, key, value)
    asset.revision += 1
    db.commit()
    return dto(asset)


@protected.post("/assets/{asset_id}/image-prompts")
def create_asset_prompt(asset_id: str, body: AssetPromptRequest, db: Session = Depends(get_db), llm: QwenCloudAdapter = Depends(get_llm)):
    asset = must_get(db, Asset, asset_id)
    try:
        return dto(polish_asset(db, llm, asset, body.target_image_model, body.request))
    except PromptConstraintError as exc:
        raise HTTPException(422, f"提示词与锁定事实冲突：{exc}") from exc


@protected.get("/assets/{asset_id}/references")
def list_asset_references(asset_id: str, db: Session = Depends(get_db)):
    must_get(db, Asset, asset_id)
    return [dto(x) | {"path": None} for x in db.scalars(select(ReferenceImage).where(ReferenceImage.asset_id == asset_id).order_by(ReferenceImage.created_at.desc()))]


@protected.post("/assets/{asset_id}/references", status_code=201)
def upload_reference(
    asset_id: str,
    role: str = "identity",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    must_get(db, Asset, asset_id)
    allowed_roles = {"identity", "pose", "costume", "composition", "environment", "prop", "first_frame"}
    if role not in allowed_roles:
        raise HTTPException(422, "不支持的参考图用途。")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    raw = file.file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, "上传图片超过大小限制。")
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        if image.width * image.height > 20_000_000:
            raise HTTPException(413, "图片像素尺寸超过限制。")
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise HTTPException(415, "仅支持 JPEG、PNG、WEBP 图片。")
        converted = image.convert("RGB")
        output = BytesIO()
        converted.save(output, format="JPEG", quality=90, optimize=True)
        content = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(415, "文件不是有效图片。") from exc
    directory = Path(settings.media_dir).resolve() / asset_id
    directory.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(content).hexdigest()
    file_path = directory / f"{checksum}.jpg"
    file_path.write_bytes(content)
    entry = ReferenceImage(
        asset_id=asset_id, path=str(file_path),
        original_filename=Path(file.filename or "reference.jpg").name[:250],
        role=role, mime_type="image/jpeg", checksum=checksum,
    )
    db.add(entry)
    db.commit()
    return dto(entry) | {"path": None}


@protected.post("/references/{ref_id}/review")
def review_reference(ref_id: str, body: ReferenceApprove, db: Session = Depends(get_db)):
    reference = must_get(db, ReferenceImage, ref_id)
    reference.approved = body.approved
    db.commit()
    return dto(reference) | {"path": None}


@protected.get("/references/{ref_id}/file")
def get_reference_file(ref_id: str, db: Session = Depends(get_db)):
    obj = must_get(db, ReferenceImage, ref_id)
    path = Path(obj.path)
    if not path.is_file():
        raise HTTPException(404, "文件未找到")
    return FileResponse(path, media_type=obj.mime_type, filename=obj.original_filename, content_disposition_type="inline")


@protected.post("/scripts/{script_id}/storyboard")
def plan_storyboard(script_id: str, body: ShotPlanRequest, db: Session = Depends(get_db), llm: QwenCloudAdapter = Depends(get_llm)):
    script = must_get(db, ScriptVersion, script_id)
    try:
        shots = create_storyboard(db, llm, script, body.count_limit, body.force)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return [dto(s) for s in shots]


@protected.get("/projects/{project_id}/shots")
def list_shots(project_id: str, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    return [dto(s) for s in db.scalars(select(Shot).where(Shot.project_id == project_id).order_by(Shot.created_at, Shot.ordinal))]


@protected.post("/projects/{project_id}/shots", status_code=201)
def add_shot(project_id: str, body: ShotCreate, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    script = must_get(db, ScriptVersion, body.script_id)
    if script.project_id != project_id:
        raise HTTPException(422, "剧本不属于当前项目。")
    for aid in body.asset_ids:
        asset = must_get(db, Asset, aid)
        if asset.project_id != project_id:
            raise HTTPException(422, "分镜不能关联其他项目的资产。")
    obj = Shot(project_id=project_id, **body.model_dump(exclude={"camera", "constraints", "start_state", "end_state"}),
               camera=body.camera.model_dump(), constraints=[c.model_dump() for c in body.constraints],
               start_state=[s.model_dump() for s in body.start_state],
               end_state=[s.model_dump() for s in body.end_state])
    db.add(obj)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "该剧本已经存在相同序号的分镜。") from exc
    return dto(obj)


@protected.patch("/shots/{shot_id}")
def edit_shot(shot_id: str, body: ShotUpdate, db: Session = Depends(get_db)):
    shot = must_get(db, Shot, shot_id)
    if body.revision != shot.revision:
        raise HTTPException(409, "分镜版本冲突，请刷新后重试。")
    for ref_id in body.reference_ids or []:
        ref = must_get(db, ReferenceImage, ref_id)
        owner = must_get(db, Asset, ref.asset_id)
        if owner.project_id != shot.project_id or owner.id not in (body.asset_ids or shot.asset_ids):
            raise HTTPException(422, "参考图不属于当前分镜关联的资产。")
    for aid in body.asset_ids or []:
        asset = must_get(db, Asset, aid)
        if asset.project_id != shot.project_id:
            raise HTTPException(422, "不能关联其他项目资产。")
    updates = body.model_dump(exclude_unset=True, exclude={"revision"})
    for key, value in updates.items():
        setattr(shot, key, value)
    shot.revision += 1
    db.commit()
    return dto(shot)


@protected.get("/shots/{shot_id}/validate")
def validate(shot_id: str, db: Session = Depends(get_db)):
    shot = must_get(db, Shot, shot_id)
    previous = db.scalar(
        select(Shot).where(Shot.script_id == shot.script_id, Shot.ordinal < shot.ordinal).order_by(Shot.ordinal.desc())
    )
    assets = [db.get(Asset, aid) for aid in shot.asset_ids]
    findings = validate_shot(shot, previous) + validate_asset_locks(
        shot, [asset for asset in assets if asset is not None]
    )
    return {"shot_id": shot.id, "findings": findings, "has_errors": any(x["level"] == "error" for x in findings)}


@protected.get("/shots/{shot_id}/reference-manifest")
def get_manifest(shot_id: str, db: Session = Depends(get_db)):
    shot = must_get(db, Shot, shot_id)
    return reference_manifest(db, shot)


@protected.post("/shots/{shot_id}/prompts")
def create_shot_prompt(shot_id: str, body: ShotPromptRequest, db: Session = Depends(get_db), llm: QwenCloudAdapter = Depends(get_llm)):
    shot = must_get(db, Shot, shot_id)
    previous = db.scalar(select(Shot).where(Shot.script_id == shot.script_id, Shot.ordinal < shot.ordinal).order_by(Shot.ordinal.desc()))
    assets = [db.get(Asset, aid) for aid in shot.asset_ids]
    findings = validate_shot(shot, previous) + validate_asset_locks(
        shot, [asset for asset in assets if asset is not None]
    )
    errors = [x for x in findings if x["level"] == "error"]
    if errors:
        raise HTTPException(422, {"reason": "分镜空间约束冲突", "findings": errors})
    try:
        return dto(polish_shot(db, llm, shot, body.purpose, body.user_guidance))
    except PromptConstraintError as exc:
        raise HTTPException(422, f"提示词与空间约束冲突：{exc}") from exc


@protected.get("/prompts")
def list_prompts(owner_kind: str, owner_id: str, db: Session = Depends(get_db)):
    if owner_kind not in {"shot", "asset"}:
        raise HTTPException(422, "owner_kind 必须是 shot 或 asset")
    must_get(db, Shot if owner_kind == "shot" else Asset, owner_id)
    rows = db.scalars(
        select(PromptVersion).where(PromptVersion.owner_kind == owner_kind, PromptVersion.owner_id == owner_id)
        .order_by(PromptVersion.created_at.desc(), PromptVersion.version.desc())
    )
    return [dto(x) for x in rows]


@protected.post("/prompts/{prompt_id}/review")
def approve_prompt(prompt_id: str, body: PromptApprove, db: Session = Depends(get_db)):
    prompt = must_get(db, PromptVersion, prompt_id)
    prompt.approved = body.approved
    db.commit()
    return dto(prompt)


@protected.get("/projects/{project_id}/llm-calls")
def audit_llm(project_id: str, db: Session = Depends(get_db)):
    must_get(db, Project, project_id)
    return [dto(x) for x in db.scalars(
        select(LLMCall).where(LLMCall.project_id == project_id).order_by(LLMCall.created_at.desc()).limit(100)
    )]


router.include_router(protected)
