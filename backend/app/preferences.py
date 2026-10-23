"""Application preferences only: no system actions, URLs or privileged settings."""

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .services import UNIT_PATTERN

Metric = Literal[
    "cpu_percent",
    "memory_percent",
    "swap_percent",
    "disk_free_percent",
    "ollama_unavailable",
    "service_failed",
    "container_stopped",
]


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    metric: Metric
    enabled: bool = True
    threshold: float = Field(default=90, ge=0, le=100, allow_inf_nan=False)
    duration_seconds: int = Field(default=30, ge=0, le=3600)
    severity: Literal["warning", "critical"] = "warning"
    target: str | None = Field(default=None, max_length=200)
    engine: Literal["docker", "podman"] | None = None

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if self.metric == "service_failed":
            if not self.target or not re.fullmatch(UNIT_PATTERN, self.target):
                raise ValueError("Exact service required")
        elif self.metric == "container_stopped":
            if not self.target or not re.fullmatch(r"[a-f0-9]{64}", self.target) or not self.engine:
                raise ValueError("Exact engine/container required")
        elif self.metric == "disk_free_percent":
            if not self.target or not self.target.startswith("/"):
                raise ValueError("Mount point required")
        elif self.target is not None:
            raise ValueError("No target for this metric")
        if self.metric != "container_stopped" and self.engine is not None:
            raise ValueError("No engine for this metric")
        return self


def default_rules() -> list[Rule]:
    return [
        Rule(id="cpu", metric="cpu_percent", threshold=90),
        Rule(id="memory", metric="memory_percent", threshold=90),
        Rule(id="swap", metric="swap_percent", threshold=90),
        Rule(id="disk", metric="disk_free_percent", target="/", threshold=10),
    ]


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    language: Literal["fr", "en"] = "fr"
    theme: Literal["dark", "light", "system"] = "system"
    refresh_seconds: int = Field(default=3, ge=3, le=60)
    retention_days: int = Field(default=7, ge=1, le=90)
    rules: list[Rule] = Field(default_factory=default_rules, max_length=20)

    @model_validator(mode="after")
    def unique_rules(self) -> Self:
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Duplicate rule")
        return self
