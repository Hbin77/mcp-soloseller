"""
설정 관리 모듈
환경 변수에서 설정값을 로드합니다.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 서버 설정
    mcp_host: str = Field(default="0.0.0.0")
    mcp_port: int = Field(default=8080)
    debug: bool = Field(default=False)
    
    # 데이터베이스
    database_url: str = Field(default="sqlite+aiosqlite:///./data/shop.db")
    
    # 네이버 스마트스토어
    naver_client_id: Optional[str] = None
    naver_client_secret: Optional[str] = None
    naver_seller_id: Optional[str] = None
    
    # 쿠팡
    coupang_vendor_id: Optional[str] = None
    coupang_access_key: Optional[str] = None
    coupang_secret_key: Optional[str] = None
    
    # 발송인 정보 (전역 설정)
    sender_name: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_zipcode: Optional[str] = None
    sender_address: Optional[str] = None

    # 기본 택배사
    default_carrier: str = Field(default="cj")

    # CJ대한통운
    cj_customer_id: Optional[str] = None
    cj_api_key: Optional[str] = None
    cj_contract_code: Optional[str] = None

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

    # 배송 추적
    delivery_tracker_api_key: Optional[str] = None
    
    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    # Slack
    slack_webhook_url: Optional[str] = None
    
    # Email
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: Optional[str] = None
    
    # 스케줄
    schedule_first_batch: str = Field(default="12:00")
    schedule_second_batch: str = Field(default="15:30")
    tracking_interval_minutes: int = Field(default=30)
    
    # 재고
    stock_alert_threshold: int = Field(default=5)
    
    # 기타
    timezone: str = Field(default="Asia/Seoul")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @property
    def naver_configured(self) -> bool:
        """네이버 API 설정 여부"""
        return all([self.naver_client_id, self.naver_client_secret, self.naver_seller_id])
    
    @property
    def coupang_configured(self) -> bool:
        """쿠팡 API 설정 여부"""
        return all([self.coupang_vendor_id, self.coupang_access_key, self.coupang_secret_key])
    
    @property
    def telegram_configured(self) -> bool:
        """텔레그램 설정 여부"""
        return all([self.telegram_bot_token, self.telegram_chat_id])

    @property
    def sender_configured(self) -> bool:
        """발송인 정보 설정 여부"""
        return all([self.sender_name, self.sender_phone, self.sender_address])

    @property
    def cj_configured(self) -> bool:
        """CJ대한통운 설정 여부"""
        return all([self.cj_customer_id, self.cj_api_key])

    @property
    def hanjin_configured(self) -> bool:
        """한진택배 설정 여부"""
        return all([self.hanjin_customer_id, self.hanjin_api_key])

    @property
    def lotte_configured(self) -> bool:
        """롯데택배 설정 여부"""
        return all([self.lotte_customer_id, self.lotte_api_key])

    @property
    def logen_configured(self) -> bool:
        """로젠택배 설정 여부"""
        return all([self.logen_customer_id, self.logen_api_key])

    @property
    def epost_configured(self) -> bool:
        """우체국택배 설정 여부"""
        return all([self.epost_customer_id, self.epost_api_key])


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    return Settings()
