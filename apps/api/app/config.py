"""Configuration loaded from environment/.env; no secrets in source control."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/director.db"
    dashscope_api_key: str = ""
    dashscope_base_url: str = ""
    qwen_model_complex: str = "qwen3.8-max"
    qwen_model_fast: str = "qwen3.8-flash"
    qwen_timeout_seconds: float = 120
    qwen_max_retries: int = 2
    app_api_token: str = ""
    app_allow_local_no_token: bool = False
    max_upload_mb: int = 12
    media_dir: str = "./data/media"
    cors_origins: str = ""
    comfyui_nodes_file: str = "config/gpu_nodes.json"
    comfyui_workflow_root: str = "../../workflows/comfyui"
    generation_dir: str = "./data/generated"
    generation_poll_seconds: float = 3.0
    generation_timeout_seconds: int = 3600
    generation_worker_idle_seconds: float = 2.0

    def model_for(self, task: str) -> str:
        return self.qwen_model_complex if task in {"script_extract", "shot_plan"} else self.qwen_model_fast


@lru_cache
def get_settings() -> Settings:
    return Settings()
