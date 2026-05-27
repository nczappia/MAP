"""Layered config: .env → map.yaml → CLI flags."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class CommsConfig:
    channels: list[str] = field(default_factory=lambda: ["terminal"])


@dataclass
class PipelineConfig:
    checkpoint_after_review: bool = False
    auto_open_pr: bool = False
    checkpoint_timeout_secs: float | None = None


@dataclass
class AgentsConfig:
    implementer_tools: list[str] = field(default_factory=lambda: ["Edit", "Write", "Bash", "Read"])
    tester_tools: list[str] = field(default_factory=lambda: ["Bash", "Read"])


@dataclass
class ModelConfig:
    default: str = "claude-sonnet-4-6"


@dataclass
class Config:
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    comms: CommsConfig = field(default_factory=CommsConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    model: ModelConfig = field(default_factory=ModelConfig)

    # Secrets (from .env)
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_allowed_chat_id: str = ""

    # Storage
    db_path: str = str(Path.home() / ".map" / "sessions.db")

    @classmethod
    def load(cls, yaml_path: str | None = None) -> Config:
        load_dotenv()
        config = cls()

        # Load yaml
        candidates = [yaml_path, "map.yaml"] if yaml_path else ["map.yaml"]
        for path in candidates:
            if path and Path(path).exists():
                with open(path) as f:
                    data: dict[str, Any] = yaml.safe_load(f) or {}
                _apply_yaml(config, data)
                break

        # Load secrets from env
        config.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        config.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        config.telegram_allowed_chat_id = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "")

        return config


def _apply_yaml(config: Config, data: dict[str, Any]) -> None:
    if pipeline := data.get("pipeline"):
        if "checkpoint_after_review" in pipeline:
            config.pipeline.checkpoint_after_review = bool(pipeline["checkpoint_after_review"])
        if "auto_open_pr" in pipeline:
            config.pipeline.auto_open_pr = bool(pipeline["auto_open_pr"])
        if "checkpoint_timeout_secs" in pipeline:
            v = pipeline["checkpoint_timeout_secs"]
            config.pipeline.checkpoint_timeout_secs = float(v) if v is not None else None

    if (comms := data.get("comms")) and "channels" in comms:
        config.comms.channels = list(comms["channels"])

    if agents := data.get("agents"):
        if "implementer_tools" in agents:
            config.agents.implementer_tools = list(agents["implementer_tools"])
        if "tester_tools" in agents:
            config.agents.tester_tools = list(agents["tester_tools"])

    if (model := data.get("model")) and "default" in model:
        config.model.default = str(model["default"])
