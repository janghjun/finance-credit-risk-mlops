from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import json
from pathlib import Path
import math
import datetime as dt

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules"
CATALOG = ROOT / "catalog" / "products.csv"


# ---------------------------
# Data classes
# ---------------------------
@dataclass
class Profile:
    score_band: str
    pd: float
    income_yearly: int
    existing_debt_payment_monthly: int
    region: str  # "capital" | "noncapital"
    loan_type: str  # "credit" | "mortgage"
    rate_type: str  # "variable" | "fixed"

    exposure_ratio: Optional[float] = None  # corporate용 (0~1)
    guarantee_ratio: Optional[float] = None  # sme용 (0~1)


@dataclass
class Candidate:
    issuer: str
    product: str


# ---------------------------
# Utils
# ---------------------------
def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def pick_rule(
    rules: List[Dict[str, Any]], rule_type: str, ref_date: str
) -> Dict[str, Any]:
    target = None
    ref = dt.date.fromisoformat(ref_date)
    for r in rules:
        if r["type"] != rule_type:
            continue
        eff = dt.date.fromisoformat(r["effective_from"])
        exp = dt.date.fromisoformat(r["expires_on"]) if r.get("expires_on") else None
        if eff <= ref and (exp is None or ref <= exp):
            target = r
            break
    if not target:
        raise ValueError(f"No active rule found for {rule_type} at {ref_date}")
    return target


def ann_to_monthly_rate(apr: float) -> float:
    # simple nominal to monthly
    return apr / 12.0


def pv_of_annuity(monthly_payment: float, monthly_rate: float, n_months: int) -> float:
    if monthly_rate <= 0:
        return monthly_payment * n_months
    return monthly_payment * (1 - (1 + monthly_rate) ** (-n_months)) / monthly_rate


# ---------------------------
# Core calculations
# ---------------------------
def regulation_limit(
    profile: Profile, as_of: str, tenor_months: int, base_rate_apr: float
) -> int:
    rules = load_jsonl(RULES / "regulation.jsonl")

    dsr_rule = pick_rule(rules, "STRESS_DSR", as_of)["payload"]

    dsr_limit = dsr_rule["dsr_limit"]  # e.g., 0.40
    if profile.region == "capital":
        stress_spread = dsr_rule["stress_spread_capital"]  # 1.50%p
    else:
        # 지방 특례 기한 이후엔 capital과 동일 처리(간단화). 실제로는 expires_on 비교 필요.
        noncap_spread = dsr_rule["stress_spread_noncapital"]
        relief_end = dt.date.fromisoformat(dsr_rule["noncapital_relief_expires"])
        stress_spread = (
            noncap_spread
            if dt.date.fromisoformat(as_of) <= relief_end
            else dsr_rule["stress_spread_capital"]
        )

    # 적용 금리 = base_rate + stress_spread
    applied_apr = base_rate_apr + stress_spread
    r_m = ann_to_monthly_rate(applied_apr)

    # 연간 허용 원리금 = income * dsr - 기존부채 연간 상환
    annual_allow = profile.income_yearly * dsr_limit - (
        profile.existing_debt_payment_monthly * 12
    )
    if annual_allow <= 0:
        return 0

    monthly_allow = annual_allow / 12.0
    # 허용 원리금에서 역산한 최대 대출원금(PV)
    principal = pv_of_annuity(monthly_allow, r_m, tenor_months)
    return max(0, int(math.floor(principal)))


def policy_limit(issuer_policy: Dict[str, Any], score_band: str) -> int:
    # 간단화: score_band 일치하는 정책에서 max_limit * limit_factor
    max_limit = int(issuer_policy["policy"]["max_limit"])
    factor = float(issuer_policy["policy"]["limit_factor"])
    return int(math.floor(max_limit * factor))


