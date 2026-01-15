"""
REST API 라우터
웹 UI와 외부 연동을 위한 REST API
"""
from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1", tags=["API"])

from . import dashboard, orders, products, settings, claims
