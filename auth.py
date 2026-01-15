"""다중 사용자 인증 모듈"""
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote


@dataclass
class UserCredentials:
    """사용자별 인증 정보 (HTTP 헤더로 전달)"""

    # 네이버 스마트스토어
    naver_client_id: Optional[str] = None
    naver_client_secret: Optional[str] = None
    naver_seller_id: Optional[str] = None

    # 쿠팡 WING
    coupang_vendor_id: Optional[str] = None
    coupang_access_key: Optional[str] = None
    coupang_secret_key: Optional[str] = None

    # CJ대한통운
    cj_customer_id: Optional[str] = None
    cj_api_key: Optional[str] = None

    # 한진택배
    hanjin_customer_id: Optional[str] = None
    hanjin_api_key: Optional[str] = None

    # 롯데택배
    lotte_customer_id: Optional[str] = None
    lotte_api_key: Optional[str] = None

    # 로젠택배
    logen_customer_id: Optional[str] = None
    logen_api_key: Optional[str] = None

    # 우체국택배
    epost_customer_id: Optional[str] = None
    epost_api_key: Optional[str] = None

    # 발송인 정보
    sender_name: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_zipcode: Optional[str] = None
    sender_address: Optional[str] = None

    # 기본 택배사
    default_carrier: str = "cj"

    @property
    def naver_configured(self) -> bool:
        return all([self.naver_client_id, self.naver_client_secret, self.naver_seller_id])

    @property
    def coupang_configured(self) -> bool:
        return all([self.coupang_vendor_id, self.coupang_access_key, self.coupang_secret_key])

    @property
    def sender_configured(self) -> bool:
        return all([self.sender_name, self.sender_phone, self.sender_address])

    def is_carrier_configured(self, carrier: str) -> bool:
        carrier = carrier.lower()
        if carrier == "cj":
            return bool(self.cj_customer_id and self.cj_api_key)
        elif carrier == "hanjin":
            return bool(self.hanjin_customer_id and self.hanjin_api_key)
        elif carrier == "lotte":
            return bool(self.lotte_customer_id and self.lotte_api_key)
        elif carrier == "logen":
            return bool(self.logen_customer_id and self.logen_api_key)
        elif carrier == "epost":
            return bool(self.epost_customer_id and self.epost_api_key)
        return False


# Context Variable - 요청별 사용자 정보 격리
_credentials: ContextVar[Optional[UserCredentials]] = ContextVar(
    "user_credentials", default=None
)


def get_credentials() -> Optional[UserCredentials]:
    """현재 요청의 사용자 인증 정보 반환"""
    return _credentials.get()


def set_credentials(credentials: UserCredentials) -> None:
    """현재 요청의 사용자 인증 정보 설정"""
    _credentials.set(credentials)


def extract_credentials_from_headers(headers: dict) -> UserCredentials:
    """HTTP 헤더에서 사용자 인증 정보 추출"""
    def get_header(name: str) -> Optional[str]:
        value = headers.get(name) or headers.get(name.lower())
        if value:
            return unquote(value)
        return None

    return UserCredentials(
        # 네이버
        naver_client_id=get_header("x-naver-client-id"),
        naver_client_secret=get_header("x-naver-client-secret"),
        naver_seller_id=get_header("x-naver-seller-id"),
        # 쿠팡
        coupang_vendor_id=get_header("x-coupang-vendor-id"),
        coupang_access_key=get_header("x-coupang-access-key"),
        coupang_secret_key=get_header("x-coupang-secret-key"),
        # CJ대한통운
        cj_customer_id=get_header("x-cj-customer-id"),
        cj_api_key=get_header("x-cj-api-key"),
        # 한진택배
        hanjin_customer_id=get_header("x-hanjin-customer-id"),
        hanjin_api_key=get_header("x-hanjin-api-key"),
        # 롯데택배
        lotte_customer_id=get_header("x-lotte-customer-id"),
        lotte_api_key=get_header("x-lotte-api-key"),
        # 로젠택배
        logen_customer_id=get_header("x-logen-customer-id"),
        logen_api_key=get_header("x-logen-api-key"),
        # 우체국택배
        epost_customer_id=get_header("x-epost-customer-id"),
        epost_api_key=get_header("x-epost-api-key"),
        # 발송인 정보
        sender_name=get_header("x-sender-name"),
        sender_phone=get_header("x-sender-phone"),
        sender_zipcode=get_header("x-sender-zipcode"),
        sender_address=get_header("x-sender-address"),
        # 기본 택배사
        default_carrier=get_header("x-default-carrier") or "cj"
    )


# HTTP 헤더 스펙 (문서화용)
AUTH_HEADERS_SPEC = {
    "description": "쇼핑몰 자동화를 위한 API 키 인증",
    "headers": [
        # 네이버
        {"name": "X-Naver-Client-Id", "description": "네이버 커머스 API Client ID"},
        {"name": "X-Naver-Client-Secret", "description": "네이버 커머스 API Client Secret"},
        {"name": "X-Naver-Seller-Id", "description": "네이버 스마트스토어 판매자 ID"},
        # 쿠팡
        {"name": "X-Coupang-Vendor-Id", "description": "쿠팡 WING Vendor ID"},
        {"name": "X-Coupang-Access-Key", "description": "쿠팡 WING Access Key"},
        {"name": "X-Coupang-Secret-Key", "description": "쿠팡 WING Secret Key"},
        # 택배사
        {"name": "X-Cj-Customer-Id", "description": "CJ대한통운 고객 ID"},
        {"name": "X-Cj-Api-Key", "description": "CJ대한통운 API Key"},
        {"name": "X-Hanjin-Customer-Id", "description": "한진택배 고객 ID"},
        {"name": "X-Hanjin-Api-Key", "description": "한진택배 API Key"},
        {"name": "X-Lotte-Customer-Id", "description": "롯데택배 고객 ID"},
        {"name": "X-Lotte-Api-Key", "description": "롯데택배 API Key"},
        {"name": "X-Logen-Customer-Id", "description": "로젠택배 고객 ID"},
        {"name": "X-Logen-Api-Key", "description": "로젠택배 API Key"},
        {"name": "X-Epost-Customer-Id", "description": "우체국택배 고객 ID"},
        {"name": "X-Epost-Api-Key", "description": "우체국택배 API Key"},
        # 발송인 정보
        {"name": "X-Sender-Name", "description": "발송인 이름"},
        {"name": "X-Sender-Phone", "description": "발송인 연락처"},
        {"name": "X-Sender-Zipcode", "description": "발송인 우편번호"},
        {"name": "X-Sender-Address", "description": "발송인 주소"},
        # 기본 설정
        {"name": "X-Default-Carrier", "description": "기본 택배사 (cj, hanjin, lotte, logen, epost)"},
    ]
}
