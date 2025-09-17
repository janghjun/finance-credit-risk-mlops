from pathlib import Path
import sys

# 루트 경로 import 보장 (CI/로컬 어디서 돌려도 안전)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from serving.app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_offer_limits_ok():
    body = {
        "as_of": "2025-09-01",
        "segment": "personal",
        "profile": {
            "score_band": "B",
            "pd": 0.05,
            "income_yearly": 60000000,
            "existing_debt_payment_monthly": 4000000,
            "region": "capital",
            "loan_type": "credit",
            "rate_type": "variable",
        },
        "candidates": [
            {"issuer": "BC_CARD", "product": "CARD_LOAN_A"},
            {"issuer": "SHINHAN", "product": "PERSONAL_LOAN_PLUS"},
        ],
    }
    r = client.post("/api/offer_limits", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "offers" in data and len(data["offers"]) == 2
    assert "best_offer" in data and data["best_offer"] is not None


def test_favicon_graceful():
    # 파비콘 라우팅을 추가 안 했어도 404면 OK, 추가했다면 204/200도 허용
    r = client.get("/favicon.ico")
    assert r.status_code in (200, 204, 404)
