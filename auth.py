"""다중 사용자 인증 모듈 - MVP (쿠팡 + CJ대한통운)"""
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote


@dataclass
class UserCredentials:
    """사용자별 인증 정보"""

    # 쿠팡 WING
    coupang_vendor_id: Optional[str] = None
    coupang_access_key: Optional[str] = None
    coupang_secret_key: Optional[str] = None

    # CJ대한통운
    cj_customer_id: Optional[str] = None
    cj_biz_reg_num: Optional[str] = None

    # 발송인 정보
    sender_name: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_zipcode: Optional[str] = None
    sender_address: Optional[str] = None

    @property
    def coupang_configured(self) -> bool:
        return all([self.coupang_vendor_id, self.coupang_access_key, self.coupang_secret_key])

    @property
    def cj_configured(self) -> bool:
        return bool(self.cj_customer_id and self.cj_biz_reg_num)

    @property
    def sender_configured(self) -> bool:
        return all([self.sender_name, self.sender_phone, self.sender_address])


# Context Variable - 요청별 사용자 정보 격리
_credentials: ContextVar[Optional[UserCredentials]] = ContextVar(
    "user_credentials", default=None
)


def get_credentials() -> Optional[UserCredentials]:
    return _credentials.get()


def set_credentials(credentials) -> None:
    _credentials.set(credentials)


def extract_credentials_from_headers(headers: dict) -> UserCredentials:
    """HTTP 헤더에서 사용자 인증 정보 추출"""
    def get_header(name: str) -> Optional[str]:
        value = headers.get(name) or headers.get(name.lower())
        return unquote(value) if value else None

    return UserCredentials(
        coupang_vendor_id=get_header("x-coupang-vendor-id"),
        coupang_access_key=get_header("x-coupang-access-key"),
        coupang_secret_key=get_header("x-coupang-secret-key"),
        cj_customer_id=get_header("x-cj-customer-id"),
        cj_biz_reg_num=get_header("x-cj-biz-reg-num"),
        sender_name=get_header("x-sender-name"),
        sender_phone=get_header("x-sender-phone"),
        sender_zipcode=get_header("x-sender-zipcode"),
        sender_address=get_header("x-sender-address"),
    )


AUTH_HEADERS_SPEC = {
    "description": "쿠팡 + CJ대한통운 자동화를 위한 API 키 인증",
    "headers": [
        {"name": "X-Coupang-Vendor-Id", "description": "쿠팡 WING Vendor ID"},
        {"name": "X-Coupang-Access-Key", "description": "쿠팡 WING Access Key"},
        {"name": "X-Coupang-Secret-Key", "description": "쿠팡 WING Secret Key"},
        {"name": "X-Cj-Customer-Id", "description": "CJ대한통운 고객 ID"},
        {"name": "X-Cj-Biz-Reg-Num", "description": "CJ대한통운 사업자등록번호"},
        {"name": "X-Sender-Name", "description": "발송인 이름"},
        {"name": "X-Sender-Phone", "description": "발송인 연락처"},
        {"name": "X-Sender-Zipcode", "description": "발송인 우편번호"},
        {"name": "X-Sender-Address", "description": "발송인 주소"},
        {"name": "Authorization", "description": "Bearer 토큰 (웹에서 발급)"},
    ]
}


def credentials_from_db_row(row: dict) -> UserCredentials:
    """데이터베이스 row를 UserCredentials로 변환"""
    return UserCredentials(
        coupang_vendor_id=row.get("coupang_vendor_id"),
        coupang_access_key=row.get("coupang_access_key"),
        coupang_secret_key=row.get("coupang_secret_key"),
        cj_customer_id=row.get("cj_customer_id"),
        cj_biz_reg_num=row.get("cj_biz_reg_num"),
        sender_name=row.get("sender_name"),
        sender_phone=row.get("sender_phone"),
        sender_zipcode=row.get("sender_zipcode"),
        sender_address=row.get("sender_address"),
    )


def extract_credentials_from_token(headers: dict) -> Optional[UserCredentials]:
    """Authorization 헤더의 Bearer 토큰으로 credentials 조회"""
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]

    try:
        from database import get_credentials_by_token
        cred_row = get_credentials_by_token(token)
        if cred_row:
            return credentials_from_db_row(cred_row)
    except Exception:
        pass

    return None


def extract_credentials_auto(headers: dict) -> UserCredentials:
    """토큰 또는 헤더에서 credentials 추출 (토큰 우선)"""
    token_creds = extract_credentials_from_token(headers)
    if token_creds:
        return token_creds
    return extract_credentials_from_headers(headers)
