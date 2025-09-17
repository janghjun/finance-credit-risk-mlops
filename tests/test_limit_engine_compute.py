from serving.limit_engine import compute_offers


def test_compute_offers_happy_flow():
    req = {
        "as_of": "2025-09-01",
        "profile": {
            "score_band": "B",
            "pd": 0.05,
            "income_yearly": 60_000_000,
            "existing_debt_payment_monthly": 4_000_000,
            "region": "capital",
            "loan_type": "credit",
            "rate_type": "variable",
        },
        "candidates": [
            {"issuer": "BC_CARD", "product": "CARD_LOAN_A"},
            {"issuer": "SHINHAN", "product": "PERSONAL_LOAN_PLUS"},
        ],
    }
    res = compute_offers(**req)
    assert "offers" in res and len(res["offers"]) == 2
    assert "best_offer" in res and res["best_offer"] is not None
    for o in res["offers"]:
        lim = o["limits"]
        # 최종 한도는 세 한도의 min
        assert lim["final_limit"] == min(
            lim["regulation_limit"], lim["policy_limit"], lim["model_limit"]
        )


def test_missing_policy_raises():
    req = {
        "as_of": "2025-09-01",
        "profile": {
            "score_band": "B",
            "pd": 0.05,
            "income_yearly": 60_000_000,
            "existing_debt_payment_monthly": 4_000_000,
            "region": "capital",
            "loan_type": "credit",
            "rate_type": "variable",
        },
        "candidates": [{"issuer": "NOPE", "product": "UNKNOWN"}],  # 존재하지 않음
    }
    try:
        compute_offers(**req)
        assert False, "Expected error for missing policy"
    except Exception as e:
        assert "Policy not found" in str(e)
