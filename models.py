"""데이터 모델 정의"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class ChannelType(str, Enum):
    """판매 채널 타입"""
    NAVER = "naver"
    COUPANG = "coupang"


class CarrierType(str, Enum):
    """택배사 타입"""
    CJ = "cj"
    HANJIN = "hanjin"
    LOTTE = "lotte"
    LOGEN = "logen"
    EPOST = "epost"

    @property
    def display_name(self) -> str:
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
        return codes.get(self.value, self.value.upper())


@dataclass
class OrderItem:
    """주문 상품"""
    product_id: str
    product_name: str
    option_name: Optional[str] = None
    quantity: int = 1
    unit_price: float = 0.0
    total_price: float = 0.0


@dataclass
class Order:
    """주문 정보"""
    channel: ChannelType
    order_id: str
    buyer_name: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_zipcode: Optional[str] = None
    total_amount: float = 0.0
    shipping_fee: float = 0.0
    buyer_memo: Optional[str] = None
    ordered_at: Optional[datetime] = None
    items: List[OrderItem] = field(default_factory=list)

    # 송장 정보 (처리 후 채워짐)
    tracking_number: Optional[str] = None
    carrier: Optional[CarrierType] = None
    shipped_at: Optional[datetime] = None
    status: str = "new"


@dataclass
class ShippingRequest:
    """송장 발급 요청"""
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
    weight: float = 1.0

    # 옵션
    box_type: str = "box"
    memo: Optional[str] = None

    # 주문 참조
    order_id: Optional[str] = None
    channel_order_id: Optional[str] = None


@dataclass
class ShippingResponse:
    """송장 발급 응답"""
    success: bool
    tracking_number: Optional[str] = None
    label_url: Optional[str] = None
    label_data: Optional[bytes] = None
    error: Optional[str] = None
    carrier: str = ""
    carrier_name: str = ""
    requested_at: datetime = field(default_factory=datetime.now)


@dataclass
class ProcessingRecord:
    """처리 기록 (엑셀 저장용)"""
    processed_at: datetime
    channel: str
    order_id: str
    buyer_name: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_zipcode: str
    product_name: str
    quantity: int
    total_amount: float
    carrier: str
    tracking_number: str
    status: str
    note: Optional[str] = None
