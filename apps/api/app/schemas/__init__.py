"""Stable input/output schemas shared by Qwen and HTTP endpoints."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Kind = Literal["character", "scene", "prop"]


class ExtractedAsset(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=160)
    description: str
    source_quote: str = Field(min_length=1)
    aliases: list[str]
    facts: list[str]


class ExtractedBeat(BaseModel):
    narrative: str
    source_quote: str = Field(min_length=1)
    scene_name: str


class ExtractResult(BaseModel):
    assets: list[ExtractedAsset]
    beats: list[ExtractedBeat]


class PolishResult(BaseModel):
    creative_prompt: str = Field(min_length=5)
    notes: list[str]


class Camera(BaseModel):
    shot_size: str = "wide"
    angle: str = "eye_level"
    movement: str = "static"
    axis: str = "unknown"


class SpatialConstraint(BaseModel):
    type: Literal["screen_side", "depth", "scale", "distance", "contact", "gaze", "other"]
    subject: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    target: str = ""
    value: str = Field(min_length=1)
    locked: bool = True


class StateFact(BaseModel):
    subject: str
    attribute: str
    value: str


class ShotDraft(BaseModel):
    narrative: str = Field(min_length=1)
    duration_seconds: int = Field(ge=1, le=30)
    camera: Camera
    constraints: list[SpatialConstraint]
    asset_names: list[str]
    start_state: list[StateFact]
    end_state: list[StateFact]
    transition: str


class StoryboardResult(BaseModel):
    shots: list[ShotDraft]


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    style_guide: str = Field(default="写实电影风格", max_length=4000)


class ScriptCreate(BaseModel):
    text: str = Field(min_length=10, max_length=200_000)


class AssetCreate(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    aliases: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    locked_fields: dict[str, str] = Field(default_factory=dict)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    aliases: list[str] | None = None
    facts: list[str] | None = None
    locked_fields: dict[str, str] | None = None
    status: Literal["approved", "reviewed", "archived"] | None = None
    revision: int = Field(ge=1)


class CandidateDecision(BaseModel):
    existing_asset_id: str | None = None
    name_override: str | None = None


class AssetPromptRequest(BaseModel):
    target_image_model: str = Field(default="generic", max_length=80)
    request: str = Field(default="写实电影级角色、场景或道具参考图", max_length=1000)


class ShotCreate(BaseModel):
    script_id: str
    ordinal: int = Field(ge=1)
    narrative: str = Field(min_length=1)
    duration_seconds: int = Field(default=5, ge=1, le=30)
    camera: Camera = Field(default_factory=Camera)
    constraints: list[SpatialConstraint] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    start_state: list[StateFact] = Field(default_factory=list)
    end_state: list[StateFact] = Field(default_factory=list)
    transition: str = "cut"


class ShotUpdate(BaseModel):
    narrative: str | None = None
    duration_seconds: int | None = Field(default=None, ge=1, le=30)
    camera: Camera | None = None
    constraints: list[SpatialConstraint] | None = None
    asset_ids: list[str] | None = None
    start_state: list[StateFact] | None = None
    end_state: list[StateFact] | None = None
    transition: str | None = None
    reference_ids: list[str] | None = None
    revision: int = Field(ge=1)


class ShotPromptRequest(BaseModel):
    purpose: Literal["shot_still", "shot_video"] = "shot_video"
    user_guidance: str = Field(default="", max_length=1500)


class ReferenceApprove(BaseModel):
    approved: bool


class PromptApprove(BaseModel):
    approved: bool


class ShotPlanRequest(BaseModel):
    count_limit: int = Field(default=12, ge=1, le=30)
    force: bool = False


class ExtractRequest(BaseModel):
    force: bool = False
