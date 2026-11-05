"""Prompt versions and deterministically compiled locked facts/reference bindings."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.qwen import QwenCloudAdapter
from app.engines.spatial.guard import validate_creative_prompt
from app.contracts import PolishResult
from app.models import Asset, Project, PromptVersion, ReferenceImage, Shot
from app.services.spatial import render_constraints

ASSET_SYSTEM = """你是电影级资产生图提示词编辑器。只处理输入资产：保持身份、外观已确定的事实与锁定字段，
不得擅自补充剧情外的身份事实。输出适合生图模型的创意描述，允许美术建议但与锁定属性不冲突。
只输出给定 JSON Schema。"""
SHOT_SYSTEM = """你是视频分镜提示词编辑器。请使用分镜叙事、景别、动作和参考资产生成准确可执行的提示词。
遵守每一项已锁定的空间关系、人物站位、道具接触，不要替换引用资产、不改变左右方位。
静态首帧只写单张画面构图；视频提示词强调时间演变与动作调度。不要输出擅自编造的<Picture N>编号，
引用绑定由程序在后续阶段完成。仅返回给定 JSON Schema。"""


def next_version(session: Session, owner_kind: str, owner_id: str, purpose: str) -> int:
    current = session.scalar(
        select(func.max(PromptVersion.version)).where(
            PromptVersion.owner_kind == owner_kind,
            PromptVersion.owner_id == owner_id,
            PromptVersion.purpose == purpose,
        )
    )
    return (current or 0) + 1


def polish_asset(session: Session, llm: QwenCloudAdapter, asset: Asset, target_model: str, request: str) -> PromptVersion:
    result = llm.call_json(
        task="asset_image_prompt",
        system_prompt=ASSET_SYSTEM,
        user_data={
            "kind": asset.kind,
            "name": asset.name,
            "description": asset.description,
            "facts": asset.facts,
            "locked_fields": asset.locked_fields,
            "image_model": target_model,
            "user_request": request,
            "project_style_guide": session.get(Project, asset.project_id).style_guide,
        },
        schema=PolishResult,
        session=session,
        project_id=asset.project_id,
    )
    validate_creative_prompt(result.creative_prompt, [(asset.name, asset.locked_fields)])
    anchors = [f"资产：{asset.kind} / {asset.name}"]
    anchors += [f"确认事实：{fact}" for fact in asset.facts]
    anchors += [f"[锁定] {key} = {value}" for key, value in sorted(asset.locked_fields.items())]
    compiled = "\n".join(anchors) + "\n\n生图创意描述：\n" + result.creative_prompt
    entry = PromptVersion(
        owner_kind="asset", owner_id=asset.id, purpose="asset_image",
        version=next_version(session, "asset", asset.id, "asset_image"),
        raw_prompt=result.creative_prompt,
        compiled_prompt=compiled,
        model=llm.settings.model_for("asset_image_prompt"),
        constraints_snapshot=[{"name": k, "value": v} for k, v in asset.locked_fields.items()],
        manifest=[],
    )
    session.add(entry)
    session.commit()
    return entry


def reference_manifest(session: Session, shot: Shot) -> list[dict]:
    """Never persist `<Picture N>` as permanent identity. Only approved images bind."""
    manifest: list[dict] = []
    selected = getattr(shot, "reference_ids", None) or []
    if selected:
        references = [session.get(ReferenceImage, rid) for rid in selected]
    else:
        references = []
        for asset_id in shot.asset_ids:
            ref = session.scalar(
                select(ReferenceImage).where(
                    ReferenceImage.asset_id == asset_id, ReferenceImage.approved.is_(True)
                ).order_by(ReferenceImage.created_at.desc(), ReferenceImage.id.desc())
            )
            if ref:
                references.append(ref)
    for ref in references:
        if ref is None or not ref.approved or ref.asset_id not in shot.asset_ids:
            continue
        asset = session.get(Asset, ref.asset_id)
        if asset is None:
            continue
        manifest.append({
            "slot": len(manifest) + 1,
            "asset_id": asset.id,
            "asset_name": asset.name,
            "reference_id": ref.id,
            "role": ref.role,
        })
        if len(manifest) == 9:
            break
    return manifest


def polish_shot(session: Session, llm: QwenCloudAdapter, shot: Shot, purpose: str, guidance: str) -> PromptVersion:
    linked_assets = [session.get(Asset, asset_id) for asset_id in shot.asset_ids]
    linked_assets = [a for a in linked_assets if a is not None]
    manifest = reference_manifest(session, shot)
    result = llm.call_json(
        task="shot_image_prompt" if purpose == "shot_still" else "shot_video_prompt",
        system_prompt=SHOT_SYSTEM,
        user_data={
            "purpose": purpose,
            "narrative": shot.narrative,
            "duration_seconds": shot.duration_seconds,
            "camera": shot.camera,
            "start_state": shot.start_state,
            "end_state": shot.end_state,
            "constraints": shot.constraints,
            "linked_assets": [{"id": a.id, "name": a.name, "facts": a.facts, "locked_fields": a.locked_fields} for a in linked_assets],
            "user_guidance": guidance,
            "project_style_guide": session.get(Project, shot.project_id).style_guide,
        },
        schema=PolishResult,
        session=session,
        project_id=shot.project_id,
    )
    validate_creative_prompt(
        result.creative_prompt,
        [(a.name, a.locked_fields) for a in linked_assets],
        shot.constraints,
    )
    reference_lines = [
        f"<Picture {item['slot']}> 是 {item['asset_name']} 的 {item['role']} 参考图（本次镜头专用序号）。"
        for item in manifest
    ]
    asset_anchors = [
        f"资产 {a.name}（{a.kind}）：" + "；".join(a.facts) +
        "。" + "；".join(f"[资产锁定] {key}={value}" for key, value in sorted(a.locked_fields.items()))
        for a in linked_assets
    ]
    title = "静态首帧生图提示词" if purpose == "shot_still" else "MiniMax H3 视频提示词"
    sections = [
        title,
        "参考图映射：\n" + ("\n".join(reference_lines) if reference_lines else "本镜头尚无已审核参考图"),
        "已确认资产信息：\n" + "\n".join(asset_anchors),
        "镜头事实：\n" + shot.narrative + "\n机位：" + str(shot.camera),
        "不可省略的空间与接触约束：\n" + render_constraints(shot.constraints),
        "动作开始：" + str(shot.start_state) + "\n动作结束：" + str(shot.end_state),
        "创意描述（不得覆盖上述锁定事实）：\n" + result.creative_prompt,
    ]
    entry = PromptVersion(
        owner_kind="shot", owner_id=shot.id, purpose=purpose,
        version=next_version(session, "shot", shot.id, purpose),
        raw_prompt=result.creative_prompt, compiled_prompt="\n\n".join(sections),
        model=llm.settings.model_for("shot_image_prompt" if purpose == "shot_still" else "shot_video_prompt"),
        manifest=manifest, constraints_snapshot=shot.constraints,
    )
    session.add(entry)
    session.commit()
    return entry
