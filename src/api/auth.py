"""
인증 관리 API
API 키 생성, 관리
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..security import AuthManager

router = APIRouter(prefix="/auth", tags=["Authentication"])


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = None


class EnableAuthRequest(BaseModel):
    enabled: bool


@router.get("/status")
async def get_auth_status():
    """인증 상태 조회"""
    return {
        "enabled": AuthManager.is_enabled(),
        "api_keys_count": len(AuthManager.list_api_keys())
    }


@router.post("/enable")
async def enable_auth(request: EnableAuthRequest):
    """인증 활성화/비활성화"""
    AuthManager.enable_auth(request.enabled)
    return {
        "success": True,
        "enabled": request.enabled,
        "message": f"인증이 {'활성화' if request.enabled else '비활성화'}되었습니다"
    }


@router.post("/api-keys")
async def create_api_key(request: CreateApiKeyRequest):
    """API 키 생성"""
    result = AuthManager.create_api_key(
        name=request.name,
        expires_days=request.expires_days
    )
    return {
        "success": True,
        "api_key": result["api_key"],
        "name": result["name"],
        "expires_at": result["expires_at"],
        "warning": "⚠️ API 키는 다시 표시되지 않습니다. 안전한 곳에 저장하세요."
    }


@router.get("/api-keys")
async def list_api_keys():
    """API 키 목록"""
    keys = AuthManager.list_api_keys()
    return {"api_keys": keys}


@router.delete("/api-keys/{name}")
async def revoke_api_key(name: str):
    """API 키 폐기"""
    success = AuthManager.revoke_api_key(name)
    
    if not success:
        raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
    
    return {"success": True, "message": f"API 키 '{name}'가 폐기되었습니다"}
