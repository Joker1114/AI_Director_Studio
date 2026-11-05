"""Generate and persist structured shots from a script and approved assets."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.qwen import QwenCloudAdapter
from app.contracts import StoryboardResult
from app.models import Asset, Project, ScriptVersion, Shot

SHOT_SYSTEM = """你是电影分镜导演。根据剧本事件按叙事必要性拆镜，不能每句机械拆一镜。
分镜要指定人物的前后状态、镜头语言和可解释的空间/持物约束。只使用传入的资产名称，不要发明资产。
当人物首次出场时，设计察觉、显露或建立镜头以避免突兀。场景中的左右方位需要遵循已给事实；
若原文缺乏方位，不得谎称已测量出精确几何关系。每个镜头控制在1～30秒以内。输出符合 JSON Schema。"""


def create_storyboard(session: Session, llm: QwenCloudAdapter, script: ScriptVersion, count_limit: int, force: bool) -> list[Shot]:
    saved = list(session.scalars(select(Shot).where(Shot.script_id == script.id).order_by(Shot.ordinal)))
    if saved:
        if force:
            raise ValueError("为了保护已编辑镜头和提示词历史，不能覆盖现有分镜；请保存剧本新版本后再规划。")
        return saved
    assets = list(session.scalars(select(Asset).where(Asset.project_id == script.project_id, Asset.status == "approved")))
    output = llm.call_json(
        task="shot_plan",
        system_prompt=SHOT_SYSTEM,
        user_data={
            "script_text": script.text,
            "assets": [{"id": a.id, "name": a.name, "kind": a.kind, "facts": a.facts, "locked_fields": a.locked_fields} for a in assets],
            "max_shots": count_limit,
            "project_style_guide": session.get(Project, script.project_id).style_guide,
        },
        schema=StoryboardResult,
        session=session,
        project_id=script.project_id,
    )
    if not output.shots:
        raise ValueError("Qwen 没有生成任何分镜。")
    if len(output.shots) > count_limit:
        raise ValueError(f"Qwen 返回了 {len(output.shots)} 个分镜，超过请求上限 {count_limit}。")
    asset_names = {a.name.casefold(): a.id for a in assets}
    for a in assets:
        for alias in a.aliases:
            asset_names.setdefault(alias.casefold(), a.id)
    created: list[Shot] = []
    for n, draft in enumerate(output.shots, 1):
        unknown = [name for name in draft.asset_names if name.casefold() not in asset_names]
        if unknown:
            raise ValueError(f"镜头 {n} 引用了尚未审核的资产：{'、'.join(unknown)}，请先确认资产。")
        links = list(dict.fromkeys(asset_names[name.casefold()] for name in draft.asset_names))
        row = Shot(
            project_id=script.project_id,
            script_id=script.id,
            ordinal=n,
            narrative=draft.narrative,
            duration_seconds=draft.duration_seconds,
            camera=draft.camera.model_dump(),
            constraints=[c.model_dump() for c in draft.constraints],
            asset_ids=links,
            start_state=[s.model_dump() for s in draft.start_state],
            end_state=[s.model_dump() for s in draft.end_state],
            transition=draft.transition,
        )
        session.add(row)
        created.append(row)
    session.commit()
    return created
