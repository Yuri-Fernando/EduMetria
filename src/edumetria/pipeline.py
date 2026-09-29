"""Orquestração ponta a ponta de uma execução (fatias A–C do prompt mestre).

geração sintética → importação validada/quarentena → snapshot → TCT → TRI
(2PL, 1PL, GRM) → EAP com incerteza → diagnósticos → DIF → validade de
conteúdo → risco point-in-time → relatório de evidências → manifesto.

Cada run grava artefatos em ``runs/<run_id>/`` e nunca sobrescreve outro run.
Resultados publicados em README/apresentação devem vir destes artefatos.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from edumetria import SCHEMA_VERSION
from edumetria.ctt.analysis import alpha_with_ci, distractor_analysis, item_statistics, score_distribution
from edumetria.data_quality.validate import to_wide, validate_responses
from edumetria.dif.analysis import run_dif
from edumetria.domain.contracts import EvidenceSection, PsychometricEvidenceReport
from edumetria.domain.enums import EvidenceStatus
from edumetria.irt.estimation import fit_2pl, fit_grm, grm_params_arrays
from edumetria.irt.models import se_from_information, total_information
from edumetria.irt.scoring import (PRIOR_DESCRIPTION, dimensionality_screen, eap_2pl, eap_grm,
                                   observed_vs_expected, q3_flags, q3_matrix)
from edumetria.observability.telemetry import METRICS, get_logger, log_event
from edumetria.reporting import figures, report
from edumetria.reporting.manifest import build_manifest, write_manifest
from edumetria.risk.features import LeakageError, build_snapshot, day_ts
from edumetria.risk.models import evaluate_baselines, split_schools
from edumetria.simulation.generator import generate, load_item_bank, load_scenario
from edumetria.validity.content import content_validity

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"


class PipelineBlocked(RuntimeError):
    def __init__(self, message: str, run_dir: Path):
        super().__init__(message)
        self.run_dir = run_dir


def _json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_default), encoding="utf-8")


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


def run_analysis(scenario: str = "s0", runs_dir: Path | None = None, resolve_quarantine: bool = False,
                 purpose: str = "simulation", overrides: dict | None = None) -> dict:
    """Executa um run completo. ``overrides`` (dict aninhado) altera o cenário
    — usado em testes para reduzir N; fica registrado no manifesto."""
    t_start = time.perf_counter()
    cfg = load_scenario(scenario)
    if overrides:
        from edumetria.simulation.generator import _deep_merge
        cfg = _deep_merge(cfg, overrides)
        cfg["overrides"] = overrides
    run_id = f"run-{cfg['scenario_id']}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    out = (runs_dir or RUNS_DIR) / run_id
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "restricted").mkdir(exist_ok=True)
    logger = get_logger("edumetria.pipeline")
    fh = logging.FileHandler(out / "run.log", encoding="utf-8")
    from edumetria.observability.telemetry import JsonFormatter
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)
    warnings: list[str] = []
    try:
        log_event(logger, "run.started", run_id=run_id, scenario=cfg["scenario_id"])
        ds = generate(cfg)
        bank = load_item_bank()
        items = ds.items

        # ---------------------------------------------------- A. DQ / snapshot
        batch = validate_responses(ds.responses, items, snapshot_prefix=f"synthetic-{cfg['scenario_id']}")
        _json(out / "data_quality.json", batch.report.to_dict())
        batch.quarantine.drop(columns=["raw_response", "scored_value"]).to_csv(
            out / "restricted" / "quarantine.csv", index=False)
        log_event(logger, "dq.validated", run_id=run_id, accepted=batch.report.n_accepted,
                  quarantined=batch.report.n_quarantined, blocking=batch.report.blocking)
        if batch.report.blocking and not resolve_quarantine:
            _json(out / "run_status.json", {"status": "blocked_by_data_quality", "run_id": run_id,
                                            "reason": "versão de item desconhecida no lote (alerta A2)"})
            raise PipelineBlocked("lote bloqueado pela validação de dados (versão desconhecida)", out)
        if batch.report.blocking:
            warnings.append("lote original bloqueado; análise usa apenas linhas aceitas após quarentena")

        Xm, persons, mcols = to_wide(batch.accepted, "math6", items)
        Xb, persons_b, bcols = to_wide(batch.accepted, "belong6", items)
        item_labels = [c.split("-")[1] for c in mcols]
        blabels = [c.split("-")[1] for c in bcols]
        students = ds.students.set_index("student_ref")

        # ---------------------------------------------------- B. TCT
        n_adm = batch.accepted[batch.accepted["instrument_id"] == "math6"].groupby("item_version_id")[
            "response_status"].apply(lambda s: int((s != "not_administered").sum())).reindex(mcols).to_numpy()
        ctt_items = item_statistics(Xm, mcols, n_adm)
        ctt_items.to_csv(out / "ctt_items.csv", index=False)
        prop = pd.Series(np.nanmean(Xm, axis=1), index=persons)
        keys = {f"math6-{it['id']}-v1": it["key"] for it in bank["math_items"]}
        distr = distractor_analysis(batch.accepted[batch.accepted["instrument_id"] == "math6"], keys, prop)
        distr.to_csv(out / "ctt_distractors.csv", index=False)
        ctt_test = {"math6": {"alpha": alpha_with_ci(Xm), "score_distribution": score_distribution(Xm)},
                    "belong6": {"alpha": alpha_with_ci(Xb),
                                "note": "alfa sobre categorias 0–3 tratadas como numéricas; ômega ordinal no roadmap"}}
        _json(out / "ctt_test.json", ctt_test)

        # ---------------------------------------------------- B. TRI
        with_timer = time.perf_counter()
        fit_m = fit_2pl(Xm, item_labels)
        fit_1 = fit_2pl(Xm, item_labels, common_slope=True)
        lr = 2 * (fit_m.loglik - fit_1.loglik)
        from scipy import stats as _st
        comparison = {"2pl": {"loglik": fit_m.loglik, "aic": fit_m.aic, "bic": fit_m.bic},
                      "1pl": {"loglik": fit_1.loglik, "aic": fit_1.aic, "bic": fit_1.bic,
                              "common_slope": float(fit_1.params["a"].iloc[0])},
                      "lr_test": {"statistic": lr, "df": fit_m.n_free_params - fit_1.n_free_params,
                                  "p_value": float(_st.chi2.sf(lr, fit_m.n_free_params - fit_1.n_free_params))},
                      "note": ("1PL com slope comum e θ~N(0,1) é reparametrização do Rasch (σ = a comum); "
                               "vantagem de ajuste não basta para escolher o modelo")}
        grm_ok, grm_err = True, None
        try:
            fit_b = fit_grm(Xb, 4, blabels)
        except ValueError as exc:
            grm_ok, grm_err, fit_b = False, str(exc), None
            warnings.append(f"GRM não ajustado: {exc}")
        fit_seconds = time.perf_counter() - with_timer
        METRICS.observe("edumetria_job_duration_seconds", fit_seconds, job_type="calibration")
        fit_m.params.assign(item_version_id=mcols).to_csv(out / "item_parameters_math6.csv", index=False)
        if grm_ok:
            fit_b.params.assign(item_version_id=bcols).to_csv(out / "item_parameters_belong6.csv", index=False)
        warnings.extend(fit_m.warnings)
        if grm_ok:
            warnings.extend(fit_b.warnings)

        # ---------------------------------------------------- escores EAP
        a, b = fit_m.params["a"].to_numpy(), fit_m.params["b"].to_numpy()
        em = eap_2pl(Xm, a, b)
        sc = em.to_frame(persons).rename(columns={"theta_eap": "theta_math", "posterior_sd": "psd_math",
                                                  "q05": "q05_math", "q95": "q95_math",
                                                  "n_answered": "n_answered_math", "status": "status_math"})
        if grm_ok:
            ab, B = grm_params_arrays(fit_b.params)
            eb = eap_grm(Xb, ab, B).to_frame(persons_b).rename(columns={
                "theta_eap": "theta_belong", "posterior_sd": "psd_belong", "q05": "q05_belong",
                "q95": "q95_belong", "n_answered": "n_answered_belong", "status": "status_belong"})
            sc = sc.merge(eb, on="subject_ref", how="outer")
        sc["available_at"] = day_ts(cfg["attendance"]["scores_available_day"])
        sc["school_id"] = students.loc[sc["subject_ref"], "school_id"].to_numpy()
        sc["calibration_ref"] = run_id
        sc["method"] = "EAP"
        sc["prior"] = PRIOR_DESCRIPTION
        sc.to_csv(out / "restricted" / "scores.csv", index=False)

        th_grid = np.linspace(-4, 4, 81)
        info = total_information(th_grid, a, b)
        _json(out / "precision_curves.json", {"theta": th_grid, "total_information": info,
                                              "se_approx": se_from_information(info),
                                              "note": "SE ≈ 1/√I(θ) difere da incerteza posterior EAP"})

        # diagnósticos
        theta_hat = sc["theta_math"].to_numpy()
        q3 = q3_matrix(Xm, a, b, theta_hat)
        oe = observed_vs_expected(Xm, a, b, theta_hat, item_labels)
        oe.to_csv(out / "observed_expected_math6.csv", index=False)
        diagnostics = {
            "math6": {**fit_m.to_dict(), "q3_flags": q3_flags(q3, item_labels),
                      "q3_mean": float(np.nanmean(q3[np.triu_indices_from(q3, 1)])),
                      "dimensionality": dimensionality_screen(Xm), "model_comparison": comparison},
            "belong6": fit_b.to_dict() if grm_ok else {"status": "failed", "error": grm_err},
            "fit_seconds": fit_seconds,
        }
        diagnostics["structure"] = _structure_block(Xm, item_labels, Xb, blabels,
                                                    students.loc[persons_b, "audit_group"].to_numpy())
        _json(out / "fit_diagnostics.json", diagnostics)
        extremes = sc[(sc["n_answered_math"] > 0)]
        pair = _uncertainty_pair(sc)

        # ---------------------------------------------------- verificação de software (usa gabarito)
        truth = pd.DataFrame(ds.truth["math_params"])
        rec = {"rmse_a": float(np.sqrt(np.mean((a - truth["a"].to_numpy()) ** 2))),
               "rmse_b": float(np.sqrt(np.mean((b - truth["b"].to_numpy()) ** 2))),
               "corr_theta": float(pd.Series(theta_hat, index=persons).corr(
                   students.loc[persons, "true_theta_math"])),
               "note": ("verificação de software em simulação — não é evidência de validade; "
                        "DIF/testlet no gerador tornam o modelo 2PL propositalmente mal especificado")}
        _json(out / "simulation_recovery.json", rec)

        # ---------------------------------------------------- C. DIF
        grp = students.loc[persons, "audit_group"].to_numpy()
        true_anchor = [it for it, anc in zip(truth["item"], truth["anchor"]) if anc]
        dif_known = run_dif(Xm, item_labels, grp, anchors=true_anchor if ds.truth["dif_items"] else None)
        dif_all = run_dif(Xm, item_labels, grp, anchors=None)
        dif_known["analysis"] = "known_anchors_simulation" if ds.truth["dif_items"] else "all_other_items"
        dif_all["analysis"] = "all_other_items"
        dif_report = pd.concat([dif_known, dif_all], ignore_index=True) if ds.truth["dif_items"] else dif_all
        dif_report.to_csv(out / "dif_report.csv", index=False)

        # ---------------------------------------------------- validade de conteúdo
        cv = content_validity(ds.judge_reviews)
        _json(out / "content_validity.json", cv)

        # ---------------------------------------------------- E. risco
        risk = _risk_block(ds, sc, cfg)
        _json(out / "risk_evaluation.json", risk)

        # ---------------------------------------------------- figuras
        flagged = dif_all.loc[dif_all.get("flagged", pd.Series(False)).fillna(False).astype(bool), "item"].tolist()
        figures.icc_plot(fit_m.params, out / "figures" / "icc_math6.png", highlight=flagged[:4] or None)
        figures.information_plot(fit_m.params, out / "figures" / "information_math6.png")
        figures.theta_uncertainty_plot(sc.rename(columns={"theta_math": "theta_eap", "psd_math": "posterior_sd",
                                                          "status_math": "status"}),
                                       out / "figures" / "theta_uncertainty_math6.png")
        figures.dif_plot(dif_all, out / "figures" / "dif_math6.png")
        figures.ctt_plot(ctt_items.assign(item=mcols), out / "figures" / "ctt_math6.png")
        worst = min(item_labels, key=lambda it: fit_m.params.set_index("item").loc[it, "a"])
        figures.obs_exp_plot(oe, worst, out / "figures" / "obs_exp_worst_item.png")

        # ---------------------------------------------------- evidências
        evidence = _evidence_report(run_id, cfg, cv, ctt_test, ctt_items, fit_m, fit_b, grm_ok, diagnostics,
                                    dif_all, risk, batch, sc)
        _json(out / "evidence_report.json", evidence.model_dump())
        context = {"run_id": run_id, "scenario": cfg, "dq": batch.report.to_dict(), "ctt_items": ctt_items,
                   "ctt_test": ctt_test, "fit_m": fit_m, "fit_b": fit_b, "comparison": comparison,
                   "dif": dif_all, "dif_known": dif_known, "cv": cv, "risk": risk, "evidence": evidence,
                   "recovery": rec, "pair": pair, "warnings": warnings, "diagnostics": diagnostics,
                   "n_scored": int((sc["status_math"] == "computed").sum()),
                   "n_insufficient": int((sc["status_math"] != "computed").sum())}
        report.write_reports(out, context)
        report.write_cards(out, context, bank)
        from edumetria.reporting.pdf import write_pdf
        write_pdf(out, context)

        elapsed = time.perf_counter() - t_start
        _json(out / "run_status.json", {"status": "succeeded", "run_id": run_id, "elapsed_seconds": elapsed,
                                        "converged_math6": fit_m.converged,
                                        "converged_belong6": bool(grm_ok and fit_b.converged)})
        manifest = build_manifest(
            run_id=run_id, purpose=purpose, data_origin="synthetic", dataset_hash_=batch.dataset_hash,
            seed=int(cfg["seed"]),
            method={"math6": "2PL MML-EM (Bock-Aitkin), 1PL comparador", "belong6": "GRM MML-EM",
                    "scoring": f"EAP, prior {PRIOR_DESCRIPTION}", "dif": "Mantel-Haenszel + regressão logística LR, BH",
                    "engine": "python-native (edumetria.irt)"},
            fit_options={"n_quad": 61, "quad_range": [-6, 6], "tol": 1e-4, "se": "crossprod"},
            sample_design={"scenario": cfg["scenario_id"], "n_students": cfg["population"]["n_students"],
                           "n_schools": cfg["population"]["n_schools"], "snapshot_id": batch.snapshot_id},
            split_manifest=risk.get("split", {}), warnings=warnings, artifacts_dir=out,
            instrument_versions=[cfg["math"]["instrument_version_id"], cfg["belonging"]["instrument_version_id"]])
        manifest_hash = write_manifest(manifest, out)
        log_event(logger, "run.succeeded", run_id=run_id, elapsed_seconds=round(elapsed, 2))
        return {"run_id": run_id, "run_dir": str(out), "status": "succeeded", "manifest_hash": manifest_hash,
                "snapshot_id": batch.snapshot_id, "converged": bool(fit_m.converged), "elapsed_seconds": elapsed,
                "n_extreme_ok": int(len(extremes))}
    except PipelineBlocked:
        log_event(logger, "run.blocked", level=logging.WARNING, run_id=run_id)
        raise
    except Exception as exc:
        _json(out / "run_status.json", {"status": "failed", "run_id": run_id, "error_code": type(exc).__name__})
        log_event(logger, "run.failed", level=logging.ERROR, run_id=run_id, error_code=type(exc).__name__)
        raise
    finally:
        logger.removeHandler(fh)
        fh.close()


def _structure_block(Xm, mnames, Xb, bnames, group) -> dict:
    """CFA ordinal (lavaan WLSMV) e invariância por grupo de auditoria — só se
    R + lavaan estiverem disponíveis; caso contrário, status explícito."""
    from edumetria.irt import r_engine
    if not r_engine.available():
        return {"status": "not_assessed", "reason": "Rscript + lavaan indisponíveis (parte bloqueada, não substituída)"}
    out = {"status": "computed"}
    for key, X, names in (("cfa_math6", Xm, mnames), ("cfa_belong6", Xb, bnames)):
        try:
            out[key] = r_engine.cfa_ordinal(X, names)
        except Exception as exc:  # falha registrada, nunca mascarada
            out[key] = {"status": "failed", "error": type(exc).__name__}
    try:
        out["invariance_belong6"] = r_engine.invariance(Xb, bnames, group)
    except Exception as exc:
        out["invariance_belong6"] = {"status": "failed", "error": type(exc).__name__}
    return out


def _uncertainty_pair(sc: pd.DataFrame) -> dict:
    """Dois estudantes artificiais com estimativas parecidas e incertezas
    diferentes (roteiro de demo, 2:30–4:00). Selecionados dos dados do run."""
    ok = sc[sc["status_math"] == "computed"].copy()
    ok["bucket"] = (ok["theta_math"] * 10).round()
    best = None
    for _, g in ok.groupby("bucket"):
        if len(g) < 2:
            continue
        hi, lo = g.loc[g["psd_math"].idxmax()], g.loc[g["psd_math"].idxmin()]
        gap = hi["psd_math"] - lo["psd_math"]
        if best is None or gap > best[0]:
            best = (gap, hi, lo)
    if best is None:
        return {}
    _, hi, lo = best
    cols = ["subject_ref", "theta_math", "psd_math", "q05_math", "q95_math", "n_answered_math"]
    return {"more_uncertain": hi[cols].to_dict(), "less_uncertain": lo[cols].to_dict()}


def _risk_block(ds, sc: pd.DataFrame, cfg: dict) -> dict:
    scores = sc.rename(columns={"subject_ref": "student_ref"}).copy()
    psy = ["theta_math", "psd_math"] + (["theta_belong", "psd_belong"] if "theta_belong" in scores else [])
    for col in ("theta_belong", "psd_belong"):
        if col not in scores:
            scores[col] = np.nan  # GRM não ajustado: coluna ausente explicitamente, fora do modelo B2
    scores = scores[["student_ref", "theta_math", "psd_math", "theta_belong", "psd_belong", "available_at"]]
    leak = bool(cfg["leakage"]["inject_future_feature"])
    try:
        if leak:
            build_snapshot(ds.attendance, 30, scores, inject_future_feature=True)
    except LeakageError as exc:
        leak_msg = str(exc)
    else:
        leak_msg = None
    train_s, test_s = split_schools(ds.students["school_id"].tolist())
    snaps = {t0: build_snapshot(ds.attendance, t0, scores) for t0 in (20, 30, 40, 45)}
    train = pd.concat([snaps[20], snaps[30]])
    train = train[train["school_id"].isin(train_s)]
    test = snaps[40][snaps[40]["school_id"].isin(test_s)]
    groups = ds.students.set_index("student_ref").loc[test["student_ref"], "audit_group"].to_numpy()
    ev = evaluate_baselines(train, test, groups_test=groups, psycho_features=psy)
    ev["b2_psycho_features"] = psy
    ev["split"] = {"train_t0_days": [20, 30], "test_t0_days": [40], "train_schools": train_s, "test_schools": test_s,
                   "horizon_days": 20, "embargo": "escolas de teste disjuntas do treino; sem estudante em comum"}
    ev["censored_example"] = {"t0_day": 45, "n": int(len(snaps[45])),
                              "target_status": snaps[45]["target_status"].unique().tolist()}
    ev["leakage_check"] = {"injected": leak, "blocked": bool(leak_msg), "message": leak_msg}
    ev["target_definition"] = ("proxy sintético: ≥5 faltas não justificadas nos 20 dias letivos seguintes a t0; "
                               "não é definição oficial de abandono/evasão")
    return ev


def _evidence_report(run_id, cfg, cv, ctt_test, ctt_items, fit_m, fit_b, grm_ok, diag, dif, risk, batch, sc):
    S = EvidenceStatus
    alpha = ctt_test["math6"]["alpha"]
    flagged = dif.loc[dif.get("flagged", pd.Series(False)).fillna(False).astype(bool), "item"].tolist()
    b2b1 = risk["bootstrap"].get("B2_minus_B1_auc", {})
    return PsychometricEvidenceReport(
        report_id=f"evr-{run_id}",
        instrument_version_id=cfg["math"]["instrument_version_id"],
        population_and_purpose=("População artificial (6º ano, 2 municípios fictícios); propósito: demonstrar "
                                "engenharia de medição — sem uso decisório."),
        data_origin="synthetic",
        content_review=EvidenceSection(
            status=S.EXPLORATORY, run_id=run_id,
            summary=(f"S-CVI/Ave={cv['s_cvi_ave']:.2f} com pareceres SIMULADOS; itens para revisão: "
                     f"{', '.join(cv['items_needing_review']) or 'nenhum'}. Não conta como evidência humana."),
            details={"evidence_origin": cv["evidence_origin"], "counts_as_human_evidence": False}),
        response_process=EvidenceSection(status=S.NOT_ASSESSED,
                                         summary="Entrevistas cognitivas não realizadas (exige piloto aprovado)."),
        dimensionality=EvidenceSection(
            status=S.EXPLORATORY, run_id=run_id,
            summary=(f"Triagem por autovalores (razão 1º/2º={diag['math6']['dimensionality'].get('ratio_first_second', float('nan')):.2f}) "
                     f"e Q3 ({len(diag['math6']['q3_flags'])} pares sinalizados). CFA ordinal: ver seção structure_invariance."),
            details={"q3_flags": diag["math6"]["q3_flags"][:10]}),
        ctt=EvidenceSection(
            status=S.SUPPORTED if alpha.get("alpha") else S.INSUFFICIENT, run_id=run_id,
            summary=(f"α={alpha.get('alpha', float('nan')):.3f} (IC95% {alpha.get('ci_low', float('nan')):.3f}–"
                     f"{alpha.get('ci_high', float('nan')):.3f}, n={alpha['n_complete']} casos completos). "
                     f"{int((ctt_items['flags'].fillna('') != '').sum())} itens com flags investigativas."),
            details={"evidence_basis": "synthetic_simulation"}),
        irt=EvidenceSection(
            status=S.SUPPORTED if fit_m.converged else S.INSUFFICIENT, run_id=run_id,
            summary=(f"2PL convergiu={fit_m.converged} em {fit_m.iterations} ciclos; GRM "
                     f"{'convergiu=' + str(fit_b.converged) if grm_ok else 'falhou'}; "
                     f"{len(fit_m.warnings)} avisos de item."),
            details={"evidence_basis": "synthetic_simulation", "engine": "python-native"}),
        precision=EvidenceSection(
            status=S.SUPPORTED, run_id=run_id,
            summary=(f"posterior_sd mediano={sc['psd_math'].median():.3f}; "
                     f"{int((sc['status_math'] != 'computed').sum())} estudantes sem evidência suficiente (θ ausente)."),
            details={"evidence_basis": "synthetic_simulation"}),
        dif=EvidenceSection(
            status=S.EXPLORATORY, run_id=run_id,
            summary=(f"{len(flagged)} itens sinalizados para revisão humana ({', '.join(flagged) or 'nenhum'}); "
                     "nenhuma remoção automática."),
            details={"review_state": "pending_human_review" if flagged else "no_action"}),
        external_relations=EvidenceSection(
            status=S.EXPLORATORY, run_id=run_id,
            summary=(f"AUC B2−B1 (escolas externas, t0=40) = {b2b1.get('mean', float('nan')):.3f} "
                     f"IC95% [{b2b1.get('ci95', [float('nan')] * 2)[0]:.3f}; {b2b1.get('ci95', [float('nan')] * 2)[1]:.3f}]. "
                     "Relação gerada pela simulação — não prova ganho real."),
        ),
        structure_invariance=_structure_section(run_id, diag.get("structure", {})),
        limitations=[
            "Todos os dados são sintéticos; nenhuma conclusão sobre estudantes, escolas ou redes reais.",
            "Pareceres de juízes são simulados; nenhuma revisão humana real ocorreu.",
            "Sem entrevistas cognitivas; linking entre versões só em estudo simulado (scripts/p2_studies.py).",
            "Escala interna (θ ~ N(0,1)) não é comparável a SAEB, ENEM ou PISA.",
            "Alvo preditivo é proxy demonstrativo, não definição de evasão.",
        ],
        prohibited_uses=["Decisão automática sobre estudantes", "Ranking punitivo de escolas/docentes",
                         "Diagnóstico psicológico", "Comparação com escalas oficiais"],
        approval_state="candidate — requer liberação manual por psicometrista",
        artifacts=["ctt_items.csv", "item_parameters_math6.csv", "item_parameters_belong6.csv",
                   "fit_diagnostics.json", "dif_report.csv", "precision_curves.json", "risk_evaluation.json",
                   "content_validity.json", "manifest.json"],
        lineage={"report": run_id, "snapshot": batch.snapshot_id, "dataset_hash": batch.dataset_hash,
                 "instrument_versions": [cfg["math"]["instrument_version_id"],
                                         cfg["belonging"]["instrument_version_id"]],
                 "item_bank": "configs/item_bank.yaml", "schema_version": SCHEMA_VERSION},
    )


def _structure_section(run_id: str, st: dict) -> EvidenceSection:
    S = EvidenceStatus
    if st.get("status") != "computed":
        return EvidenceSection(status=S.NOT_ASSESSED, run_id=run_id, summary=st.get("reason", "não avaliado"))
    parts, ok = [], True
    for key, label in (("cfa_math6", "matemática"), ("cfa_belong6", "pertencimento")):
        fm = st.get(key, {}).get("fit_measures")
        if fm:
            parts.append(f"CFA 1 fator {label}: CFI={fm['cfi.scaled']:.3f}, RMSEA={fm['rmsea.scaled']:.3f}, "
                         f"SRMR={fm['srmr']:.3f}")
        else:
            ok = False
            parts.append(f"CFA {label}: falhou")
    inv = st.get("invariance_belong6", {})
    lrt = inv.get("lrt")
    if lrt:
        p_thr, p_load = lrt[1].get("Pr(>Chisq)"), lrt[2].get("Pr(>Chisq)")
        parts.append(f"invariância pertencimento (A×B): limiares p={p_thr:.3f}, +cargas p={p_load:.3f}")
    return EvidenceSection(status=S.EXPLORATORY if ok else S.INSUFFICIENT, run_id=run_id,
                           summary="; ".join(parts) + ". Índices descritivos — nenhum limiar isolado autoriza uso.",
                           details={"evidence_basis": "synthetic_simulation", "engine": "R/lavaan WLSMV"})
