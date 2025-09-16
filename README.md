# 규제‑적응형 신용평가모형과 다중 한도 산출 엔진 (RegTech × MLOps × RAG)

이 프로젝트는 한국의 최근 금융 규제 변화(스트레스 DSR 3단계, Basel LEX 등)를 반영하여, 고객 세그먼트(개인 / 법인 / 소상공인) 및 카드사/상품별 정책을 결합한 **신용평가모형 + 규제/정책 기반 한도 엔진**을 구축하는 것을 목표로 합니다.  

> 본 설계는 공개된 정책 자료 및 금융감독원, 금융위원회, BIS/BCBS 등의 문서를 근거로 하며, 실제 사용 전 내부 정책·법무 검토 필요합니다.

---

## 1. 배경 및 정책 근거

- **스트레스 DSR 3단계 시행 (2025년 7월 1일)**  
  금융위원회는 2025년 7월부터 전체 업권(은행 + 2금융권 포함)에 대해 가계대출의 DSR(총부채원리금상환비율) 평가 시 “스트레스 금리”를 1.50%p 가산하여 적용하기로 확정했습니다. 다만, 지방 주택담보대출은 2025년 말까지 0.75%p 가산이 예외적으로 적용됩니다. 신용대출은 잔액 1억원 초과분부터 적용됨.  
- **LEX (Large Exposure) 규제 및 RCAP 평가**  
  한국은 2024년 2월부터 “Large Exposures (LEX)” 프레임워크를 시행했고, BIS RCAP 평가 보고서에서는 전반적으로 Basel LEX 기준에 대해 “대체로 준수(largely compliant)” 판정됨.  
- **대출 한도 감소 사례**  
  예컨대 연 소득 1억원, 수도권 주택담보대출 변동금리 조건에서 스트레스 DSR 3단계 시행 전후 대출 가능한 한도가 약 1억 원 이상 감소했다는 보도 있음.  

---

## 2. 목표 및 기능

- 고객 속성(개인·법인·소상공인) + 카드사/상품 정책 + 규제 요건을 결합하여 **발급사별/상품별/세그먼트별 최종 대출 한도**를 산출  
- 규정 변경 시 자동 반영(크롤링 → RAG 색인 → JSON 룰 업데이트 → 엔진 반영)  
- 신용평가모형(PD + 필요시 LGD/EAD) + 정책/규제 제한 조합으로 안정성과 실용성 확보  
- 설명가능성, 감사추적, 공정성 지표 포함  

---

## 3. 범위 및 세그먼트 구분

| 구분 | 설명 |
|---|---|
| 세그먼트 | 개인(personal), 법인(corporate), 소상공인(sme) |
| 카드사/상품 | 카드사별 신용대출/카드론/할부 상품 등 내부 정책이 다른 상품군을 분리 관리 |
| 점수 밴드 | PD 기반 스코어밴드 (예: A/B/C/D)로 상품/카드사 정책이 달라짐 |
| 규제 한도 | 스트레스 DSR, LEX 등 감독규정 + 지역/잔액/금리유형 예외 고려 |

---

## 4. 시스템 설계

### 아키텍처 개요

```
[규제 문서 소스(FSC/FSS/Basel/뉴스)] --(크롤러/변경 감지)--> [문서 저장소]
                                   └─> [청크화 + 텍스트/표/수식 파싱] → [Vector DB] → [RAG 질의/요약]
                                                             │
                    [Human‑in‑the‑loop 승인] ← JSON 룰 추출(LLM) → [Regulation Rule Engine]
                                                             │
[카드사‑상품 정책 저장소] --(issuer_policy)--> [Policy Engine]
                                                             │
[신용평가모형 (PD + 필요시 LGD/EAD)] --(feature store, MLflow)--> [Model Engine]
                                                             │
                          [Limit Engine] (최종 한도 = min(규제한도, 정책한도, 모형한도))
                                                             │
                     [API Serving + 한도 제안 / 사유서 반환]
                                                             │
           [Monitoring Module: DSR 변화 영향 / 모형 성능 / 드리프트 / 공정성]
```

---

## 5. 모형 / 정책 / 규제 한도 산출 로직

### 규제 한도(Rule Engine)
- 스트레스 DSR 적용: 차입자의 연간 원리금 상환액 ≤ 연소득 × DSR 한도 (예: 40%) 조건  
- 스트레스 금리 가산: 수도권 적용 시 1.50%p, 지방 또는 예외 지역 시 0.75%p (2025년 말까지 예외)  
- 신용대출 잔액 1억원 초과 여부 → 적용 여부 판단  

### 카드사/상품 정책 한도 (Policy Engine)
- 카드사 상품별 내부 한도 상한치, 점수 밴드별 계수, 최대 만기, 금리 스프레드 조건  
- 예: 카드사 A의 카드론 상품은 점수 밴드 B일 경우 정책한도 = 발급사 max 한도 × 0.85  

### 신용모형 (Model Engine)
- LightGBM/XGBoost 기본 PD 예측  
- 검증: 그룹 K‑Fold / 시간 순 K‑Fold 적용  
- 지표: AUC, KS, GINI, Recall@TopK, Profit Curve  