def model_limit(profile: Profile) -> int:
    # PoC: PD를 단순 페널티로 적용 (PD↑ → 한도↓)
    # 예: base 50,000,000에서 PD 0.05면 (1 - 0.05*0.8)=0.96 배
    base = 50_000_000
    penalty = max(0.5, 1.0 - profile.pd * 0.8)
    return int(base * penalty)


def pick_issuer_policy(issuer: str, product: str, score_band: str) -> Dict[str, Any]:
    policies = load_jsonl(RULES / "issuer_policy.jsonl")
    for p in policies:
        if (
            p["issuer"] == issuer
            and p["product"] == product
            and p["score_band"] == score_band
        ):
            return p
    raise ValueError(f"Policy not found for {issuer}/{product}/{score_band}")


def compute_offers(
    as_of: str, profile: Dict[str, Any], candidates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    pr = Profile(**profile)
    rules_all = load_jsonl(RULES / "regulation.jsonl")
    offers = []
    for c in candidates:
        pol = pick_issuer_policy(c["issuer"], c["product"], pr.score_band)
        tenor = min(int(pol["policy"]["max_tenor_months"]), 60)
        base_apr = float(pol["policy"]["base_rate_apr"])

        r_limit = regulation_limit(pr, as_of, tenor, base_apr)
        p_limit = policy_limit(pol, pr.score_band)
        m_limit = model_limit(pr)
        base_final = min(r_limit, p_limit, m_limit)

        # --- NEW: segment post-processing ---
        seg = profile.get("segment", "personal")
        final = base_final
        seg_reasons = []

        if seg == "corporate":
            exposure_ratio = float(
                profile.get("exposure_ratio", 0.10)
            )  # 입력 없으면 보수적으로 10%
            adjusted = apply_lex_limit(base_final, exposure_ratio, rules_all)
            if adjusted == 0 and base_final > 0:
                seg_reasons.append(
                    f"LEX 한도 위반: exposure_ratio={exposure_ratio:.2f}"
                )
            final = min(final, adjusted)

        elif seg == "sme":
            guarantee_ratio = float(profile.get("guarantee_ratio", 0.0))  # 0~1
            final = apply_sme_guarantee(final, guarantee_ratio, rules_all)
            seg_reasons.append(f"SME 보증 적용: guarantee_ratio={guarantee_ratio:.2f}")

        reasons = [
            f"스트레스 DSR 적용(base APR {base_apr:.3f})",
            f"발급사 정책 limit_factor {pol['policy']['limit_factor']}",
            f"모형(PD={pr.pd:.2f}) 반영",
            *seg_reasons,
        ]

        offers.append(
            {
                "issuer": c["issuer"],
                "product": c["product"],
                "limits": {
                    "regulation_limit": r_limit,
                    "policy_limit": p_limit,
                    "model_limit": m_limit,
                    "final_limit": final,
                },
                "reasons": reasons,
            }
        )

    best = max(offers, key=lambda x: x["limits"]["final_limit"]) if offers else None
    return {"offers": offers, "best_offer": best}


def apply_lex_limit(base_limit: int, exposure_ratio: float, rules: list[dict]) -> int:
    lex = [r for r in rules if r["type"] == "LEX"]
    if not lex:
        return base_limit
    payload = lex[0]["payload"]
    # 노출비율(exposure_ratio)이 한도를 직접 깎지는 않지만, 초과 시 한도 = 0 또는 경고 처리
    return 0 if exposure_ratio > payload["single_counterparty_limit"] else base_limit


def apply_sme_guarantee(
    base_limit: int, guarantee_ratio: float, rules: list[dict]
) -> int:
    g = [r for r in rules if r["type"] == "SME_GUARANTEE"]
    if not g:
        return base_limit
    payload = g[0]["payload"]
    ratio = min(guarantee_ratio, payload["max_guarantee_ratio"])
    boosted = int(base_limit * (1 + ratio * 0.5))  # 예시: 보증 85%면 최대 42.5% 가산
    cap = payload.get("max_guarantee_amount", boosted)
    return min(boosted, base_limit + cap)
