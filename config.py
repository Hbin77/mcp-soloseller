"""설정 관리 모듈"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """환경 변수 기반 설정"""

    # 발송인 정보
    sender_name: str = Field(default="")
    sender_phone: str = Field(default="")
    sender_zipcode: str = Field(default="")
    sender_address: str = Field(default="")

    # 기본 택배사
    default_carrier: str = Field(default="cj")

    # 엑셀 저장 경로
    export_dir: str = Field(default="./exports")

    # 네이버 스마트스토어 API
    naver_client_id: Optional[str] = None
    naver_client_secret: Optional[str] = None
    naver_seller_id: Optional[str] = None

    # 쿠팡 WING API
    coupang_vendor_id: Optional[str] = None
    coupang_access_key: Optional[str] = None
    coupang_secret_key: Optional[str] = None

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def is_naver_configured(self) -> bool:
        """네이버 API 설정 여부"""
        return all([
            self.naver_client_id,
            self.naver_client_secret,
            self.naver_seller_id
        ])

    def is_coupang_configured(self) -> bool:
        """쿠팡 API 설정 여부"""
        return all([
            self.coupang_vendor_id,
            self.coupang_access_key,
            self.coupang_secret_key
        ])

    def is_carrier_configured(self, carrier: str) -> bool:
        """택배사 API 설정 여부"""
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


# 싱글톤 인스턴스
settings = Settings()
