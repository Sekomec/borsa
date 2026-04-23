"""
Macro endpoints
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.data_fetchers.macro import macro_service

router = APIRouter()


@router.get("/snapshot")
async def macro_snapshot():
    return await macro_service.fred.get_macro_snapshot()

