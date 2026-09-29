"""Gerador reprodutível de dados sintéticos com ground truth (trilha A, seção 14).

Tudo é artificial: identificadores sintéticos, nenhum nome/CPF/telefone,
grupo de auditoria A/B sem significado demográfico. O gabarito verdadeiro
(parâmetros, θ, âncoras, DIF) fica em ``truth`` para testes de recuperação —
nunca é consumido pelo pipeline de análise.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from edumetria.domain.enums import ResponseStatus
from edumetria.irt.models import grm_category_probs, logistic

ROOT = Path(__file__).resolve().parents[3]
SCENARIO_DIR = ROOT / "configs" / "scenarios"
ITEM_BANK = ROOT / "configs" / "item_bank.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_scenario(name_or_path: str | Path) -> dict:
    """Carrega cenário YAML resolvendo ``extends``. Aceita 's2' ou caminho."""
    p = Path(name_or_path)
    if not p.exists():
        matches = sorted(SCENARIO_DIR.glob(f"{name_or_path}_*.yaml")) or sorted(
            SCENARIO_DIR.glob(f"{name_or_path}.yaml"))
        if str(name_or_path) in ("s0", "base"):
            matches = [SCENARIO_DIR / "base.yaml"]
        if not matches:
            raise FileNotFoundError(f"cenário não encontrado: {name_or_path}")
        p = matches[0]
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    parent = cfg.pop("extends", None)
    if parent:
        cfg = _deep_merge(load_scenario(p.parent / parent), cfg)
    return cfg


def load_item_bank() -> dict:
    return yaml.safe_load(ITEM_BANK.read_text(encoding="utf-8"))


@dataclass
class SyntheticDataset:
    scenario: dict
    items: pd.DataFrame
    students: pd.DataFrame
    responses: pd.DataFrame
    attendance: pd.DataFrame
    judge_reviews: pd.DataFrame
    truth: dict = field(default_factory=dict)

    def save(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.items.to_csv(out / "items.csv", index=False)
        self.students.drop(columns=[c for c in self.students.columns if c.startswith("true_")]).to_csv(
            out / "students.csv", index=False)
        self.responses.to_csv(out / "responses.csv", index=False)
        self.attendance.to_csv(out / "attendance.csv", index=False)
        self.judge_reviews.to_csv(out / "judge_reviews.csv", index=False)
        (out / "scenario.yaml").write_text(yaml.safe_dump(self.scenario, allow_unicode=True, sort_keys=False),
                                           encoding="utf-8")
        truth_dir = out / "_truth"
        truth_dir.mkdir(exist_ok=True)
        self.students[["student_ref"] + [c for c in self.students.columns if c.startswith("true_")]].to_csv(
            truth_dir / "true_theta.csv", index=False)
        pd.DataFrame(self.truth["math_params"]).to_csv(truth_dir / "true_math_params.csv", index=False)
        pd.DataFrame(self.truth["belong_params"]).to_csv(truth_dir / "true_belong_params.csv", index=False)
        return out


def _day_to_ts(day: int | np.ndarray) -> pd.Series | pd.Timestamp:
    base = pd.Timestamp("2026-03-02")  # início letivo fictício
    return base + pd.to_timedelta(np.asarray(day) * 1, unit="D")


def generate(scenario: dict | str) -> SyntheticDataset:
    cfg = load_scenario(scenario) if not isinstance(scenario, dict) else scenario
    bank = load_item_bank()
    rng = np.random.default_rng(int(cfg["seed"]))
    pop = cfg["population"]
    n = int(pop["n_students"])

    # ---------------- população ----------------
    n_schools = int(pop["n_schools"])
    school_ids = [f"SCH{s + 1:02d}" for s in range(n_schools)]
    school_muni = {sid: f"MUN{(i % pop['n_municipalities']) + 1}" for i, sid in enumerate(school_ids)}
    school = rng.choice(school_ids, size=n)
    group = np.where(rng.random(n) < pop["audit_group_share_b"], "B", "A")
    rho = pop["theta_corr_math_belong"]
    z = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], size=n)
    theta_math = z[:, 0] + pop.get("theta_mean_shift", 0.0) + np.where(
        group == "B", pop.get("theta_mean_shift_group_b", 0.0), 0.0)
    theta_belong = z[:, 1]
    students = pd.DataFrame({
        "student_ref": [f"synthetic-student-{i + 1:05d}" for i in range(n)],
        "school_id": school,
        "municipality_id": [school_muni[s] for s in school],
        "audit_group": group,
        "true_theta_math": theta_math,
        "true_theta_belong": theta_belong,
    })

    # ---------------- itens de matemática (2PL) ----------------
    mcfg = cfg["math"]
    math_items = bank["math_items"]
    J = len(math_items)
    a = rng.lognormal(mcfg["a_lognormal"]["meanlog"], mcfg["a_lognormal"]["sdlog"], J)
    b = rng.normal(mcfg["b_normal"]["mean"], mcfg["b_normal"]["sd"], J)
    ids = [it["id"] for it in math_items]
    idx = {k: i for i, k in enumerate(ids)}
    for it in mcfg.get("low_discrimination_items", []):
        a[idx[it]] = 0.15
    for it, bval in (mcfg.get("extreme_items") or {}).items():
        b[idx[it]] = float(bval)
    for dr in mcfg.get("param_drift", []):
        b[idx[dr["item"]]] += float(dr["delta_b"])
    dif_items = {d["item"]: d for d in mcfg.get("dif", [])}

    th_eff = np.repeat(theta_math[:, None], J, axis=1)
    sd2 = mcfg.get("second_dimension")
    if sd2:  # S6: parte dos itens mede outra dimensão correlacionada
        z2 = rng.normal(0, 1, n)
        theta2 = sd2["corr"] * (theta_math - theta_math.mean()) / theta_math.std() + np.sqrt(1 - sd2["corr"] ** 2) * z2
        for it in sd2["items"]:
            th_eff[:, idx[it]] = theta2
        students["true_theta_dim2"] = theta2
    tl = mcfg.get("testlet")
    if tl:
        gamma = rng.normal(0, tl["sd"], n)
        for it in tl["items"]:
            th_eff[:, idx[it]] += gamma
    A = np.tile(a, (n, 1))
    Bm = np.tile(b, (n, 1))
    isB = group == "B"
    for it, d in dif_items.items():
        j = idx[it]
        if d["type"] == "uniform":
            Bm[isB, j] += float(d["delta_b"])
        else:
            A[isB, j] *= float(d["a_ratio"])
    P = logistic(A * (th_eff - Bm))
    correct = rng.random((n, J)) < P

    # respostas brutas (alternativa marcada) — distratores com plausibilidade decrescente
    letters = np.array(["A", "B", "C", "D"])
    raw = np.empty((n, J), dtype=object)
    for j, it in enumerate(math_items):
        wrong = [L for L in letters if L != it["key"]]
        w = np.array([0.55, 0.30, 0.15])
        rng.shuffle(w)
        pick = rng.choice(wrong, size=n, p=w)
        raw[:, j] = np.where(correct[:, j], it["key"], pick)
    scored = correct.astype(float)
    status = np.full((n, J), ResponseStatus.ANSWERED.value, dtype=object)

    miss = cfg["missing"]
    omit_p = np.full((n, J), miss["mcar_omit_rate"])
    if miss.get("mnar_strength", 0) > 0:
        omit_p = omit_p + 0.08 * logistic(-miss["mnar_strength"] * theta_math - 1.5)[:, None]
    omitted = rng.random((n, J)) < omit_p
    status[omitted] = ResponseStatus.OMITTED.value
    if miss.get("not_reached_rate", 0) > 0:
        nr = rng.random(n) < miss["not_reached_rate"]
        start = rng.integers(J - 6, J - 1, size=n)
        for i in np.where(nr)[0]:
            status[i, start[i]:] = ResponseStatus.NOT_REACHED.value
    ext = int(miss.get("extreme_patterns", 0))
    if ext:
        rows = rng.choice(n, size=ext, replace=False)
        half = ext // 2
        for r_i, i in enumerate(rows):
            status[i, :] = ResponseStatus.ANSWERED.value
            val = 1.0 if r_i < half else 0.0
            scored[i, :] = val
            for j, it in enumerate(math_items):
                raw[i, j] = it["key"] if val == 1 else [L for L in letters if L != it["key"]][0]
    non_answered = status != ResponseStatus.ANSWERED.value
    scored[non_answered] = np.nan
    raw[non_answered] = None

    # ---------------- itens de pertencimento (GRM) ----------------
    bcfg = cfg["belonging"]
    bel_items = bank["belonging_items"]
    Jb = len(bel_items)
    ab = rng.lognormal(bcfg["a_lognormal"]["meanlog"], bcfg["a_lognormal"]["sdlog"], Jb)
    base_thr = np.array(bcfg["thresholds_base"])
    Bb = np.sort(base_thr[None, :] + rng.normal(0, bcfg["thresholds_jitter_sd"], (Jb, 3)), axis=1)
    bids = [it["id"] for it in bel_items]
    for it in bcfg.get("rare_top_category_items", []):
        Bb[bids.index(it), 2] = 2.9
    Y = np.zeros((n, Jb))
    for j in range(Jb):
        Pc = grm_category_probs(theta_belong, ab[j], Bb[j])
        u = rng.random(n)[:, None]
        Y[:, j] = (u > np.cumsum(Pc, axis=1)).sum(axis=1)
    Y = np.minimum(Y, 3)
    bstatus = np.full((n, Jb), ResponseStatus.ANSWERED.value, dtype=object)
    bstatus[rng.random((n, Jb)) < miss["mcar_omit_rate"]] = ResponseStatus.OMITTED.value
    j02 = bids.index("B02")
    bstatus[rng.random(n) < bcfg["b02_not_applicable_rate"], j02] = ResponseStatus.NOT_APPLICABLE.value
    Ys = Y.astype(float)
    Ys[bstatus != ResponseStatus.ANSWERED.value] = np.nan

    # ---------------- formato longo com tempos ----------------
    ad = cfg["attendance"]
    assess_day = int(ad["assessment_day"])
    avail_day = int(ad["scores_available_day"])
    event_ts = _day_to_ts(assess_day)
    avail_ts = _day_to_ts(avail_day)
    recs = []
    for inst, item_list, stat, sv, rv, ver in (
        ("math6", ids, status, scored, raw, mcfg["instrument_version_id"]),
        ("belong6", bids, bstatus, Ys, None, bcfg["instrument_version_id"]),
    ):
        nI = len(item_list)
        df = pd.DataFrame({
            "student_ref": np.repeat(students["student_ref"].to_numpy(), nI),
            "school_id": np.repeat(students["school_id"].to_numpy(), nI),
            "instrument_id": inst,
            "item_version_id": [f"{ver.split('-v')[0]}-{it}-v1" for it in item_list] * n,
            "raw_response": (rv.ravel() if rv is not None else np.where(np.isnan(sv.ravel()), None,
                                                                         sv.ravel().astype(object))),
            "scored_value": sv.ravel(),
            "response_status": stat.ravel(),
            "scoring_rule_version": "math6-key-v1" if inst == "math6" else "belong6-ord-v1",
            "form_id": f"{inst}-F1-v1",
            "attempt": 1,
        })
        recs.append(df)
    responses = pd.concat(recs, ignore_index=True)
    responses["session_id"] = "sess-" + responses["school_id"] + "-d" + str(assess_day)
    responses["event_time"] = event_ts
    responses["ingested_at"] = event_ts + pd.Timedelta(hours=6)
    responses["available_at"] = avail_ts
    responses["data_origin"] = "synthetic"

    an = cfg["admin_anomalies"]
    extra = []
    if an["duplicate_rows"]:
        extra.append(responses.sample(an["duplicate_rows"], random_state=1))
    if an["unknown_version_rows"]:
        bad = responses.sample(an["unknown_version_rows"], random_state=2).copy()
        bad["item_version_id"] = bad["item_version_id"].str.replace("-v1", "-v9", regex=False)
        extra.append(bad)
    if an["invalid_category_rows"]:
        bad = responses[responses["instrument_id"] == "belong6"].sample(an["invalid_category_rows"],
                                                                        random_state=3).copy()
        bad["raw_response"] = 7
        bad["scored_value"] = 7.0
        bad["response_status"] = ResponseStatus.ANSWERED.value
        bad["attempt"] = 2
        extra.append(bad)
    if an["late_rows"]:
        late = responses.sample(an["late_rows"], random_state=4).copy()
        late["ingested_at"] = late["event_time"] + pd.Timedelta(days=40)
        late["attempt"] = 3
        extra.append(late)
    if extra:
        responses = pd.concat([responses, *extra], ignore_index=True)
    responses.insert(0, "response_id", [f"r{i:07d}" for i in range(len(responses))])

    # ---------------- frequência diária ----------------
    n_days = int(ad["n_days"])
    school_eff = {s: rng.normal(0, ad["school_sd"]) for s in school_ids}
    person = rng.normal(0, ad["person_sd"], n)
    base = (ad["base_logit"] + np.array([school_eff[s] for s in school]) + person
            + ad["beta_belong"] * theta_belong + ad["beta_math"] * theta_math)
    deteriorates = rng.random(n) < ad["deterioration_share"] * (1 + logistic(-theta_belong))
    days = np.arange(1, n_days + 1)
    logit_day = base[:, None] + np.where(
        (days[None, :] >= ad["deterioration_start_day"]) & deteriorates[:, None], ad["deterioration_logit"], 0.0)
    absent = rng.random((n, n_days)) < logistic(logit_day)
    justified = absent & (rng.random((n, n_days)) < ad["justified_share"])
    attendance = pd.DataFrame({
        "student_ref": np.repeat(students["student_ref"].to_numpy(), n_days),
        "school_id": np.repeat(school, n_days),
        "school_day": np.tile(days, n),
        "present": (~absent).ravel().astype(int),
        "absence_justified": justified.ravel().astype(int),
    })
    attendance["event_time"] = _day_to_ts(attendance["school_day"].to_numpy())
    attendance["available_at"] = attendance["event_time"] + pd.Timedelta(days=1)
    students["true_deteriorates"] = deteriorates

    # ---------------- pareceres simulados de juízes ----------------
    judge_reviews = simulate_judge_reviews(ids + bids, rng)

    items_rows = []
    for j, it in enumerate(math_items):
        items_rows.append({
            "item_id": it["id"], "instrument_id": "math6",
            "item_version_id": f"math6-{it['id']}-v1", "axis": it["axis"], "demand": it["demand"],
            "key": it["key"], "stem": it["stem"], "bncc_code": None, "n_categories": 2})
    for it in bel_items:
        items_rows.append({
            "item_id": it["id"], "instrument_id": "belong6",
            "item_version_id": f"belong6-{it['id']}-v1", "axis": "pertencimento", "demand": None,
            "key": None, "stem": it["stem"], "bncc_code": None, "n_categories": 4})
    items = pd.DataFrame(items_rows)

    truth = {
        "math_params": {"item": ids, "a": a, "b": b,
                        "dif": [it in dif_items for it in ids],
                        "anchor": [it not in dif_items for it in ids]},
        "belong_params": {"item": bids, "a": ab, "b1": Bb[:, 0], "b2": Bb[:, 1], "b3": Bb[:, 2]},
        "dif_items": list(dif_items),
        "testlet_items": (tl or {}).get("items", []),
        "second_dimension_items": (sd2 or {}).get("items", []),
        "leakage": bool(cfg["leakage"]["inject_future_feature"]),
    }
    return SyntheticDataset(cfg, items, students, responses, attendance, judge_reviews, truth)


def simulate_judge_reviews(item_ids: list[str], rng: np.random.Generator, n_judges: int = 6) -> pd.DataFrame:
    """Pareceres FICTÍCIOS (evidence_origin = simulated_review). Demonstram o
    workflow; nunca integram relatório como parecer de especialistas reais."""
    rows = []
    criteria = ["relevancia", "clareza", "alinhamento", "adequacao_etaria", "acessibilidade"]
    for it in item_ids:
        for jdg in range(n_judges):
            for c in criteria:
                base = 3.4
                if it == "B02" and c in ("relevancia", "alinhamento"):
                    base = 2.1  # desalinhamento intencional (mede suporte, não pertencimento)
                if it == "A23" and c == "clareza":
                    base = 2.6  # enunciado com duas operações — clareza discutível
                score = int(np.clip(np.round(rng.normal(base, 0.6)), 1, 4))
                rows.append({"item_id": it, "judge_ref": f"juiz-ficticio-{jdg + 1}", "criterion": c,
                             "rating": score, "evidence_origin": "simulated_review",
                             "comment": ("possível desalinhamento com o construto" if it == "B02" and c == "alinhamento"
                                         and score <= 2 else "")})
    return pd.DataFrame(rows)
