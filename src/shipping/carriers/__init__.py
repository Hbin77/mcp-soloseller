"""
택배사 API 클라이언트 기반 모듈
- BaseShippingCarrier: 추상 기본 클래스
- ShippingRequest/Response: 데이터 모델
- CarrierType: 택배사 열거형
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from src.auth import UserCredentials

logger = structlog.get_logger()


class CarrierType(str, Enum):
    """지원 택배사 목록"""
    CJ = "cj"
    HANJIN = "hanjin"
    LOTTE = "lotte"
    LOGEN = "logen"
    EPOST = "epost"

    @property
    def display_name(self) -> str:
        """한글 표시명"""
        names = {
            "cj": "CJ대한통운",
            "hanjin": "한진택배",
            "lotte": "롯데택배",
            "logen": "로젠택배",
            "epost": "우체국택배"
        }
        return names.get(self.value, self.value)

    @property
    def marketplace_code(self) -> str:
        """마켓플레이스 송장 등록용 코드"""
        codes = {
            "cj": "CJGLS",
            "hanjin": "HANJIN",
            "lotte": "LOTTE",
            "logen": "LOGEN",
            "epost": "EPOST"
        }
        return codes.get(self.value, "CJGLS")


@dataclass
class SenderInfo:
    """발송인 정보"""
    name: str
    phone: str
    zipcode: str
    address: str
    detail_address: str = ""

    def full_address(self) -> str:
        if self.detail_address:
            return f"{self.address} {self.detail_address}"
        return self.address


@dataclass
class ShippingRequest:
    """송장 발급 요청 데이터"""
    # 발송인 정보
    sender_name: str
    sender_phone: str
    sender_address: str
    sender_zipcode: str

    # 수령인 정보
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_zipcode: str

    # 상품 정보
    product_name: str
    quantity: int = 1
    weight: float = 1.0  # kg

    # 옵션
    box_type: str = "box"  # box, envelope, etc.
    memo: Optional[str] = None  # 배송 메모

    # 주문 참조
    order_id: Optional[str] = None
    channel_order_id: Optional[str] = None


@dataclass
class ShippingResponse:
    """송장 발급 응답 데이터"""
    success: bool
    tracking_number: Optional[str] = None
    label_url: Optional[str] = None
    label_data: Optional[bytes] = None  # PDF 바이너리
    error: Optional[str] = None
    carrier: str = ""
    carrier_name: str = ""
    requested_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "tracking_number": self.tracking_number,
            "label_url": self.label_url,
            "error": self.error,
            "carrier": self.carrier,
            "carrier_name": self.carrier_name,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None
        }


class BaseShippingCarrier(ABC):
    """택배사 API 클라이언트 추상 기본 클래스"""

    def __init__(self):
        self.logger = logger.bind(carrier=self.carrier_code)

    @property
    @abstractmethod
    def carrier_code(self) -> str:
        """택배사 코드 (cj, hanjin, lotte, logen, epost)"""
        pass

    @property
    @abstractmethod
    def carrier_name(self) -> str:
        """택배사 한글명"""
        pass

    @property
    def marketplace_code(self) -> str:
        """마켓플레이스 송장 등록용 코드"""
        return CarrierType(self.carrier_code).marketplace_code

    @abstractmethod
    async def authenticate(self) -> bool:
        """API 인증 확인

        Returns:
            bool: 인증 성공 여부
        """
        pass

    @abstractmethod
    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 요청

        Args:
            request: 송장 발급 요청 데이터

        Returns:
            ShippingResponse: 발급 결과 (송장번호 포함)
        """
        pass

    @abstractmethod
    async def get_label(self, tracking_number: str) -> Optional[bytes]:
        """송장 라벨 PDF 조회

        Args:
            tracking_number: 송장번호

        Returns:
            bytes: PDF 바이너리 데이터 또는 None
        """
        pass

    @abstractmethod
    async def request_pickup(self, tracking_numbers: List[str], pickup_date: date) -> bool:
        """집하 요청

        Args:
            tracking_numbers: 집하 요청할 송장번호 목록
            pickup_date: 집하 희망일

        Returns:
            bool: 요청 성공 여부
        """
        pass

    @abstractmethod
    async def cancel_invoice(self, tracking_number: str) -> bool:
        """송장 취소

        Args:
            tracking_number: 취소할 송장번호

        Returns:
            bool: 취소 성공 여부
        """
        pass

    async def close(self):
        """리소스 정리"""
        pass

    @classmethod
    def from_credentials(cls, credentials: "UserCredentials") -> Optional["BaseShippingCarrier"]:
        """UserCredentials에서 클라이언트 생성 (PlayMCP용)

        서브클래스에서 구현해야 함
        """
        return None


# 택배사 클라이언트 임포트 (순환 참조 방지를 위해 하단에 배치)
def get_carrier_client(carrier_type: CarrierType, **kwargs) -> Optional[BaseShippingCarrier]:
    """택배사 유형에 따른 클라이언트 인스턴스 생성

    Args:
        carrier_type: 택배사 유형
        **kwargs: 택배사별 인증 정보

    Returns:
        BaseShippingCarrier 인스턴스 또는 None
    """
    from .cj import CJLogisticsClient
    from .hanjin import HanjinClient
    from .lotte import LotteClient
    from .logen import LogenClient
    from .epost import EpostClient

    clients = {
        CarrierType.CJ: CJLogisticsClient,
        CarrierType.HANJIN: HanjinClient,
        CarrierType.LOTTE: LotteClient,
        CarrierType.LOGEN: LogenClient,
        CarrierType.EPOST: EpostClient,
    }

    client_class = clients.get(carrier_type)
    if client_class:
        try:
            return client_class(**kwargs)
        except Exception as e:
            logger.error("택배사 클라이언트 생성 실패", carrier=carrier_type.value, error=str(e))

    return None
