"""
채널 API 기본 클래스
모든 채널 API 클라이언트의 부모 클래스
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class ChannelOrder:
    """채널 주문 데이터 표준 형식"""
    channel_order_id: str
    status: str
    buyer_name: str
    buyer_phone: Optional[str]
    buyer_email: Optional[str]
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    receiver_zipcode: Optional[str]
    total_amount: float
    shipping_fee: float
    buyer_memo: Optional[str]
    ordered_at: datetime
    items: List["ChannelOrderItem"]


@dataclass
class ChannelOrderItem:
    """채널 주문 상품 데이터"""
    channel_product_id: str
    product_name: str
    option_name: Optional[str]
    quantity: int
    unit_price: float
    total_price: float


@dataclass
class ChannelClaim:
    """채널 클레임 데이터"""
    channel_claim_id: str
    channel_order_id: str
    claim_type: str  # return, exchange, cancel
    status: str
    reason: Optional[str]
    requested_at: datetime


class BaseChannelClient(ABC):
    """채널 API 클라이언트 기본 클래스"""
    
    def __init__(self):
        self.logger = structlog.get_logger(channel=self.channel_name)
    
    @property
    @abstractmethod
    def channel_name(self) -> str:
        """채널 이름"""
        pass
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """인증 처리"""
        pass
    
    @abstractmethod
    async def get_new_orders(self) -> List[ChannelOrder]:
        """신규 주문 조회"""
        pass
    
    @abstractmethod
    async def get_order_detail(self, order_id: str) -> Optional[ChannelOrder]:
        """주문 상세 조회"""
        pass
    
    @abstractmethod
    async def confirm_order(self, order_id: str) -> bool:
        """발주 확인"""
        pass
    
    @abstractmethod
    async def register_invoice(self, order_id: str, tracking_number: str, carrier: str = "CJ대한통운") -> bool:
        """송장 등록"""
        pass
    
    @abstractmethod
    async def get_claims(self) -> List[ChannelClaim]:
        """클레임(반품/교환/취소) 조회"""
        pass
    
    @abstractmethod
    async def update_stock(self, product_id: str, quantity: int) -> bool:
        """재고 업데이트"""
        pass
    
    async def close(self):
        """리소스 정리"""
        pass
