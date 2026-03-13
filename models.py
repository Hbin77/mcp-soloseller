"""데이터 모델 정의 - MVP (쿠팡 + CJ대한통운)"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


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
    memo: Optional[str] = None

    # 주문 참조
    order_id: Optional[str] = None


@dataclass
class ShippingResponse:
    """송장 발급 응답"""
    success: bool
    tracking_number: Optional[str] = None
    error: Optional[str] = None
    is_test: bool = False
