"""채널 API 모듈"""
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class ChannelOrderItem:
    """채널 주문 상품"""
    product_id: str
    product_name: str
    option_name: Optional[str] = None
    quantity: int = 1
    unit_price: float = 0.0
    total_price: float = 0.0


@dataclass
class ChannelOrder:
    """채널 주문 데이터"""
    channel: str
    order_id: str
    status: str
    buyer_name: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_zipcode: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_email: Optional[str] = None
    total_amount: float = 0.0
    shipping_fee: float = 0.0
    buyer_memo: Optional[str] = None
    ordered_at: Optional[datetime] = None
    items: Optional[List[ChannelOrderItem]] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "channel": self.channel,
            "order_id": self.order_id,
            "status": self.status,
            "buyer_name": self.buyer_name,
            "receiver_name": self.receiver_name,
            "receiver_phone": self.receiver_phone,
            "receiver_address": self.receiver_address,
            "receiver_zipcode": self.receiver_zipcode,
            "total_amount": self.total_amount,
            "shipping_fee": self.shipping_fee,
            "buyer_memo": self.buyer_memo,
            "ordered_at": self.ordered_at.isoformat() if self.ordered_at else None,
            "items": [
                {
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "option_name": item.option_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price
                }
                for item in self.items
            ]
        }
