"""Add generation jobs and explicit reference binding to shots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

JSON_FIELD = sa.JSON().with_variant(JSONB, "postgresql")

revision = "20261105_jobs"
down_revision = "ab8f3366df9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shots", sa.Column("reference_ids", JSON_FIELD, nullable=False, server_default="[]"))
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("shot_id", sa.String(36), sa.ForeignKey("shots.id", ondelete="CASCADE")),
        sa.Column("prompt_version_id", sa.String(36), sa.ForeignKey("prompt_versions.id")),
        sa.Column("workflow_id", sa.String(100)),
        sa.Column("node_id", sa.String(100)),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24)),
        sa.Column("comfy_prompt_id", sa.String(100), nullable=True),
        sa.Column("result_files", JSON_FIELD),
        sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generation_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_index("ix_generation_jobs_shot_id", "generation_jobs", ["shot_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("generation_jobs")
    op.drop_column("shots", "reference_ids")
