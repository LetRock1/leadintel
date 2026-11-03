"""Project-wide rules: no emoji anywhere, a complete settings file, and no secrets in what git tracks."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _emoji_checker():
    spec = importlib.util.spec_from_file_location("check_no_emoji", ROOT / "scripts" / "check_no_emoji.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_emoji_in_code_settings_or_documents():
    problems = _emoji_checker().scan([ROOT])
    assert problems == [], "\n".join(problems[:20])


def test_the_emoji_check_finds_one(tmp_path):
    probe = tmp_path / "probe.ts"
    probe.write_text('const label = "Launch \U0001f680";\n', encoding="utf-8")
    assert len(_emoji_checker().scan([probe])) == 1


def test_the_settings_file_is_complete_and_consistent():
    s = json.loads((ROOT / "crm_settings.json").read_text(encoding="utf-8"))
    scores = [t["min_score"] for t in s["tiers"]]
    assert scores == sorted(scores, reverse=True) and scores[-1] == 0
    assert "none" in s["actions"]
    for key, action in s["actions"].items():
        assert action["label"], key
        assert action["channel"] in {None, "email", "call", "whatsapp"}, key
        assert 0 <= action["discount"] < 1 and action["cost"] >= 0, key
    assert int(s["daily_call_capacity"]) > 0
    assert s["call_capacity"]["policy"] in {"priced", "fcfs"}
    assert 0 < s["global_control"]["share"] < 0.5
    assert 0 <= s["exploration_rate"] < 0.5


def test_no_secrets_are_tracked():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "backend/.env" in ignored and "backend/data/" in ignored
    example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    secret = re.compile(r"^(\w*(PASSWORD|SECRET|API_KEY)\w*)=(.*)$")
    for line in example.splitlines():
        m = secret.match(line.strip())
        if m:
            assert m.group(3) == "", f"{m.group(1)} must be empty in .env.example"


def test_env_example_matches_the_settings(monkeypatch, tmp_path):
    """Every key in .env.example is a real setting, and the file works when copied as it is."""
    names = {name.upper() for name in Settings.model_fields}
    aliases = {"DATABASE_PATH", "DB_PATH", "SIMULATION_DB_PATH", "RULES_PATH"}
    example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    keys = [line.split("=", 1)[0] for line in example.splitlines() if line and not line.startswith("#")]
    unknown = [k for k in keys if k not in names | aliases]
    assert unknown == []
    for line in example.splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            monkeypatch.setenv(key, value)
    settings = Settings()
    assert settings.demo_mode is True
    assert settings.data_dir.name == "data"  # an empty DATA_DIR means the default folder
    assert settings.simulation_enabled is None
