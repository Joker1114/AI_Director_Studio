"""Persistent business entities; JSON fields are typed by the API contracts."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

JSON_FIELD = JSON().with_variant(JSONB, "postgresql")


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditFields:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(AuditFields, Base):
    __tablename__ = "projects"
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    style_guide: Mapped[str] = mapped_column(Text, default="写实电影风格")


class ScriptVersion(AuditFields, Base):
    __tablename__ = "script_versions"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("project_id", "version"),)


class ExtractionRun(AuditFields, Base):
    __tablename__ = "extraction_runs"
    script_id: Mapped[str] = mapped_column(ForeignKey("script_versions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="completed")
    model: Mapped[str] = mapped_column(String(100), default="")
    beat_count: Mapped[int] = mapped_column(Integer, default=0)


class Candidate(AuditFields, Base):
    __tablename__ = "candidates"
    run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    source_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end: Mapped[int] = mapped_column(Integer, nullable=False)
    aliases: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    facts: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)


class Asset(AuditFields, Base):
    __tablename__ = "assets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    aliases: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    facts: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    locked_fields: Mapped[dict] = mapped_column(JSON_FIELD, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="approved")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (Index("ix_assets_project_kind", "project_id", "kind"),)


class ReferenceImage(AuditFields, Base):
    __tablename__ = "reference_images"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(250), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="identity")
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class Shot(AuditFields, Base):
    __tablename__ = "shots"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    script_id: Mapped[str] = mapped_column(ForeignKey("script_versions.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=5)
    camera: Mapped[dict] = mapped_column(JSON_FIELD, default=dict)
    constraints: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    asset_ids: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    reference_ids: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    start_state: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    end_state: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    transition: Mapped[str] = mapped_column(String(120), default="cut")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("script_id", "ordinal"),)


class PromptVersion(AuditFields, Base):
    __tablename__ = "prompt_versions"
    owner_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    compiled_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    manifest: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    constraints_snapshot: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("owner_kind", "owner_id", "purpose", "version"),)


class LLMCall(AuditFields, Base):
    __tablename__ = "llm_calls"
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    task: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")


class StoryBeat(AuditFields, Base):
    __tablename__ = "story_beats"
    run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    source_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_name: Mapped[str] = mapped_column(String(160), default="")


class GenerationJob(AuditFields, Base):
    __tablename__ = "generation_jobs"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"), index=True)
    prompt_version_id: Mapped[str] = mapped_column(ForeignKey("prompt_versions.id"))
    workflow_id: Mapped[str] = mapped_column(String(100))
    node_id: Mapped[str] = mapped_column(String(100))
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    comfy_prompt_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_files: Mapped[list] = mapped_column(JSON_FIELD, default=list)
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
