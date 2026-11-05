"""Script extraction, exact text evidence validation and approval workflow."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.qwen import QwenCloudAdapter
from app.contracts import ExtractResult
from app.models import Asset, Candidate, ExtractionRun, Project, ScriptVersion, StoryBeat

EXTRACTION_SYSTEM = """你是严谨的影视剧本实体与事件抽取器。仅依据原文抽取角色(character)、
场景(scene)、道具(prop)和推动剧情的事件。每个实体必须有 source_quote：与剧本完全相同的连续原文片段；
不得臆造物品、场景、人物外观，不知道的字段留空字符串/空列表。实体名字尽量使用剧本原词，
别名只在有明确指代证据时归并。事件也必须附连续原文引文。结果符合给定 JSON Schema。"""


def extract_script(session: Session, llm: QwenCloudAdapter, script: ScriptVersion, force: bool = False) -> ExtractionRun:
    previous = session.scalar(
        select(ExtractionRun).where(ExtractionRun.script_id == script.id).order_by(ExtractionRun.created_at.desc())
    )
    if previous is not None and not force:
        return previous

    result = llm.call_json(
        task="script_extract",
        system_prompt=EXTRACTION_SYSTEM,
        user_data={"script_text": script.text, "project_style_guide": session.get(Project, script.project_id).style_guide},
        schema=ExtractResult,
        session=session,
        project_id=script.project_id,
    )
    run = ExtractionRun(script_id=script.id, model=llm.settings.model_for("script_extract"))
    session.add(run)
    session.flush()
    seen: set[tuple[str, str, int]] = set()
    for item in result.assets:
        location = script.text.find(item.source_quote)
        # Invalid evidence may be shown for review, but never treated as approved.
        valid = location >= 0
        identity = (item.kind, item.name.strip().casefold(), location)
        if identity in seen:
            continue
        seen.add(identity)
        session.add(
            Candidate(
                run_id=run.id,
                kind=item.kind,
                name=item.name.strip(),
                description=item.description,
                quote=item.source_quote,
                source_start=location,
                source_end=location + len(item.source_quote) if valid else -1,
                aliases=item.aliases,
                facts=item.facts,
                status="pending" if valid else "invalid_evidence",
            )
        )
    beat_count = 0
    for beat in result.beats:
        location = script.text.find(beat.source_quote)
        if location < 0:
            continue
        session.add(
            StoryBeat(
                run_id=run.id,
                text=beat.narrative,
                quote=beat.source_quote,
                source_start=location,
                source_end=location + len(beat.source_quote),
                scene_name=beat.scene_name,
            )
        )
        beat_count += 1
    run.beat_count = beat_count
    session.commit()
    return run


def approve_candidate(session: Session, candidate: Candidate, existing: Asset | None = None, name: str | None = None) -> Asset:
    if candidate.status == "invalid_evidence":
        raise ValueError("候选证据不在剧本原文中，请先修改或重新抽取。")
    if candidate.asset_id:
        saved = session.get(Asset, candidate.asset_id)
        if saved:
            return saved
    if existing:
        if existing.kind != candidate.kind:
            raise ValueError("不能把不同资产类型合并为一个资产。")
        existing.aliases = sorted(set(existing.aliases + candidate.aliases + [candidate.name]))
        existing.facts = list(dict.fromkeys(existing.facts + candidate.facts))
        existing.revision += 1
        asset = existing
    else:
        run = session.get(ExtractionRun, candidate.run_id)
        script = session.get(ScriptVersion, run.script_id)
        asset = Asset(
            project_id=script.project_id,
            kind=candidate.kind,
            name=name or candidate.name,
            description=candidate.description,
            aliases=candidate.aliases,
            facts=candidate.facts,
            locked_fields={},
        )
        session.add(asset)
        session.flush()
    candidate.asset_id = asset.id
    candidate.status = "approved"
    session.commit()
    return asset
