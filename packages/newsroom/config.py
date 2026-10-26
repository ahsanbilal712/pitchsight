"""Newsroom configuration: model roles (config/models.yaml), Director budgets (config/budgets.yaml), environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "config" / "models.yaml"
BUDGETS = ROOT / "config" / "budgets.yaml"
PROMPTS = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class Role:
    name: str
    provider: str
    model: str
    effort: str | None = None
    max_tokens: int | None = None
    timeout_s: float = 60.0
    max_retries: int = 2
    output_format: str | None = None
    tools: tuple[str, ...] = ()
    max_tool_rounds: int = 0
    fallback_role: str | None = None
    batch: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def is_template(self) -> bool:
        return self.provider == "none"

    def thinking_level(self) -> str | None:
        """Gemini thinking_level for this role's effort (models.yaml header: medium -> high on Argon, low on Flash)."""
        if self.provider != "gemini" or self.effort is None:
            return None
        if self.effort == "none":
            return "none"
        if self.effort == "medium":
            return "high" if "argon" in self.model else "low"
        return self.effort


@lru_cache(maxsize=4)
def load_models(path: str = str(MODELS)) -> dict:
    return yaml.safe_load(Path(path).read_text())


@lru_cache(maxsize=4)
def load_budgets(path: str = str(BUDGETS)) -> dict:
    return yaml.safe_load(Path(path).read_text())


def role(name: str, models: dict | None = None) -> Role:
    cfg = models or load_models()
    raw = dict(cfg["roles"][name])
    defaults = cfg.get("provider_defaults", {}).get(raw.get("provider"), {})
    known = {"provider", "model", "effort", "max_tokens", "timeout_s", "max_retries", "output_format", "tools",
             "max_tool_rounds", "fallback_role", "batch"}
    provider, model = raw["provider"], raw["model"]
    if provider == "gemini" and os.environ.get("WHYLINE_LLM_PROVIDER") == "foundry":
        # Azure deployment: every model role runs on the Foundry project's deployment (FOUNDRY_MODEL_DEPLOYMENT,
        # or a per-tier one: FOUNDRY_MODEL_DEPLOYMENT_FAST for Flash roles, _REASONING for Argon roles)
        tier = "FAST" if "flash" in model else "REASONING"
        provider = "foundry"
        model = os.environ.get(f"FOUNDRY_MODEL_DEPLOYMENT_{tier}") or os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or model
    return Role(
        name=name, provider=provider, model=model, effort=raw.get("effort"),
        max_tokens=raw.get("max_tokens"), timeout_s=float(raw.get("timeout_s", defaults.get("timeout_s", 60))),
        max_retries=int(raw.get("max_retries", defaults.get("max_retries", 2))),
        output_format=raw.get("output_format"), tools=tuple(raw.get("tools") or ()),
        max_tool_rounds=int(raw.get("max_tool_rounds", 0)), fallback_role=raw.get("fallback_role"),
        batch=bool(raw.get("batch", False)), extra={k: v for k, v in raw.items() if k not in known})


def mode() -> str:
    """replay (CacheClient) or live (LiveClient); degraded is entered at runtime."""
    return os.environ.get("WHYLINE_MODE", "replay")


def checkpoint_dir() -> Path:
    path = Path(os.environ.get("WHYLINE_CHECKPOINT_DIR", ".checkpoints"))
    return path if path.is_absolute() else ROOT / path


def prompt(name: str) -> tuple[str, str]:
    """(version, text) for a prompt file `prompts/<agent>@<n>.md`, e.g. prompt("narrator@2")."""
    text = (PROMPTS / f"{name}.md").read_text()
    return name, text
