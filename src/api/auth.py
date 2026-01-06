"""
인증 관리 API
JWT 인증, 회원가입, 로그인, API 키 관리
이메일 인증, reCAPTCHA
"""
import random
import string
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timedelta

from ..security import AuthManager
from ..jwt_auth import (
    authenticate_user,
    create_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_current_active_user,
    CurrentUser,
    get_db
)
from ..database import User, EmailVerification
from ..config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================
# Helper Functions
# ============================================

async def verify_recaptcha(token: str) -> bool:
    """Google reCAPTCHA 검증"""
    settings = get_settings()
    if not settings.recaptcha_secret_key:
        return True  # reCAPTCHA 미설정 시 통과

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={
                    "secret": settings.recaptcha_secret_key,
                    "response": token
                }
            )
            result = response.json()
            return result.get("success", False)
    except Exception:
        return False


async def send_verification_email(email: str, code: str) -> bool:
    """인증 이메일 발송"""
    settings = get_settings()
    if not settings.smtp_configured:
        # SMTP 미설정 시 콘솔에 출력 (개발용)
        print(f"[DEV] Verification code for {email}: {code}")
        return True

    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg["From"] = settings.smtp_user
        msg["To"] = email
        msg["Subject"] = "[쇼핑몰 자동화 MCP] 이메일 인증 코드"

        body = f"""
안녕하세요!

쇼핑몰 자동화 MCP 회원가입을 위한 인증 코드입니다.

인증 코드: {code}

이 코드는 10분간 유효합니다.

본인이 요청하지 않은 경우 이 이메일을 무시해주세요.

감사합니다.
쇼핑몰 자동화 MCP 팀
"""
        msg.attach(MIMEText(body, "plain", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True
        )
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        return False


def generate_verification_code() -> str:
    """6자리 인증 코드 생성"""
    return "".join(random.choices(string.digits, k=6))


# ============================================
# Request/Response Models
# ============================================

class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = None


class EnableAuthRequest(BaseModel):
    enabled: bool


class SendVerificationRequest(BaseModel):
    """인증코드 전송 요청"""
    email: EmailStr
    recaptcha_token: Optional[str] = None


class SignupRequest(BaseModel):
    """회원가입 요청"""
    email: EmailStr
    password: str = Field(min_length=6, description="최소 6자 이상")
    name: str = Field(min_length=1, max_length=100)
    verification_code: str = Field(min_length=6, max_length=6)


class LoginRequest(BaseModel):
    """로그인 요청"""
    email: EmailStr
    password: str
    recaptcha_token: Optional[str] = None


class TokenResponse(BaseModel):
    """토큰 응답"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """토큰 갱신 요청"""
    refresh_token: str


class UserResponse(BaseModel):
    """사용자 정보 응답"""
    id: int
    email: str
    name: str
    is_active: bool
    is_admin: bool


class McpApiKeyResponse(BaseModel):
    """MCP API 키 응답"""
    api_key: Optional[str] = None
    created_at: Optional[str] = None
    has_key: bool = False


# ============================================
# reCAPTCHA & 이메일 인증
# ============================================

@router.get("/recaptcha-config")
async def get_recaptcha_config():
    """reCAPTCHA 설정 조회 (site key만 반환)"""
    settings = get_settings()
    return {
        "site_key": settings.recaptcha_site_key or "",
        "enabled": settings.recaptcha_configured
    }


@router.post("/send-verification")
async def send_verification(request: SendVerificationRequest):
    """이메일 인증코드 전송"""
    settings = get_settings()

    # reCAPTCHA 검증
    if settings.recaptcha_configured:
        if not request.recaptcha_token:
            raise HTTPException(status_code=400, detail="reCAPTCHA 인증이 필요합니다")
        if not await verify_recaptcha(request.recaptcha_token):
            raise HTTPException(status_code=400, detail="reCAPTCHA 인증에 실패했습니다")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    from sqlalchemy import select, delete

    async with db.async_session() as session:
        # 이미 가입된 이메일인지 확인
        result = await session.execute(
            select(User).where(User.email == request.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")

        # 기존 인증 코드 삭제
        await session.execute(
            delete(EmailVerification).where(EmailVerification.email == request.email)
        )

        # 새 인증 코드 생성
        code = generate_verification_code()
        verification = EmailVerification(
            email=request.email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        session.add(verification)
        await session.commit()

        # 이메일 발송
        if not await send_verification_email(request.email, code):
            raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다")

        return {"success": True, "message": "인증코드가 이메일로 전송되었습니다"}


# ============================================
# API 키 관리 (기존)
# ============================================

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
        "warning": "API 키는 다시 표시되지 않습니다. 안전한 곳에 저장하세요."
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


# ============================================
# JWT 사용자 인증
# ============================================

@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    """회원가입 (이메일 인증 필요)"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    from sqlalchemy import select

    async with db.async_session() as session:
        # 인증 코드 확인
        result = await session.execute(
            select(EmailVerification).where(
                EmailVerification.email == request.email,
                EmailVerification.code == request.verification_code,
                EmailVerification.used == False,
                EmailVerification.expires_at > datetime.utcnow()
            )
        )
        verification = result.scalar_one_or_none()

        if not verification:
            raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 인증 코드입니다")

        # 인증 코드 사용 처리
        verification.used = True

        try:
            user = await create_user(
                session=session,
                email=request.email,
                password=request.password,
                name=request.name
            )

            # 토큰 생성
            access_token = create_access_token(data={"sub": user.id})
            refresh_token = create_refresh_token(data={"sub": user.id})

            settings = get_settings()

            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=settings.jwt_access_token_expire_minutes * 60
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """로그인"""
    settings = get_settings()

    # reCAPTCHA 검증
    if settings.recaptcha_configured:
        if not request.recaptcha_token:
            raise HTTPException(status_code=400, detail="reCAPTCHA 인증이 필요합니다")
        if not await verify_recaptcha(request.recaptcha_token):
            raise HTTPException(status_code=400, detail="reCAPTCHA 인증에 실패했습니다")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    async with db.async_session() as session:
        user = await authenticate_user(
            session=session,
            email=request.email,
            password=request.password
        )

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="이메일 또는 비밀번호가 올바르지 않습니다"
            )

        # 마지막 로그인 시간 업데이트
        user.last_login_at = datetime.utcnow()
        await session.commit()

        # 토큰 생성
        access_token = create_access_token(data={"sub": user.id})
        refresh_token = create_refresh_token(data={"sub": user.id})

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    """토큰 갱신"""
    payload = decode_token(request.refresh_token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # 새 토큰 생성
    access_token = create_access_token(data={"sub": user_id})
    refresh_token_new = create_refresh_token(data={"sub": user_id})

    settings = get_settings()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_new,
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_active_user)):
    """현재 로그인된 사용자 정보"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin
    )


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_active_user)):
    """로그아웃 (클라이언트에서 토큰 삭제)"""
    return {"success": True, "message": "로그아웃되었습니다"}


# ============================================
# MCP API 키 관리
# ============================================

@router.get("/mcp-api-key", response_model=McpApiKeyResponse)
async def get_mcp_api_key(current_user: CurrentUser = Depends(get_current_active_user)):
    """MCP API 키 조회 (마스킹된 키 반환)"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    from sqlalchemy import select
    from ..database import UserSettings

    async with db.async_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == current_user.id)
        )
        settings = result.scalar_one_or_none()

        if settings and settings.mcp_api_key:
            # 키의 앞 8자리만 표시, 나머지는 마스킹
            masked_key = settings.mcp_api_key[:8] + "*" * 24
            return McpApiKeyResponse(
                api_key=masked_key,
                created_at=settings.mcp_api_key_created_at.isoformat() if settings.mcp_api_key_created_at else None,
                has_key=True
            )

        return McpApiKeyResponse(has_key=False)


