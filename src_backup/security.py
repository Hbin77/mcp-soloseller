"""
보안 및 인증 모듈
API 키 인증, 세션 관리
"""
from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import APIKeyHeader, APIKeyQuery
from typing import Optional
import secrets
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

# API 키 헤더
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)

# 설정 파일
AUTH_FILE = Path("data/auth.json")


def load_auth_config() -> dict:
    """인증 설정 로드"""
    if AUTH_FILE.exists():
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    return {"api_keys": [], "enabled": False}


def save_auth_config(config: dict):
    """인증 설정 저장"""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump(config, f, indent=2)


def generate_api_key() -> str:
    """API 키 생성"""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """API 키 해시"""
    return hashlib.sha256(api_key.encode()).hexdigest()


class AuthManager:
    """인증 관리자"""
    
    @staticmethod
    def is_enabled() -> bool:
        """인증 활성화 여부"""
        config = load_auth_config()
        return config.get("enabled", False)
    
    @staticmethod
    def create_api_key(name: str, expires_days: Optional[int] = None) -> dict:
        """API 키 생성"""
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        
        config = load_auth_config()
        
        key_data = {
            "name": name,
            "hash": key_hash,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=expires_days)).isoformat() if expires_days else None,
            "last_used": None
        }
        
        config["api_keys"].append(key_data)
        save_auth_config(config)
        
        logger.info("API 키 생성됨", name=name)
        
        return {
            "api_key": api_key,  # 최초 1회만 표시
            "name": name,
            "expires_at": key_data["expires_at"]
        }
    
    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """API 키 검증"""
        if not api_key:
            return False
        
        config = load_auth_config()
        key_hash = hash_api_key(api_key)
        
        for key_data in config["api_keys"]:
            if key_data["hash"] == key_hash:
                # 만료 확인
                if key_data.get("expires_at"):
                    expires = datetime.fromisoformat(key_data["expires_at"])
                    if datetime.now() > expires:
                        logger.warning("만료된 API 키 사용 시도", name=key_data["name"])
                        return False
                
                # 마지막 사용 시간 업데이트
                key_data["last_used"] = datetime.now().isoformat()
                save_auth_config(config)
                
                return True
        
        return False
    
    @staticmethod
    def list_api_keys() -> list:
        """API 키 목록"""
        config = load_auth_config()
        return [
            {
                "name": k["name"],
                "created_at": k["created_at"],
                "expires_at": k.get("expires_at"),
                "last_used": k.get("last_used")
            }
            for k in config["api_keys"]
        ]
    
    @staticmethod
    def revoke_api_key(name: str) -> bool:
        """API 키 폐기"""
        config = load_auth_config()
        
        for i, key_data in enumerate(config["api_keys"]):
            if key_data["name"] == name:
                del config["api_keys"][i]
                save_auth_config(config)
                logger.info("API 키 폐기됨", name=name)
                return True
        
        return False
    
    @staticmethod
    def enable_auth(enabled: bool = True):
        """인증 활성화/비활성화"""
        config = load_auth_config()
        config["enabled"] = enabled
        save_auth_config(config)
        logger.info("인증 상태 변경", enabled=enabled)


async def get_api_key(
    api_key_header: str = Security(API_KEY_HEADER),
    api_key_query: str = Security(API_KEY_QUERY)
) -> Optional[str]:
    """API 키 추출"""
    return api_key_header or api_key_query


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Depends(get_api_key)
):
    """API 키 검증 의존성"""
    # 인증이 비활성화된 경우 통과
    if not AuthManager.is_enabled():
        return True
    
    # 로컬 요청은 통과 (개발용)
    client_host = request.client.host if request.client else ""
    if client_host in ["127.0.0.1", "localhost", "::1"]:
        return True
    
    # 정적 파일 및 문서 경로 제외
    exempt_paths = ["/", "/docs", "/redoc", "/openapi.json", "/static", "/health"]
    if any(request.url.path.startswith(p) for p in exempt_paths):
        return True
    
    # API 키 검증
    if not api_key or not AuthManager.validate_api_key(api_key):
        logger.warning("인증 실패", path=request.url.path, client=client_host)
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return True


class RateLimiter:
    """레이트 리미터"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: dict = {}  # {client_ip: [(timestamp, count)]}
    
    def is_allowed(self, client_ip: str) -> bool:
        """요청 허용 여부"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # 오래된 기록 정리
        if client_ip in self.requests:
            self.requests[client_ip] = [
                (ts, count) for ts, count in self.requests[client_ip]
                if ts > minute_ago
            ]
        
        # 요청 수 계산
        request_count = sum(
            count for ts, count in self.requests.get(client_ip, [])
        )
        
        if request_count >= self.requests_per_minute:
            return False
        
        # 요청 기록
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        self.requests[client_ip].append((now, 1))
        
        return True


# 전역 레이트 리미터
rate_limiter = RateLimiter(requests_per_minute=120)


async def check_rate_limit(request: Request):
    """레이트 리미트 검사"""
    client_ip = request.client.host if request.client else "unknown"
    
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )
    
    return True
