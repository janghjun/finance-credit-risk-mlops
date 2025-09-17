import math
from serving.limit_engine import regulation_limit, Profile


def test_regulation_limit_capital_stress():
    # 수도권: 1.50%p 가산
    profile = Profile(
        score_band="B",
        pd=0.05,
        income_yearly=60_000_000,
        existing_debt_payment_monthly=4_000_000,
        region="capital",
        loan_type="credit",
        rate_type="variable",
    )
    # base apr 11.7% + 1.5% = 13.2%
    principal = regulation_limit(
        profile, "2025-09-01", tenor_months=60, base_rate_apr=0.117
    )
    assert isinstance(principal, int)
    assert principal >= 0  # 허용상환 여유가 적으니 0 혹은 낮은 값이어야 함


def test_regulation_limit_noncapital_relief_before_expiry():
    # 지방 특례 기간 내: 0.75%p 가산
    profile = Profile(
        score_band="B",
        pd=0.05,
        income_yearly=120_000_000,
        existing_debt_payment_monthly=1_000_000,
        region="noncapital",
        loan_type="credit",
        rate_type="variable",
    )
    p_relief = regulation_limit(
        profile, "2025-09-01", tenor_months=60, base_rate_apr=0.113
    )
    p_after = regulation_limit(
        profile, "2026-01-10", tenor_months=60, base_rate_apr=0.113
    )
    # 특례 기간 내 한도 >= 특례 종료 후 한도 (금리 가산이 더 낮기 때문)
    assert p_relief >= p_after