### 최종 산출 한도
- `final_limit = min(regulation_limit, policy_limit, model_limit)`  
- API 반환 시 각각의 한도 및 사유 제공  

---

## 6. 서비스 및 API 설계 (예시)

### 요청
```http
POST /api/offer_limits
Content-Type: application/json

{
  "as_of": "2025-09-01",
  "segment": "personal",
  "profile": {
    "score_band": "B",
    "pd": 0.05,
    "income_yearly": 60000000,
    "existing_debt_payment_monthly": 4000000,
    "region": "capital",
    "loan_type": "credit",
    "rate_type": "variable"
  },
  "candidates":[
    {"issuer":"BC_CARD", "product":"CARD_LOAN_A"},
    {"issuer":"SHINHAN", "product":"PERSONAL_LOAN_PLUS"}
  ]
}
```

### 응답
```json
{
  "offers":[
    {
      "issuer":"BC_CARD",
      "product":"CARD_LOAN_A",
      "limits":{
        "regulation_limit": 25000000,
        "policy_limit": 32000000,
        "model_limit": 30000000,
        "final_limit": 25000000
      },
      "reasons":[
        "스트레스 DSR 3단계 규제 적용: 금리 +1.50%p",
        "발급사 정책 limit_factor 0.80 (점수밴드 B)",
        "모형 PD 기반 한도 계산 결과"
      ]
    },
    {
      "issuer":"SHINHAN",
      "product":"PERSONAL_LOAN_PLUS",
      "limits":{
        "regulation_limit": 25000000,
        "policy_limit": 35000000,
        "model_limit": 33000000,
        "final_limit": 25000000
      },
      "reasons":[
        "스트레스 DSR 3단계 규제 적용",
        "발급사 정책 limit_factor 0.90",
        "신용점수 밴드 고려"
      ]
    }
  ],
  "best_offer": {
    "issuer":"SHINHAN",
    "product":"PERSONAL_LOAN_PLUS",
    "final_limit":25000000
  }
}
```

---

## 7. MLOps 및 모니터링

- **저장/레이크**: Delta/Iceberg – Bronze → Silver → Gold  
- **변환**: dbt 또는 Spark/Polars  
- **Feature Store**: Feast  
- **품질**: Great Expectations (스키마/분포/참조무결성 검증)  
- **실험/레지스트리**: MLflow  
- **배포**: FastAPI + Docker + GitHub Actions CI/CD  
- **모니터링**: Evidently (데이터·성능 드리프트), 규정 변경 알림  
- **재학습 트리거**: (i) 규정 변경, (ii) 성능 저하, (iii) 데이터 드리프트 초과  

---

## 8. KPI

- 정확도: AUC ≥ 0.78, KS ≥ 0.35  
- 규제 위반 한도 산출률: 0%  
- 규제 변경 반영 속도: 공지 후 T+1 이내 반영  
- 설명가능성 커버리지: ≥ 90% (사유서 제공)  
- 공정성 지표: 점수밴드/지역/소득군별 성능 격차 ≤ 0.05  

---

## 9. 위험 및 유의사항

- 규제/정책 조항은 변동이 잦아 자동 감지·버전 관리 필수  
- 카드사 내부 정책 데이터는 공개가 제한적이므로 예시/가정에서 시작해야 함  
- PII 보호 및 감사 로깅 필요  
- 공개 데이터 기반 실험은 실제 대출 승인과 차이가 있을 수 있음  

---

## 10. 참고 자료

- 금융위원회: 3단계 스트레스 DSR 시행 방안 발표 (2025)  
- BIS/BCBS: Korea RCAP – Large Exposures (2024)  
- 관련 미디어 보도: 스트레스 DSR 시행 시 대출한도 감소 분석 기사 등  

---

## 11. 레포지토리 구조

```
credit‑risk‑regtech/
├ data/
│  ├ raw/
│  ├ bronze/
│  └ gold/
├ rules/
│  ├ regulation.jsonl
│  ├ issuer_policy.jsonl
│  ├ schema/
│  └ changelog.md
├ catalog/
│  └ products.csv
├ feature_store/
├ training/
├ serving/
├ monitoring/
├ rag_agent/
└ README.md
```

---

## 12. 일정 (스프린트)

| 단계 | 기간 | Deliverable |
|---|---|---|
| Sprint 1 | 2주 | 규제 문서 크롤러 + RAG 인덱스 + 규제 룰 JSON 스키마 |
| Sprint 2 | 2주 | 카드사 정책 데이터 확보 + 신용점수 밴드 매핑 + PD 모델 개발 |
| Sprint 3 | 2주 | 한도 엔진 API + 규제/정책/모형 통합 |
| Sprint 4 | 2주 | 모니터링 대시보드 + 설명가능성 리포트 + 데모 |

---

## 13. 결론

- 규제 자동 반영 + 카드사 정책 통합 → 실무적 가치  
- 개인/법인/소상공인 세그먼트별 한도 산출 → 고객 다양성 반영  
- MLOps + RegTech 통합 → 금융권 채용 우대 기술 충족  
- 설명가능성, 공정성, 감사대응 → 감독기관 보고에 활용 가능
