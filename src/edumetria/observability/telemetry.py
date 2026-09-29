"""Telemetria mínima (seção 22): logs JSON, métricas RED com labels limitados
e propagação W3C ``traceparent``.

- Nunca registrar resposta, gabarito, prompt bruto, segredo ou identificador
  direto: chaves sensíveis são redigidas antes de serializar.
- Labels Prometheus só aceitam valores de conjuntos fechados (sem student_id,
  item_id ilimitado, trace_id ou e-mail).
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

SERVICE = "edumetria"
SENSITIVE_KEYS = {"raw_response", "scored_value", "answer_key", "key", "stem", "student_name", "name", "cpf",
                  "email", "phone", "telefone", "password", "token", "authorization", "prompt", "subject_ref",
                  "student_ref"}
SENSITIVE_PATTERNS = [re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),  # CPF
                      re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),              # e-mail
                      re.compile(r"Bearer\s+[A-Za-z0-9._-]+")]
REDACTED = "[REDACTED]"

ALLOWED_LABELS = {
    "route": {"/v1/calibrations", "/v1/jobs/{id}", "/v1/calibrations/{id}", "/v1/calibrations/{id}/release",
              "/v1/support-cases", "/v1/support-cases/{id}", "/v1/support-cases/{id}/submit",
              "/v1/support-cases/{id}/reviews", "/v1/support-cases/{id}/transition", "/v1/audit",
              "/v1/evidence-reports/{id}", "/health/live", "/health/ready", "/metrics", "other",
              "/v1/items", "/v1/item-versions/{vid}", "/v1/item-versions/{vid}/new-version",
              "/v1/item-versions/{vid}/submit", "/v1/item-versions/{vid}/reviews", "/v1/item-versions/{vid}/approve",
              "/v1/forms", "/v1/copilot/ask", "/v1/integrations/status", "/v1/scores", "/v1/jobs/{job_id}",
              "/v1/calibrations/{cid}", "/v1/calibrations/{cid}/release", "/v1/calibrations/{cid}/diagnostics",
              "/v1/evidence-reports/{cid}", "/v1/support-cases/{case_id}", "/v1/support-cases/{case_id}/submit",
              "/v1/support-cases/{case_id}/reviews", "/v1/support-cases/{case_id}/transition"},
    "method": {"GET", "POST", "PUT", "DELETE", "PATCH"},
    "status_class": {"2xx", "3xx", "4xx", "5xx"},
    "job_type": {"calibration", "other"},
    "status": {"succeeded", "failed", "retried", "queued", "running", "cancelled"},
}


def redact(obj):
    if isinstance(obj, dict):
        return {k: (REDACTED if k.lower() in SENSITIVE_KEYS else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        s = obj
        for p in SENSITIVE_PATTERNS:
            s = p.sub(REDACTED, s)
        return s
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": SERVICE,
            "environment": "demo-synthetic",
            "event": record.getMessage(),
        }
        extra = getattr(record, "fields", None) or {}
        payload.update(redact(extra))
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str = SERVICE, stream=None) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        h = logging.StreamHandler(stream or sys.stderr)
        h.setFormatter(JsonFormatter())
        # nível do CONSOLE configurável (ex.: WARNING em notebooks); arquivos como run.log seguem em INFO
        h.setLevel(os.environ.get("EDUMETRIA_LOG_LEVEL", "INFO").upper())
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


# ---------------------------------------------------------------- tracing
def new_traceparent() -> str:
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    m = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}", value.strip())
    if not m or m.group(1) == "0" * 32:
        return None
    return m.group(1), m.group(2)


def child_traceparent(parent: str | None) -> str:
    parsed = parse_traceparent(parent)
    trace_id = parsed[0] if parsed else secrets.token_hex(16)
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"


# ---------------------------------------------------------------- métricas
class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.counters: dict[tuple, float] = defaultdict(float)
        self.hist_sum: dict[tuple, float] = defaultdict(float)
        self.hist_count: dict[tuple, int] = defaultdict(int)
        self.gauges: dict[tuple, float] = {}

    @staticmethod
    def _labels(labels: dict) -> tuple:
        clean = []
        for k, v in sorted(labels.items()):
            allowed = ALLOWED_LABELS.get(k)
            if allowed is None:
                raise ValueError(f"label não permitido: {k}")
            clean.append((k, v if v in allowed else "other"))
        return tuple(clean)

    def inc(self, name: str, value: float = 1.0, **labels):
        with self._lock:
            self.counters[(name, self._labels(labels))] += value

    def observe(self, name: str, value: float, **labels):
        key = (name, self._labels(labels))
        with self._lock:
            self.hist_sum[key] += value
            self.hist_count[key] += 1

    def set_gauge(self, name: str, value: float, **labels):
        with self._lock:
            self.gauges[(name, self._labels(labels))] = value

    def render(self) -> str:
        def fmt(labels):
            return "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}" if labels else ""
        lines = []
        with self._lock:
            for (n, l), v in sorted(self.counters.items()):
                lines.append(f"{n}{fmt(l)} {v}")
            for (n, l), v in sorted(self.hist_sum.items()):
                lines.append(f"{n}_sum{fmt(l)} {v}")
                lines.append(f"{n}_count{fmt(l)} {self.hist_count[(n, l)]}")
            for (n, l), v in sorted(self.gauges.items()):
                lines.append(f"{n}{fmt(l)} {v}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.t0
