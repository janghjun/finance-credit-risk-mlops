from pathlib import Path
import json, datetime as dt

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "rules"


def synthesize_stress_dsr_rule():
    rule = {
        "rule_id": "KR.DSR.STRESS.V1",
        "type": "STRESS_DSR",
        "version": "1.0",
        "effective_from": "2025-07-01",
        "expires_on": None,
        "payload": {
            "dsr_limit": 0.40,
            "stress_spread_capital": 0.0150,
            "stress_spread_noncapital": 0.0075,
            "noncapital_relief_expires": "2025-12-31",
            "credit_line_threshold": 100000000,
        },
        "_meta": {
            "source": "simulated",
            "generated_at": dt.datetime.utcnow().isoformat(),
        },
    }
    return rule


def main():
    out = RULES / "regulation.jsonl"
    candidates = [synthesize_stress_dsr_rule()]
    with out.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print("Wrote", out)


if __name__ == "__main__":
    main()
