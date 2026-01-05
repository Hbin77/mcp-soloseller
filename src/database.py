"""
데이터베이스 모델
SQLAlchemy ORM 모델 정의
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import enum


class Base(DeclarativeBase):
    """Base 클래스"""
    pass


# ============================================
# Enum 정의
# ============================================

class ChannelType(str, enum.Enum):
    """판매 채널"""
    NAVER = "naver"
    COUPANG = "coupang"


class OrderStatus(str, enum.Enum):
    """주문 상태"""
    NEW = "new"                      # 신규 주문
    CONFIRMED = "confirmed"          # 발주 확인
    SHIPPED = "shipped"              # 발송 완료
    DELIVERING = "delivering"        # 배송 중
    DELIVERED = "delivered"          # 배송 완료
    CANCELLED = "cancelled"          # 취소


class ClaimType(str, enum.Enum):
    """클레임 유형"""
    RETURN = "return"                # 반품
    EXCHANGE = "exchange"            # 교환
    CANCEL = "cancel"                # 취소


class ClaimStatus(str, enum.Enum):
    """클레임 상태"""
    REQUESTED = "requested"          # 요청됨
    APPROVED = "approved"            # 승인됨
    REJECTED = "rejected"            # 거절됨
    COMPLETED = "completed"          # 완료됨


class DeliveryStatus(str, enum.Enum):
    """배송 상태"""
    READY = "ready"                  # 배송 준비
    PICKED_UP = "picked_up"          # 집화
    IN_TRANSIT = "in_transit"        # 배송 중
    OUT_FOR_DELIVERY = "out_for_delivery"  # 배송 출발
    DELIVERED = "delivered"          # 배송 완료
    FAILED = "failed"                # 배송 실패


class StockChangeReason(str, enum.Enum):
    """재고 변동 사유"""
    ORDER = "order"                  # 주문으로 인한 차감
    RETURN = "return"                # 반품으로 인한 증가
    ADJUSTMENT = "adjustment"        # 수동 조정
    INCOMING = "incoming"            # 입고


# ============================================
# 사용자 모델
# ============================================

class User(Base):
    """사용자 모델"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))

    # 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # 시간
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 관계
    settings: Mapped[Optional["UserSettings"]] = relationship(back_populates="user", uselist=False)
    products: Mapped[list["Product"]] = relationship(back_populates="user")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class UserSettings(Base):
    """사용자별 설정"""
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    # 네이버 스마트스토어
    naver_client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    naver_client_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    naver_seller_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 쿠팡
    coupang_vendor_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    coupang_access_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    coupang_secret_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 발송인 정보
    sender_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sender_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sender_zipcode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sender_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 기본 택배사
    default_carrier: Mapped[str] = mapped_column(String(20), default="cj")

    # 택배사 API 설정 (JSON 형태로 저장)
    carrier_settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 텔레그램
    telegram_bot_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 스케줄
    schedule_first_batch: Mapped[str] = mapped_column(String(10), default="12:00")
    schedule_second_batch: Mapped[str] = mapped_column(String(10), default="15:30")

    # MCP API 키
    mcp_api_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    mcp_api_key_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 시간
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    user: Mapped["User"] = relationship(back_populates="settings")


# ============================================
# 모델 정의
# ============================================

