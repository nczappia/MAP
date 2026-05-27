"""Unit tests for Config loading."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from map.config import Config, _apply_yaml


class TestConfigDefaults:
    def test_default_model(self) -> None:
        cfg = Config()
        assert cfg.model.default == "claude-sonnet-4-6"

    def test_default_channels_include_terminal(self) -> None:
        cfg = Config()
        assert "terminal" in cfg.comms.channels

    def test_default_implementer_tools(self) -> None:
        cfg = Config()
        assert "Edit" in cfg.agents.implementer_tools

    def test_default_tester_tools(self) -> None:
        cfg = Config()
        assert "Bash" in cfg.agents.tester_tools

    def test_default_pipeline_no_checkpoint_after_review(self) -> None:
        cfg = Config()
        assert cfg.pipeline.checkpoint_after_review is False

    def test_default_pipeline_no_auto_open_pr(self) -> None:
        cfg = Config()
        assert cfg.pipeline.auto_open_pr is False

    def test_default_db_path_under_home(self) -> None:
        cfg = Config()
        assert ".map" in cfg.db_path


class TestApplyYaml:
    def test_applies_pipeline_section(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"pipeline": {"checkpoint_after_review": True, "auto_open_pr": True}})
        assert cfg.pipeline.checkpoint_after_review is True
        assert cfg.pipeline.auto_open_pr is True

    def test_applies_pipeline_timeout(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"pipeline": {"checkpoint_timeout_secs": 300}})
        assert cfg.pipeline.checkpoint_timeout_secs == 300.0

    def test_applies_null_timeout(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"pipeline": {"checkpoint_timeout_secs": None}})
        assert cfg.pipeline.checkpoint_timeout_secs is None

    def test_applies_comms_channels(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"comms": {"channels": ["terminal", "telegram"]}})
        assert cfg.comms.channels == ["terminal", "telegram"]

    def test_applies_implementer_tools(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"agents": {"implementer_tools": ["Edit", "Read"]}})
        assert cfg.agents.implementer_tools == ["Edit", "Read"]

    def test_applies_tester_tools(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"agents": {"tester_tools": ["Bash"]}})
        assert cfg.agents.tester_tools == ["Bash"]

    def test_applies_model(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"model": {"default": "claude-opus-4-7"}})
        assert cfg.model.default == "claude-opus-4-7"

    def test_ignores_unknown_sections(self) -> None:
        cfg = Config()
        _apply_yaml(cfg, {"unknown_section": {"foo": "bar"}})
        # Should not raise


class TestConfigLoad:
    def test_load_reads_env_vars(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-test",
                "TELEGRAM_BOT_TOKEN": "bot123",
                "TELEGRAM_ALLOWED_CHAT_ID": "456",
            },
        ):
            cfg = Config.load()

        assert cfg.anthropic_api_key == "sk-test"
        assert cfg.telegram_bot_token == "bot123"
        assert cfg.telegram_allowed_chat_id == "456"

    def test_load_missing_env_gives_empty_string(self) -> None:
        skip = {"ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN"}
        env = {k: v for k, v in os.environ.items() if k not in skip}
        with patch.dict(os.environ, env, clear=True):
            cfg = Config.load()
        assert cfg.anthropic_api_key == ""

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "map.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
                pipeline:
                  checkpoint_after_review: true
                model:
                  default: claude-opus-4-7
            """)
        )
        cfg = Config.load(str(yaml_file))
        assert cfg.pipeline.checkpoint_after_review is True
        assert cfg.model.default == "claude-opus-4-7"

    def test_load_no_yaml_uses_defaults(self) -> None:
        cfg = Config.load("/nonexistent/path/map.yaml")
        assert cfg.model.default == "claude-sonnet-4-6"

    def test_load_falls_back_to_map_yaml_in_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "map.yaml").write_text("model:\n  default: claude-haiku-4-5-20251001\n")
        cfg = Config.load()
        assert cfg.model.default == "claude-haiku-4-5-20251001"
