"""Deterministic checks on spatial relations and cross-shot continuity.

These checks validate intent/metadata, NOT the physical pixels of a generated video.
"""
from dataclasses import dataclass

from app.contracts import SpatialConstraint, StateFact
from app.models import Shot


@dataclass(frozen=True)
class Finding:
    code: str
    level: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "level": self.level, "message": self.message}


def validate_rules(
    constraints: list[SpatialConstraint],
    start_state: list[StateFact],
    prior_end_state: list[StateFact] | None = None,
    prior_constraints: list[SpatialConstraint] | None = None,
    transition: str = "cut",
) -> list[dict[str, str]]:
    issues: list[Finding] = []
    unique: dict[tuple[str, str, str], str] = {}
    for rule in constraints:
        identity = (rule.type, rule.subject.casefold(), rule.relation.casefold())
        if rule.locked and identity in unique and unique[identity] != rule.value:
            issues.append(Finding("SC01", "error", f"{rule.subject} 的锁定约束互相冲突：{unique[identity]} / {rule.value}"))
        unique[identity] = rule.value
        if rule.type == "scale" and rule.relation in {"height_fraction", "screen_height_fraction"}:
            try:
                value = float(rule.value)
                if not 0 < value <= 1:
                    raise ValueError
            except ValueError:
                issues.append(Finding("SC06", "error", "人物画面高度比例必须是 0～1 之间的小数。"))
        if rule.type == "contact" and not rule.target.strip():
            issues.append(Finding("SC05", "error", f"{rule.subject} 的道具接触关系缺少目标部件。"))
    if prior_end_state is not None:
        old = {(s.subject.casefold(), s.attribute.casefold()): s.value for s in prior_end_state}
        for state in start_state:
            key = (state.subject.casefold(), state.attribute.casefold())
            if key in old and old[key] != state.value and transition not in {"time_jump", "scene_change"}:
                issues.append(Finding("SC04", "warning", f"{state.subject}.{state.attribute} 从 {old[key]} 跳变为 {state.value}，需要过渡说明。"))
    if prior_constraints and transition in {"cut", "eyeline_match", "action_match"}:
        prior_sides = {
            (c.subject.casefold(), c.relation): c.value
            for c in prior_constraints if c.type == "screen_side" and c.locked
        }
        for rule in constraints:
            key = (rule.subject.casefold(), rule.relation)
            if rule.type == "screen_side" and rule.locked and key in prior_sides and prior_sides[key] != rule.value:
                issues.append(Finding("SC02", "warning", f"{rule.subject} 的屏幕左右方向从 {prior_sides[key]} 改为 {rule.value}，请核对机位与轴线。"))
    return [item.as_dict() for item in issues]


def validate_shot(shot: Shot, previous: Shot | None) -> list[dict[str, str]]:
    return validate_rules(
        constraints=[SpatialConstraint.model_validate(c) for c in shot.constraints],
        start_state=[StateFact.model_validate(s) for s in shot.start_state],
        prior_end_state=[StateFact.model_validate(s) for s in previous.end_state] if previous else None,
        prior_constraints=[SpatialConstraint.model_validate(c) for c in previous.constraints] if previous else None,
        transition=shot.transition,
    )


def render_constraints(constraints: list[dict], locked_only: bool = False) -> str:
    lines: list[str] = []
    for item in constraints:
        if locked_only and not item.get("locked", True):
            continue
        prefix = "不可改动" if item.get("locked", True) else "建议"
        target = f" → {item['target']}" if item.get("target") else ""
        lines.append(f"- [{prefix}] {item['subject']} · {item['relation']}{target}：{item['value']}")
    return "\n".join(lines) if lines else "- 未设置额外空间约束"


def validate_asset_locks(shot: Shot, linked_assets: list) -> list[dict[str, str]]:
    """Block direct conflicts between asset-level screen locks and a shot's metadata.

    First release validates explicit matching rules; image pixels remain unchecked.
    """
    findings: list[Finding] = []
    for asset in linked_assets:
        screen_side = (asset.locked_fields or {}).get("screen_side")
        if not screen_side:
            continue
        for rule in shot.constraints:
            same_object = rule.get("subject", "").casefold() in {
                asset.name.casefold(), *[x.casefold() for x in asset.aliases]
            }
            if same_object and rule.get("type") == "screen_side" and rule.get("value") != screen_side:
                findings.append(Finding(
                    "SC09", "error",
                    f"镜头把 {asset.name} 放在 {rule.get('value')}，但资产已锁定为 {screen_side}。",
                ))
    return [f.as_dict() for f in findings]
