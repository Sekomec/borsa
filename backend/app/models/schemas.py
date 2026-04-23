"""
QuantEdge AI — Pydantic Schemas
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Timeframe = Literal["1d", "1w", "1mo", "3mo", "1y"]


class PredictionRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    timeframe: Timeframe = "1d"

    include_technical: bool = True
    include_sentiment: bool = True
    include_fundamental: bool = True
    include_macro: bool = True

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class PredictionResponse(BaseModel):
    ticker: str
    timeframe: Timeframe
    current_price: float
    predicted_price: float
    direction: Literal["up", "down", "sideways"]
    direction_confidence: float

    predicted_return_pct: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

    technical_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    macro_score: Optional[float] = None

    risk_level: Optional[str] = None
    volatility_estimate: Optional[float] = None
    anomaly_detected: Optional[bool] = None
    anomaly_description: Optional[str] = None

    model_version: Optional[str] = None
    ensemble_weights: Optional[dict] = None
    model_contributions: Optional[dict] = None
    explanation: Optional[str] = None

    disclaimer: str

