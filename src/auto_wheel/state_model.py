"""
统一状态模型定义。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class JobState(str, Enum):
    """任务级状态。"""

    CREATED = "created"
    RESOLVING_UV = "resolving_uv"
    RESOLVING_PIP_FALLBACK = "resolving_pip_fallback"
    PLANNING_READY = "planning_ready"
    DOWNLOADING = "downloading"
    VERIFYING_INSTALLABILITY = "verifying_installability"
    COMPLETED = "completed"
    COMPLETED_WITH_RISKS = "completed_with_risks"
    FAILED = "failed"


class DependencyState(str, Enum):
    """依赖级状态。"""

    PENDING = "pending"
    RESOLVED = "resolved"
    WHEEL_READY = "wheel_ready"
    SOURCE_REQUIRED = "source_required"
    MANUAL_REQUIRED = "manual_required"
    UNRESOLVED = "unresolved"


class ArtifactState(str, Enum):
    """产物级状态。"""

    MISSING = "missing"
    GENERATED = "generated"
    VALIDATED = "validated"
    INVALID = "invalid"


@dataclass
class ResolutionStateSnapshot:
    """解析阶段状态快照。"""

    job_state: JobState
    stage: str
    resolver: str
    failure_kind: Optional[str] = None
    reason: Optional[str] = None
    target_platform: Optional[str] = None
    normalized_platform: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict，便于日志和后续报告使用。"""
        payload = asdict(self)
        payload["job_state"] = self.job_state.value
        return payload

