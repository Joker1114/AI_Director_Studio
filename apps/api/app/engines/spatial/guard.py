"""Fail closed on detectable contradictions in generated creative text.

This is a lightweight lexical guard, NOT a substitute for visual geometry verification.
"""
from __future__ import annotations

import re


class PromptConstraintError(ValueError):
    """The model-generated prompt contradicted a protected scene fact."""


def _direction(value: str) -> str | None:
    normalized = str(value).casefold().strip()
    if normalized in {"right", "右", "右侧", "画面右侧", "screen_right"}:
        return "right"
    if normalized in {"left", "左", "左侧", "画面左侧", "screen_left"}:
        return "left"
    return None


def _clauses(text: str) -> list[str]:
    return [part.strip().casefold() for part in re.split(r"[。；;,，\n!?！？]", text) if part.strip()]


def _contradictory_side(subject: str, expected: str, text: str) -> bool:
    wrong = "left" if expected == "right" else "right"
    wrong_pattern = (
        r"(?:画面|镜头|构图|屏幕|站台|道路|位置)[^，,]{0,12}(左侧|左边|左半|left side|screen left)"
        if wrong == "left"
        else r"(?:画面|镜头|构图|屏幕|站台|道路|位置)[^，,]{0,12}(右侧|右边|右半|right side|screen right)"
    )
    plain = r"(?:在|位于|处于|保持在|remains on|located on)[^，,]{0,18}" + (
        r"(?:左侧|左边|left side|screen left)" if wrong == "left"
        else r"(?:右侧|右边|right side|screen right)"
    )
    aliases = {subject.casefold()}
    # Small bilingual vocabulary for common scene and prop nouns.
    if "公交站" in subject:
        aliases.update({"bus stop", "bus shelter", "站台"})
    for clause in _clauses(text):
        if not any(alias in clause for alias in aliases):
            continue
        if re.match(r"^(?:不要|禁止|避免|不得|不能|do not|never)", clause, re.I):
            continue
        if re.search(wrong_pattern, clause, re.I) or re.search(plain, clause, re.I):
            return True
    return False


def validate_creative_prompt(
    text: str,
    asset_locks: list[tuple[str, dict[str, str]]],
    shot_constraints: list[dict] | None = None,
) -> None:
    """Reject clear contradictions before persistence or approval."""
    for subject, locks in asset_locks:
        side = _direction(locks.get("screen_side", ""))
        if side and _contradictory_side(subject, side, text):
            raise PromptConstraintError(f"模型把锁定为 {side} 的 {subject} 写到了反方向")
    for rule in shot_constraints or []:
        if not rule.get("locked", True):
            continue
        subject = rule.get("subject", "")
        if rule.get("type") == "screen_side":
            side = _direction(rule.get("value", ""))
            if side and _contradictory_side(subject, side, text):
                raise PromptConstraintError(f"模型违背了 {subject} 的屏幕方向约束")
        elif rule.get("type") == "contact":
            # Obvious physical-disconnection statements must be rejected.
            if re.search(r"伞[^。；\n]{0,12}(?:漂浮|悬空|脱离|没有握住)|umbrella[^.\n]{0,30}(?:floating|levitating|not held)", text, re.I):
                raise PromptConstraintError(f"模型描述了与 {subject} 的持物接触约束冲突的动作")
        elif rule.get("type") == "scale" and rule.get("relation") in {"height_fraction", "screen_height_fraction"}:
            try:
                expected = float(rule["value"])
            except (ValueError, KeyError, TypeError):
                continue
            for clause in _clauses(text):
                if expected <= .15 and subject.casefold() in clause and re.search(
                    r"(?:特写|近景|close.?up|占(?:据)?画面(?:高度)?\s*(?:[3-9]\d|100)%)",
                    clause, re.I,
                ):
                    raise PromptConstraintError(
                        f"模型将远景主体 {subject} 变成了近景或特写"
                    )
