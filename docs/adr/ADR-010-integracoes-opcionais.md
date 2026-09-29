# ADR-010 — Integrações corporativas são opcionais e não bloqueiam a demo

**Status:** aceito. Adapters Themis/Argus geram payloads de metadado (sem registros individuais) e se declaram `unverified`; Aegis está `disabled`. Falha de integração em uso real bloquearia liberação; na demo sintética o rótulo de integração desligada fica visível.
