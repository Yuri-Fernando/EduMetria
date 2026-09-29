"""Adapters de ecossistema (seções 3 e 19) — contratos pequenos, núcleo autônomo.

Estado honesto de cada integração: nenhuma chamada de rede é feita aqui.
Os payloads seguem o formato observado nos repositórios (ThemisAI
``shared/schemas.py`` v0.5.0; Argus data products), mas a integração
real não foi testada ponta a ponta → ``integration_status = "unverified"``.
Nunca mostrar conexão verde porque um import funcionou (seção 3).
"""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATIONS = {
    "themis": {"integration_status": "unverified", "mode": "payload_export_only",
               "note": "adapter gera metadados de finalidade/categorias; política educacional exige revisão jurídica"},
    "argus": {"integration_status": "unverified", "mode": "manifest_export_only",
              "note": "prefixo de domínio 'education'; nenhum estudante entra em golden record comercial"},
    "aegis": {"integration_status": "disabled", "mode": "none",
              "note": "copiloto LLM desligado por padrão (ADR-009); só receberia conteúdo agregado e sanitizado"},
}


def themis_policy_request(run_dir: Path, purpose: str = "educational_measurement_demo") -> dict:
    """Payload mínimo para avaliação de política no Themis (sem dados individuais)."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "source_system": "edumetria",
        "integration_status": INTEGRATIONS["themis"]["integration_status"],
        "purpose": purpose,
        "data_origin": manifest["data_origin"],
        "data_categories": ["desempenho_educacional_pseudonimizado", "frequencia_escolar_pseudonimizada",
                            "percepcao_de_pertencimento_pseudonimizada"],
        "data_subjects": "criancas_e_adolescentes",
        "legal_review_required": True,
        "automated_decision": False,
        "human_oversight": "revisão persistente obrigatória para publicação e intervenção",
        "run_id": manifest["run_id"],
        "dataset_hash": manifest["dataset_hash"],
        "contains_personal_data": False,
        "notes": "Payload é metadado; nenhum registro individual é enviado. Base legal depende de operação real.",
    }


def argus_data_product(run_dir: Path) -> dict:
    """Manifesto de data product no namespace 'education' para o Argus."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((run_dir / "evidence_report.json").read_text(encoding="utf-8"))
    return {
        "namespace": "education.edumetria",
        "integration_status": INTEGRATIONS["argus"]["integration_status"],
        "product": "psychometric_evidence_report",
        "schema_version": evidence["schema_version"],
        "run_id": manifest["run_id"],
        "release_status": manifest["release_status"],
        "code_commit": manifest["code_commit"],
        "artifacts": {k: v for k, v in manifest["artifacts"].items() if not k.startswith("restricted/")},
        "evidence_status": {k: evidence[k]["status"] for k in
                            ("content_review", "response_process", "dimensionality", "ctt", "irt", "precision",
                             "dif", "external_relations")},
        "events": ["education.calibration.completed", "education.calibration.released"],
    }
