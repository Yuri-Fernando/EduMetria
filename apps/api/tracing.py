"""Tracing OpenTelemetry da API (perfil ``observability``).

- Um span SERVER por requisição, continuando o ``traceparent`` W3C recebido.
- Atributos só de baixa cardinalidade e sem dado pessoal: rota (template),
  método, status. Nunca corpo, identificador de estudante ou token.
- Exportação: OTLP/HTTP se ``OTEL_EXPORTER_OTLP_ENDPOINT`` estiver definido
  (ex.: ``http://localhost:4318`` → collector → Jaeger); sem ele, spans ficam
  só em memória do processo (nenhum envio externo).
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, format_span_id, format_trace_id

from edumetria import __version__


def build_provider(exporter=None) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": "edumetria-api",
                                                        "service.version": __version__,
                                                        "deployment.environment": "demo-synthetic"}))
    if exporter is None and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces")
    if exporter is not None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        proc = SimpleSpanProcessor(exporter) if exporter.__class__.__name__ == "InMemorySpanExporter" \
            else BatchSpanProcessor(exporter)
        provider.add_span_processor(proc)
    return provider


def start_server_span(tracer, method: str, route: str, headers):
    ctx = extract({k.lower(): v for k, v in headers.items()})
    return tracer.start_as_current_span(f"{method} {route}", context=ctx, kind=SpanKind.SERVER,
                                        attributes={"http.request.method": method, "http.route": route})


def traceparent_of(span) -> str:
    sc = span.get_span_context()
    return f"00-{format_trace_id(sc.trace_id)}-{format_span_id(sc.span_id)}-{int(sc.trace_flags):02x}"


__all__ = ["build_provider", "start_server_span", "traceparent_of", "trace"]
