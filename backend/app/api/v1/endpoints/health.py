"""
Health endpoint
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.models.database import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    async with get_db() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}

