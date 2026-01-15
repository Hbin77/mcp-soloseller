"""
PlayMCP 인증 모듈
HTTP 헤더에서 사용자별 API 키를 추출하여 관리합니다.
"""
from dataclasses import dataclass
from typing import Optional
from contextvars import ContextVar
from fastapi import Request
import structlog

logger = structlog.get_logger()

# Context variable for storing user credentials per request
_user_credentials: ContextVar[Optional["UserCredentials"]] = ContextVar(
    "user_credentials", default=None
)


@dataclass
class UserCredentials:
    """사용자별 인증 정보"""
    # 네이버 스마트스토어
    naver_client_id: Optional[str] = None
    naver_client_secret: Optional[str] = None
    naver_seller_id: Optional[str] = None

    # 쿠팡
    coupang_vendor_id: Optional[str] = None
    coupang_access_key: Optional[str] = None
    coupang_secret_key: Optional[str] = None

    @property
    def naver_configured(self) -> bool:
        """네이버 API 설정 여부"""
        return all([self.naver_client_id, self.naver_client_secret, self.naver_seller_id])

    @property
    def coupang_configured(self) -> bool:
        """쿠팡 API 설정 여부"""
        return all([self.coupang_vendor_id, self.coupang_access_key, self.coupang_secret_key])

    def has_any_credentials(self) -> bool:
        """하나라도 인증 정보가 있는지 확인"""
        return self.naver_configured or self.coupang_configured


def get_user_credentials() -> Optional[UserCredentials]:
    """현재 요청의 사용자 인증 정보 반환"""
    return _user_credentials.get()


def set_user_credentials(credentials: UserCredentials) -> None:
    """현재 요청의 사용자 인증 정보 설정"""
    _user_credentials.set(credentials)


def extract_credentials_from_request(request: Request) -> UserCredentials:
    """
    HTTP 헤더에서 사용자 인증 정보 추출

    PlayMCP에서 전달하는 헤더:
    - X-Naver-Client-Id
    - X-Naver-Client-Secret
    - X-Naver-Seller-Id
    - X-Coupang-Vendor-Id
    - X-Coupang-Access-Key
    - X-Coupang-Secret-Key
    """
    credentials = UserCredentials(
        # 네이버
        naver_client_id=request.headers.get("X-Naver-Client-Id"),
        naver_client_secret=request.headers.get("X-Naver-Client-Secret"),
        naver_seller_id=request.headers.get("X-Naver-Seller-Id"),
        # 쿠팡
        coupang_vendor_id=request.headers.get("X-Coupang-Vendor-Id"),
        coupang_access_key=request.headers.get("X-Coupang-Access-Key"),
        coupang_secret_key=request.headers.get("X-Coupang-Secret-Key"),
    )

    if credentials.has_any_credentials():
        logger.info(
            "사용자 인증 정보 추출 완료",
            naver_configured=credentials.naver_configured,
            coupang_configured=credentials.coupang_configured
        )

    return credentials


# PlayMCP 등록 시 필요한 헤더 정의 (메타데이터용)
PLAYMCP_AUTH_HEADERS = {
    "description": "쇼핑몰 자동화를 위한 API 키 인증",
    "headers": [
        {
            "name": "X-Naver-Client-Id",
            "description": "네이버 커머스 API Client ID",
            "required": False
        },
        {
            "name": "X-Naver-Client-Secret",
            "description": "네이버 커머스 API Client Secret",
            "required": False
        },
        {
            "name": "X-Naver-Seller-Id",
            "description": "네이버 스마트스토어 판매자 ID",
            "required": False
        },
        {
            "name": "X-Coupang-Vendor-Id",
            "description": "쿠팡 WING Vendor ID",
            "required": False
        },
        {
            "name": "X-Coupang-Access-Key",
            "description": "쿠팡 WING Access Key",
            "required": False
        },
        {
            "name": "X-Coupang-Secret-Key",
            "description": "쿠팡 WING Secret Key",
            "required": False
        }
    ]
}