class Product(Base):
    """상품 모델"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)  # 내부 SKU (user별 unique)
    name: Mapped[str] = mapped_column(String(500))
    
    # 채널별 상품 ID
    naver_product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    coupang_product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 재고
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    stock_alert_threshold: Mapped[int] = mapped_column(Integer, default=5)
    
    # 가격
    price: Mapped[float] = mapped_column(Float, default=0)
    
    # 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # 시간
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    user: Mapped["User"] = relationship(back_populates="products")
    stock_history: Mapped[list["StockHistory"]] = relationship(back_populates="product")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")


class Order(Base):
    """주문 모델"""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # 채널 정보
    channel: Mapped[ChannelType] = mapped_column(SQLEnum(ChannelType))
    channel_order_id: Mapped[str] = mapped_column(String(100), index=True)  # 채널의 주문 ID
    
    # 주문 상태
    status: Mapped[OrderStatus] = mapped_column(SQLEnum(OrderStatus), default=OrderStatus.NEW)
    
    # 주문자 정보
    buyer_name: Mapped[str] = mapped_column(String(100))
    buyer_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    buyer_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # 수령인 정보
    receiver_name: Mapped[str] = mapped_column(String(100))
    receiver_phone: Mapped[str] = mapped_column(String(20))
    receiver_address: Mapped[str] = mapped_column(Text)
    receiver_zipcode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # 배송 정보
    tracking_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    carrier: Mapped[str] = mapped_column(String(50), default="CJ대한통운")
    
    # 금액
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    shipping_fee: Mapped[float] = mapped_column(Float, default=0)
    
    # 메모
    buyer_memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 시간
    ordered_at: Mapped[datetime] = mapped_column(DateTime)  # 채널에서의 주문 시간
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 처리 배치 (1차/2차)
    batch_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1 또는 2
    batch_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    
    # 관계
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(back_populates="order")
    delivery_tracking: Mapped[list["DeliveryTracking"]] = relationship(back_populates="order")


class OrderItem(Base):
    """주문 상품 모델"""
    __tablename__ = "order_items"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    
    # 채널 상품 정보 (매핑 안 된 경우 대비)
    channel_product_id: Mapped[str] = mapped_column(String(100))
    channel_product_name: Mapped[str] = mapped_column(String(500))
    channel_option_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    total_price: Mapped[float] = mapped_column(Float, default=0)
    
    # 관계
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped[Optional["Product"]] = relationship(back_populates="order_items")


class StockHistory(Base):
    """재고 변동 이력"""
    __tablename__ = "stock_history"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    
    # 변동 정보
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_change: Mapped[int] = mapped_column(Integer)  # 양수: 증가, 음수: 감소
    quantity_after: Mapped[int] = mapped_column(Integer)
    
    reason: Mapped[StockChangeReason] = mapped_column(SQLEnum(StockChangeReason))
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 주문번호 등
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 관계
    product: Mapped["Product"] = relationship(back_populates="stock_history")


class Claim(Base):
    """클레임 (반품/교환/취소) 모델"""
    __tablename__ = "claims"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    
    # 채널 정보
    channel: Mapped[ChannelType] = mapped_column(SQLEnum(ChannelType))
    channel_claim_id: Mapped[str] = mapped_column(String(100))
    
    # 클레임 정보
    claim_type: Mapped[ClaimType] = mapped_column(SQLEnum(ClaimType))
    status: Mapped[ClaimStatus] = mapped_column(SQLEnum(ClaimStatus), default=ClaimStatus.REQUESTED)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 시간
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 관계
    order: Mapped["Order"] = relationship(back_populates="claims")


class DeliveryTracking(Base):
    """배송 추적 이력"""
    __tablename__ = "delivery_tracking"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    tracking_number: Mapped[str] = mapped_column(String(50), index=True)
    
    # 배송 상태
    status: Mapped[DeliveryStatus] = mapped_column(SQLEnum(DeliveryStatus))
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    tracked_at: Mapped[datetime] = mapped_column(DateTime)  # 배송사에서의 시간
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 관계
    order: Mapped["Order"] = relationship(back_populates="delivery_tracking")


class ProcessingLog(Base):
    """처리 로그 (1차/2차 배치 처리 기록)"""
    __tablename__ = "processing_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    batch_number: Mapped[int] = mapped_column(Integer)  # 1 또는 2
    batch_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    
    # 처리 결과
    orders_collected: Mapped[int] = mapped_column(Integer, default=0)
    orders_confirmed: Mapped[int] = mapped_column(Integer, default=0)
    invoices_printed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    
    # 상세 로그
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 형태
    
    started_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================
# 데이터베이스 연결 관리
# ============================================

class Database:
    """데이터베이스 연결 관리"""
    
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    async def init_db(self):
        """데이터베이스 테이블 생성"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def get_session(self) -> AsyncSession:
        """세션 반환"""
        async with self.async_session() as session:
            yield session
