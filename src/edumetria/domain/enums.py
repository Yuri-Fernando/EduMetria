"""Enumerações do domínio (seções 15, 18 e 21 do plano mestre)."""

from __future__ import annotations

from enum import Enum


class ResponseStatus(str, Enum):
    ANSWERED = "answered"
    OMITTED = "omitted"
    NOT_REACHED = "not_reached"
    NOT_ADMINISTERED = "not_administered"
    INVALIDATED = "invalidated"
    DECLINED = "declined"
    NOT_APPLICABLE = "not_applicable"


class EvidenceStatus(str, Enum):
    SUPPORTED = "supported"
    EXPLORATORY = "exploratory"
    INSUFFICIENT = "insufficient"
    NOT_ASSESSED = "not_assessed"


class EvidenceOrigin(str, Enum):
    SIMULATED_REVIEW = "simulated_review"
    HUMAN_REVIEW = "human_review"


class DataOrigin(str, Enum):
    SYNTHETIC = "synthetic"
    PUBLIC = "public"
    PILOT = "pilot"


class ReleaseStatus(str, Enum):
    CANDIDATE = "candidate"
    RELEASED = "released"
    REJECTED = "rejected"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CaseStatus(str, Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class ScoreStatus(str, Enum):
    COMPUTED = "computed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_COMPUTED = "not_computed"


class ItemStatState(str, Enum):
    """Estados explícitos da TCT (seção 9): nunca devolver zero como valor válido."""

    OK = "ok"
    CONSTANT_ITEM = "constant_item"
    NO_VARIANCE = "no_variance"
    SMALL_SAMPLE = "small_sample"
    NOT_ADMINISTERED = "not_administered"
