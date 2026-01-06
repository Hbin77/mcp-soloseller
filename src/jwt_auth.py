"""
JWT 인증 모듈
사용자 인증 및 JWT 토큰 관리
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from .config import get_settings
from .database import User, UserSettings, Database

logger = structlog.get_logger()

# 비밀번호 해싱 (bcrypt 72바이트 제한 - truncate_error=False로 자동 처리)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False
)

# Bearer 토큰 스키마
bearer_scheme = HTTPBearer(auto_error=False)


def _truncate_password(password: str, max_bytes: int = 72) -> str:
    """bcrypt 72바이트 제한을 위해 비밀번호 truncate"""
    encoded = password.encode('utf-8')
    if len(encoded) <= max_bytes:
        return password
    # UTF-8 문자 경계를 존중하며 truncate
    truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
    return truncated


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return pwd_context.verify(_truncate_password(plain_password), hashed_password)


def get_password_hash(password: str) -> str:
    """비밀번호 해시 생성"""
    return pwd_context.hash(_truncate_password(password))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """액세스 토큰 생성"""
    settings = get_settings()
    to_encode = data.copy()

    # sub를 문자열로 변환
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """리프레시 토큰 생성"""
    settings = get_settings()
    to_encode = data.copy()

    # sub를 문자열로 변환
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """토큰 디코딩"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.warning("JWT 디코딩 실패", error=str(e))
        return None


class TokenData:
    """토큰 데이터"""
    def __init__(self, user_id: int, email: str, token_type: str = "access"):
        self.user_id = user_id
        self.email = email
        self.token_type = token_type


class CurrentUser:
    """현재 로그인된 사용자"""
    def __init__(
        self,
        id: int,
        email: str,
        name: str,
        is_active: bool,
        is_admin: bool
    ):
        self.id = id
        self.email = email
        self.name = name
        self.is_active = is_active
        self.is_admin = is_admin


# 데이터베이스 인스턴스 (main.py에서 설정)
_db: Optional[Database] = None


def set_database(db: Database):
    """데이터베이스 인스턴스 설정"""
    global _db
    _db = db


def get_db() -> Optional[Database]:
    """데이터베이스 인스턴스 반환"""
    return _db


async def get_db_session() -> AsyncSession:
    """DB 세션 반환"""
    if _db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not initialized"
        )
    async with _db.async_session() as session:
        yield session


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> CurrentUser:
    """현재 사용자 가져오기 (인증 필수)"""

    # 인증 예외 경로 (정확히 일치하거나 prefix로 시작)
    exact_exempt = ["/", "/docs", "/redoc", "/openapi.json", "/health", "/login", "/setup"]
    prefix_exempt = [
        "/static/", "/api/v1/auth/login", "/api/v1/auth/signup",
        "/api/v1/auth/refresh", "/api/v1/auth/status",
        "/api/v1/auth/send-verification", "/api/v1/auth/recaptcha-config"
    ]

    path = request.url.path
    if path in exact_exempt or any(path.startswith(p) for p in prefix_exempt):
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise credentials_exception

    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise credentials_exception

    user_id_str = payload.get("sub")
    token_type: str = payload.get("type")

    if user_id_str is None or token_type != "access":
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    # 데이터베이스에서 사용자 조회
    if _db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not initialized"
        )

    async with _db.async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise credentials_exception

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled"
            )

        return CurrentUser(
            id=user.id,
            email=user.email,
            name=user.name,
            is_active=user.is_active,
            is_admin=user.is_admin
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Optional[CurrentUser]:
    """현재 사용자 가져오기 (인증 선택)"""
    if not credentials:
        return None

    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


async def get_current_active_user(
    current_user: CurrentUser = Depends(get_current_user)
) -> CurrentUser:
    """활성 사용자만 허용"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user


async def get_current_admin_user(
    current_user: CurrentUser = Depends(get_current_user)
) -> CurrentUser:
    """관리자만 허용"""
    if current_user is None or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str
) -> Optional[User]:
    """사용자 인증"""
    result = await session.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    name: str
) -> User:
    """새 사용자 생성"""
    # 이메일 중복 확인
    result = await session.execute(
        select(User).where(User.email == email)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # 사용자 생성
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        name=name
    )
    session.add(user)
    await session.flush()

    # 기본 설정 생성
    settings = UserSettings(user_id=user.id)
    session.add(settings)

    await session.commit()
    await session.refresh(user)

    logger.info("새 사용자 생성", user_id=user.id, email=email)
    return user


async def get_user_settings(
    session: AsyncSession,
    user_id: int
) -> Optional[UserSettings]:
    """사용자 설정 조회"""
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_settings_by_api_key(api_key: str) -> Optional[UserSettings]:
    """MCP API 키로 사용자 설정 조회"""
    if _db is None:
        return None

    async with _db.async_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.mcp_api_key == api_key)
        )
        return result.scalar_one_or_none()