@router.post("/mcp-api-key", response_model=McpApiKeyResponse)
async def create_mcp_api_key(current_user: CurrentUser = Depends(get_current_active_user)):
    """MCP API 키 발급 (기존 키가 있으면 재발급)"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    import secrets
    from sqlalchemy import select
    from ..database import UserSettings

    async with db.async_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == current_user.id)
        )
        settings = result.scalar_one_or_none()

        if not settings:
            # 설정이 없으면 생성
            settings = UserSettings(user_id=current_user.id)
            session.add(settings)

        # 새 API 키 생성 (32바이트 = 64자 hex)
        new_api_key = secrets.token_hex(32)
        settings.mcp_api_key = new_api_key
        settings.mcp_api_key_created_at = datetime.utcnow()

        await session.commit()

        return McpApiKeyResponse(
            api_key=new_api_key,  # 발급 시에만 전체 키 반환
            created_at=settings.mcp_api_key_created_at.isoformat(),
            has_key=True
        )


@router.delete("/mcp-api-key")
async def delete_mcp_api_key(current_user: CurrentUser = Depends(get_current_active_user)):
    """MCP API 키 삭제"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    from sqlalchemy import select
    from ..database import UserSettings

    async with db.async_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == current_user.id)
        )
        settings = result.scalar_one_or_none()

        if settings and settings.mcp_api_key:
            settings.mcp_api_key = None
            settings.mcp_api_key_created_at = None
            await session.commit()
            return {"success": True, "message": "MCP API 키가 삭제되었습니다"}

        return {"success": False, "message": "삭제할 API 키가 없습니다"}
