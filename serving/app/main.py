from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
from ..limit_engine import compute_offers

app = FastAPI(title="Credit Risk RegTech API", version="0.1.0")


class Profile(BaseModel):
    score_band: Literal["A", "B", "C", "D"]
    pd: float = Field(ge=0, le=1)
    income_yearly: int = Field(ge=0)
    existing_debt_payment_monthly: int = Field(ge=0)
    region: Literal["capital", "noncapital"]
    loan_type: Literal["credit", "mortgage"]
    rate_type: Literal["variable", "fixed"]


class Candidate(BaseModel):
    issuer: str
    product: str


class OfferRequest(BaseModel):
    as_of: str
    segment: Literal["personal", "corporate", "sme"]
    profile: Profile
    candidates: List[Candidate]


@app.post("/api/offer_limits")
def offer_limits(req: OfferRequest) -> Dict[str, Any]:
    # 세그먼트별 추가 룰/확장 로직은 이후 여기에 분기 처리
    return compute_offers(
        as_of=req.as_of,
        profile=req.profile.model_dump(),
        candidates=[c.model_dump() for c in req.candidates],
    )


@app.get("/health")
def health():
    return {"status": "ok"}
