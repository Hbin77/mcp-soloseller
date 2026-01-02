"""
쇼핑몰 자동화 MCP 서버
다채널 통합 + 자동 송장 처리 + 재고 관리
"""
import asyncio
import json
from datetime import datetime, date
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.config import get_settings, Settings
from src.database import (
    Database, Product, Order, OrderItem, StockHistory, Claim, 
    DeliveryTracking, ProcessingLog, OrderStatus, ChannelType,
    StockChangeReason, ClaimStatus, ClaimType
)
from src.channels.naver import NaverCommerceClient
from src.channels.coupang import CoupangWingClient
from src.channels import ChannelOrder
from src.notifications import NotificationManager, TelegramNotifier, SlackNotifier, EmailNotifier

# 로깅 설정
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


class ShopAutomationServer:
    """쇼핑몰 자동화 MCP 서버"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mcp = Server("shop-automation")
        self.db = Database(settings.database_url)
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone)
        
        # 채널 클라이언트
        self.naver_client: Optional[NaverCommerceClient] = None
        self.coupang_client: Optional[CoupangWingClient] = None
        
        # 알림 관리자
        self.notifier: Optional[NotificationManager] = None
        
        # MCP Tools 등록
        self._register_tools()
    
    async def initialize(self):
        """서버 초기화"""
        logger.info("서버 초기화 시작")
        
        # DB 초기화
        await self.db.init_db()
        logger.info("데이터베이스 초기화 완료")
        
        # 채널 클라이언트 초기화
        if self.settings.naver_configured:
            self.naver_client = NaverCommerceClient(
                self.settings.naver_client_id,
                self.settings.naver_client_secret,
                self.settings.naver_seller_id
            )
            logger.info("네이버 클라이언트 초기화 완료")
        
        if self.settings.coupang_configured:
            self.coupang_client = CoupangWingClient(
                self.settings.coupang_vendor_id,
                self.settings.coupang_access_key,
                self.settings.coupang_secret_key
            )
            logger.info("쿠팡 클라이언트 초기화 완료")
        
        # 알림 관리자 초기화
        telegram = None
        if self.settings.telegram_configured:
            telegram = TelegramNotifier(
                self.settings.telegram_bot_token,
                self.settings.telegram_chat_id
            )
        
        slack = None
        if self.settings.slack_webhook_url:
            slack = SlackNotifier(self.settings.slack_webhook_url)
        
        email = None
        if self.settings.smtp_user:
            email = EmailNotifier(
                self.settings.smtp_host,
                self.settings.smtp_port,
                self.settings.smtp_user,
                self.settings.smtp_password,
                self.settings.smtp_from,
                self.settings.smtp_to
            )
        
        self.notifier = NotificationManager(telegram, slack, email)
        logger.info("알림 관리자 초기화 완료")
        
        # 스케줄러 설정
        self._setup_scheduler()
        self.scheduler.start()
        logger.info("스케줄러 시작 완료")
    
    def _setup_scheduler(self):
        """스케줄러 설정 - 1차/2차 송장 처리"""
        # 1차 처리 (12:00)
        first_hour, first_minute = self.settings.schedule_first_batch.split(":")
        self.scheduler.add_job(
            self._run_batch_processing,
            CronTrigger(hour=int(first_hour), minute=int(first_minute)),
            args=[1],
            id="batch_1",
            name="1차 송장 처리"
        )
        
        # 2차 처리 (15:30)
        second_hour, second_minute = self.settings.schedule_second_batch.split(":")
        self.scheduler.add_job(
            self._run_batch_processing,
            CronTrigger(hour=int(second_hour), minute=int(second_minute)),
            args=[2],
            id="batch_2",
            name="2차 송장 처리"
        )
        
        # 배송 추적 (30분 간격)
        self.scheduler.add_job(
            self._run_delivery_tracking,
            'interval',
            minutes=self.settings.tracking_interval_minutes,
            id="delivery_tracking",
            name="배송 추적"
        )
        
        logger.info(
            "스케줄러 설정 완료",
            first_batch=self.settings.schedule_first_batch,
            second_batch=self.settings.schedule_second_batch,
            tracking_interval=self.settings.tracking_interval_minutes
        )
    
    async def _run_batch_processing(self, batch_number: int):
        """배치 처리 실행 (1차 또는 2차)"""
        logger.info(f"{batch_number}차 송장 처리 시작")
        
        results = {
            "collected": 0,
            "confirmed": 0,
            "printed": 0,
            "errors": 0
        }
        
        try:
            # 1. 신규 주문 수집
            orders = await self._collect_new_orders()
            results["collected"] = len(orders)
            
            # 2. 발주 확인 + 재고 차감 + 송장 등록
            for order in orders:
                try:
                    # 발주 확인
                    confirmed = await self._confirm_order(order)
                    if confirmed:
                        results["confirmed"] += 1
                        
                        # 송장 발급 (TODO: CJ대한통운 연동)
                        # 현재는 더미 송장번호 생성
                        tracking_number = f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}{order.id}"
                        
                        # 채널에 송장 등록
                        registered = await self._register_invoice_to_channel(order, tracking_number)
                        if registered:
                            results["printed"] += 1
                except Exception as e:
                    logger.exception("주문 처리 오류", order_id=order.id, error=str(e))
                    results["errors"] += 1
            
            # 3. 처리 결과 알림
            if self.notifier:
                await self.notifier.notify_batch_complete(batch_number, results)
            
            # 4. 처리 로그 저장
            await self._save_processing_log(batch_number, results)
            
        except Exception as e:
            logger.exception(f"{batch_number}차 처리 오류", error=str(e))
            if self.notifier:
                await self.notifier.notify_error(f"{batch_number}차 송장 처리", str(e))
        
        logger.info(f"{batch_number}차 송장 처리 완료", results=results)
    
    async def _collect_new_orders(self) -> List[Order]:
        """신규 주문 수집"""
        all_orders = []
        
        async with self.db.async_session() as session:
            # 네이버 주문 수집
            if self.naver_client:
                try:
                    naver_orders = await self.naver_client.get_new_orders()
                    for order_data in naver_orders:
                        order = await self._save_order(session, order_data, ChannelType.NAVER)
                        if order:
                            all_orders.append(order)
                except Exception as e:
                    logger.exception("네이버 주문 수집 오류", error=str(e))
            
            # 쿠팡 주문 수집
            if self.coupang_client:
                try:
                    coupang_orders = await self.coupang_client.get_new_orders()
                    for order_data in coupang_orders:
                        order = await self._save_order(session, order_data, ChannelType.COUPANG)
                        if order:
                            all_orders.append(order)
                except Exception as e:
                    logger.exception("쿠팡 주문 수집 오류", error=str(e))
            
            await session.commit()
        
        return all_orders
    
    async def _save_order(self, session: AsyncSession, order_data: ChannelOrder, channel: ChannelType) -> Optional[Order]:
        """주문 저장"""
        # 이미 존재하는지 확인
        result = await session.execute(
            select(Order).where(
                Order.channel == channel,
                Order.channel_order_id == order_data.channel_order_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return None  # 이미 수집된 주문
        
        # 새 주문 생성
        order = Order(
            channel=channel,
            channel_order_id=order_data.channel_order_id,
            status=OrderStatus.NEW,
            buyer_name=order_data.buyer_name,
            buyer_phone=order_data.buyer_phone,
            buyer_email=order_data.buyer_email,
            receiver_name=order_data.receiver_name,
            receiver_phone=order_data.receiver_phone,
            receiver_address=order_data.receiver_address,
            receiver_zipcode=order_data.receiver_zipcode,
            total_amount=order_data.total_amount,
            shipping_fee=order_data.shipping_fee,
            buyer_memo=order_data.buyer_memo,
            ordered_at=order_data.ordered_at
        )
        session.add(order)
        await session.flush()
        
        # 주문 상품 추가
        for item_data in order_data.items:
            item = OrderItem(
                order_id=order.id,
                channel_product_id=item_data.channel_product_id,
                channel_product_name=item_data.product_name,
                channel_option_name=item_data.option_name,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                total_price=item_data.total_price
            )
            session.add(item)
        
        return order
    
    async def _confirm_order(self, order: Order) -> bool:
        """발주 확인"""
        client = self.naver_client if order.channel == ChannelType.NAVER else self.coupang_client
        if not client:
            return False
        
        success = await client.confirm_order(order.channel_order_id)
        
        if success:
            async with self.db.async_session() as session:
                order.status = OrderStatus.CONFIRMED
                order.confirmed_at = datetime.now()
                session.add(order)
                await session.commit()
        
        return success
    
    async def _register_invoice_to_channel(self, order: Order, tracking_number: str) -> bool:
        """채널에 송장 등록"""
        client = self.naver_client if order.channel == ChannelType.NAVER else self.coupang_client
        if not client:
            return False
        
        success = await client.register_invoice(order.channel_order_id, tracking_number)
        
        if success:
            async with self.db.async_session() as session:
                order.status = OrderStatus.SHIPPED
                order.tracking_number = tracking_number
                order.shipped_at = datetime.now()
                session.add(order)
                await session.commit()
        
        return success
    
    async def _run_delivery_tracking(self):
        """배송 추적 실행"""
        logger.info("배송 추적 시작")
        # TODO: Delivery Tracker API 연동
        logger.info("배송 추적 완료")
    
    async def _save_processing_log(self, batch_number: int, results: dict):
        """처리 로그 저장"""
        async with self.db.async_session() as session:
            log = ProcessingLog(
                batch_number=batch_number,
                batch_date=date.today().isoformat(),
                orders_collected=results["collected"],
                orders_confirmed=results["confirmed"],
                invoices_printed=results["printed"],
                errors=results["errors"],
                details=json.dumps(results),
                started_at=datetime.now(),
                completed_at=datetime.now()
            )
            session.add(log)
            await session.commit()
    
    def _register_tools(self):
        """MCP Tools 등록"""
        
        @self.mcp.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                # 주문 관리
                Tool(name="get_new_orders", description="모든 채널에서 신규 주문 수집", inputSchema={"type": "object", "properties": {}}),
                Tool(name="get_pending_orders", description="발송 대기 중인 주문 목록", inputSchema={"type": "object", "properties": {}}),
                Tool(name="process_batch", description="수동으로 배치 처리 실행", inputSchema={
                    "type": "object",
                    "properties": {"batch_number": {"type": "integer", "description": "배치 번호 (1 또는 2)"}},
                    "required": ["batch_number"]
                }),
                
                # 재고 관리
                Tool(name="get_stock", description="상품 재고 조회", inputSchema={
                    "type": "object",
                    "properties": {"sku": {"type": "string", "description": "상품 SKU"}},
                    "required": ["sku"]
                }),
                Tool(name="update_stock", description="재고 수량 업데이트", inputSchema={
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "description": "상품 SKU"},
                        "quantity": {"type": "integer", "description": "변경할 수량"},
                        "reason": {"type": "string", "description": "변경 사유", "enum": ["incoming", "adjustment"]}
                    },
                    "required": ["sku", "quantity", "reason"]
                }),
                Tool(name="get_low_stock_alerts", description="재고 부족 상품 목록", inputSchema={"type": "object", "properties": {}}),
                Tool(name="sync_stock_all_channels", description="모든 채널 재고 동기화", inputSchema={"type": "object", "properties": {}}),
                
                # 클레임 관리
                Tool(name="get_claims", description="반품/교환/취소 요청 조회", inputSchema={"type": "object", "properties": {}}),
                
                # 리포트
                Tool(name="get_daily_report", description="일일 리포트 조회", inputSchema={
                    "type": "object",
                    "properties": {"date": {"type": "string", "description": "조회 날짜 (YYYY-MM-DD)"}}
                }),
                Tool(name="get_processing_logs", description="배치 처리 이력 조회", inputSchema={
                    "type": "object",
                    "properties": {"days": {"type": "integer", "description": "최근 N일", "default": 7}}
                }),
                
                # 알림
                Tool(name="send_test_notification", description="테스트 알림 발송", inputSchema={
                    "type": "object",
                    "properties": {"message": {"type": "string", "description": "메시지 내용"}},
                    "required": ["message"]
                }),
                
                # 상품 관리
                Tool(name="add_product", description="신규 상품 등록", inputSchema={
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "name": {"type": "string"},
                        "stock_quantity": {"type": "integer"},
                        "price": {"type": "number"},
                        "naver_product_id": {"type": "string"},
                        "coupang_product_id": {"type": "string"}
                    },
                    "required": ["sku", "name"]
                }),
                Tool(name="list_products", description="상품 목록 조회", inputSchema={"type": "object", "properties": {}})
            ]
        
        @self.mcp.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            result = await self._handle_tool(name, arguments)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    
    async def _handle_tool(self, name: str, arguments: dict) -> Any:
        """Tool 실행 핸들러"""
        try:
            if name == "get_new_orders":
                return await self._tool_get_new_orders()
            elif name == "get_pending_orders":
                return await self._tool_get_pending_orders()
            elif name == "process_batch":
                return await self._tool_process_batch(arguments.get("batch_number", 1))
            elif name == "get_stock":
                return await self._tool_get_stock(arguments["sku"])
            elif name == "update_stock":
                return await self._tool_update_stock(
                    arguments["sku"],
                    arguments["quantity"],
                    arguments["reason"]
                )
            elif name == "get_low_stock_alerts":
                return await self._tool_get_low_stock_alerts()
            elif name == "sync_stock_all_channels":
                return await self._tool_sync_stock_all_channels()
            elif name == "get_claims":
                return await self._tool_get_claims()
            elif name == "get_daily_report":
                return await self._tool_get_daily_report(arguments.get("date"))
            elif name == "get_processing_logs":
                return await self._tool_get_processing_logs(arguments.get("days", 7))
            elif name == "send_test_notification":
                return await self._tool_send_test_notification(arguments["message"])
            elif name == "add_product":
                return await self._tool_add_product(arguments)
            elif name == "list_products":
                return await self._tool_list_products()
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.exception(f"Tool 실행 오류: {name}", error=str(e))
            return {"error": str(e)}
    
    async def _tool_get_new_orders(self) -> dict:
        """신규 주문 수집"""
        orders = await self._collect_new_orders()
        return {
            "success": True,
            "collected": len(orders),
            "orders": [
                {
                    "id": o.id,
                    "channel": o.channel.value,
                    "channel_order_id": o.channel_order_id,
                    "buyer_name": o.buyer_name,
                    "total_amount": o.total_amount,
                    "ordered_at": o.ordered_at.isoformat()
                }
                for o in orders
            ]
        }
    
    async def _tool_get_pending_orders(self) -> dict:
        """발송 대기 주문 조회"""
        async with self.db.async_session() as session:
            result = await session.execute(
                select(Order).where(Order.status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED]))
            )
            orders = result.scalars().all()
            
            return {
                "success": True,
                "count": len(orders),
                "orders": [
                    {
                        "id": o.id,
                        "channel": o.channel.value,
                        "channel_order_id": o.channel_order_id,
                        "status": o.status.value,
                        "buyer_name": o.buyer_name,
                        "receiver_name": o.receiver_name,
                        "total_amount": o.total_amount,
                        "ordered_at": o.ordered_at.isoformat()
                    }
                    for o in orders
                ]
            }
    
    async def _tool_process_batch(self, batch_number: int) -> dict:
        """수동 배치 처리"""
        await self._run_batch_processing(batch_number)
        return {"success": True, "message": f"{batch_number}차 처리 완료"}
    
    async def _tool_get_stock(self, sku: str) -> dict:
        """재고 조회"""
        async with self.db.async_session() as session:
            result = await session.execute(
                select(Product).where(Product.sku == sku)
            )
            product = result.scalar_one_or_none()
            
            if not product:
                return {"success": False, "error": "상품을 찾을 수 없습니다"}
            
            return {
                "success": True,
                "product": {
                    "sku": product.sku,
                    "name": product.name,
                    "stock_quantity": product.stock_quantity,
                    "alert_threshold": product.stock_alert_threshold,
                    "is_low_stock": product.stock_quantity <= product.stock_alert_threshold
                }
            }
    
    async def _tool_update_stock(self, sku: str, quantity: int, reason: str) -> dict:
        """재고 업데이트"""
        async with self.db.async_session() as session:
            result = await session.execute(
                select(Product).where(Product.sku == sku)
            )
            product = result.scalar_one_or_none()
            
            if not product:
                return {"success": False, "error": "상품을 찾을 수 없습니다"}
            
            before = product.stock_quantity
            product.stock_quantity += quantity
            
            # 재고 이력 저장
            history = StockHistory(
                product_id=product.id,
                quantity_before=before,
                quantity_change=quantity,
                quantity_after=product.stock_quantity,
                reason=StockChangeReason(reason),
                memo=f"수동 조정: {reason}"
            )
            session.add(history)
            await session.commit()
            
            return {
                "success": True,
                "product": {
                    "sku": product.sku,
                    "name": product.name,
                    "before": before,
                    "change": quantity,
                    "after": product.stock_quantity
                }
            }
    
    async def _tool_get_low_stock_alerts(self) -> dict:
        """재고 부족 상품 조회"""
        async with self.db.async_session() as session:
            result = await session.execute(
                select(Product).where(
                    Product.stock_quantity <= Product.stock_alert_threshold,
                    Product.is_active == True
                )
            )
            products = result.scalars().all()
            
            return {
                "success": True,
                "count": len(products),
                "products": [
                    {
                        "sku": p.sku,
                        "name": p.name,
                        "stock_quantity": p.stock_quantity,
                        "alert_threshold": p.stock_alert_threshold
                    }
                    for p in products
                ]
            }
    
    async def _tool_sync_stock_all_channels(self) -> dict:
        """모든 채널 재고 동기화"""
        results = {"naver": 0, "coupang": 0, "errors": []}
        
        async with self.db.async_session() as session:
            result = await session.execute(select(Product).where(Product.is_active == True))
            products = result.scalars().all()
            
            for product in products:
                # 네이버 동기화
                if product.naver_product_id and self.naver_client:
                    try:
                        success = await self.naver_client.update_stock(
                            product.naver_product_id,
                            product.stock_quantity
                        )
                        if success:
                            results["naver"] += 1
                    except Exception as e:
                        results["errors"].append(f"네이버 {product.sku}: {str(e)}")
                
                # 쿠팡 동기화
                if product.coupang_product_id and self.coupang_client:
                    try:
                        success = await self.coupang_client.update_stock(
                            product.coupang_product_id,
                            product.stock_quantity
                        )
                        if success:
                            results["coupang"] += 1
                    except Exception as e:
                        results["errors"].append(f"쿠팡 {product.sku}: {str(e)}")
        
        return {"success": True, "results": results}
    
    async def _tool_get_claims(self) -> dict:
        """클레임 조회"""
        all_claims = []
        
        if self.naver_client:
            claims = await self.naver_client.get_claims()
            for c in claims:
                all_claims.append({
                    "channel": "naver",
                    "claim_id": c.channel_claim_id,
                    "order_id": c.channel_order_id,
                    "type": c.claim_type,
                    "status": c.status,
                    "reason": c.reason,
                    "requested_at": c.requested_at.isoformat()
                })
        
        if self.coupang_client:
            claims = await self.coupang_client.get_claims()
            for c in claims:
                all_claims.append({
                    "channel": "coupang",
                    "claim_id": c.channel_claim_id,
                    "order_id": c.channel_order_id,
                    "type": c.claim_type,
                    "status": c.status,
                    "reason": c.reason,
                    "requested_at": c.requested_at.isoformat()
                })
        
        return {"success": True, "count": len(all_claims), "claims": all_claims}
    
    async def _tool_get_daily_report(self, date_str: Optional[str] = None) -> dict:
        """일일 리포트"""
        target_date = date.fromisoformat(date_str) if date_str else date.today()
        
        async with self.db.async_session() as session:
            # 주문 통계
            order_result = await session.execute(
                select(
                    Order.channel,
                    func.count(Order.id).label('count'),
                    func.sum(Order.total_amount).label('total')
                ).where(
                    func.date(Order.ordered_at) == target_date
                ).group_by(Order.channel)
            )
            orders = order_result.all()
            
            # 배송 통계
            shipped = await session.execute(
                select(func.count(Order.id)).where(
                    func.date(Order.shipped_at) == target_date
                )
            )
            delivered = await session.execute(
                select(func.count(Order.id)).where(
                    func.date(Order.delivered_at) == target_date
                )
            )
            
            report = {
                "date": target_date.isoformat(),
                "orders": {
                    "total": sum(o.count for o in orders),
                    "naver": next((o.count for o in orders if o.channel == ChannelType.NAVER), 0),
                    "coupang": next((o.count for o in orders if o.channel == ChannelType.COUPANG), 0)
                },
                "sales": {
                    "total": sum(o.total or 0 for o in orders),
                    "naver": next((o.total or 0 for o in orders if o.channel == ChannelType.NAVER), 0),
                    "coupang": next((o.total or 0 for o in orders if o.channel == ChannelType.COUPANG), 0)
                },
                "shipping": {
                    "shipped": shipped.scalar() or 0,
                    "delivered": delivered.scalar() or 0
                }
            }
            
            return {"success": True, "report": report}
    
    async def _tool_get_processing_logs(self, days: int) -> dict:
        """처리 로그 조회"""
        async with self.db.async_session() as session:
            result = await session.execute(
                select(ProcessingLog).order_by(ProcessingLog.created_at.desc()).limit(days * 2)
            )
            logs = result.scalars().all()
            
            return {
                "success": True,
                "logs": [
                    {
                        "batch_number": l.batch_number,
                        "batch_date": l.batch_date,
                        "orders_collected": l.orders_collected,
                        "orders_confirmed": l.orders_confirmed,
                        "invoices_printed": l.invoices_printed,
                        "errors": l.errors,
                        "completed_at": l.completed_at.isoformat() if l.completed_at else None
                    }
                    for l in logs
                ]
            }
    
    async def _tool_send_test_notification(self, message: str) -> dict:
        """테스트 알림 발송"""
        if not self.notifier:
            return {"success": False, "error": "알림이 설정되지 않았습니다"}
        
        results = await self.notifier._send_all(message)
        return {
            "success": True,
            "results": [{"channel": r.channel, "success": r.success, "error": r.error} for r in results]
        }
    
    async def _tool_add_product(self, args: dict) -> dict:
        """상품 등록"""
        async with self.db.async_session() as session:
            product = Product(
                sku=args["sku"],
                name=args["name"],
                stock_quantity=args.get("stock_quantity", 0),
                price=args.get("price", 0),
                naver_product_id=args.get("naver_product_id"),
                coupang_product_id=args.get("coupang_product_id"),
                stock_alert_threshold=args.get("stock_alert_threshold", self.settings.stock_alert_threshold)
            )
            session.add(product)
            await session.commit()
            
            return {
                "success": True,
                "product": {
                    "id": product.id,
                    "sku": product.sku,
                    "name": product.name
                }
            }
    
    async def _tool_list_products(self) -> dict:
        """상품 목록 조회"""
        async with self.db.async_session() as session:
            result = await session.execute(select(Product).where(Product.is_active == True))
            products = result.scalars().all()
            
            return {
                "success": True,
                "count": len(products),
                "products": [
                    {
                        "id": p.id,
                        "sku": p.sku,
                        "name": p.name,
                        "stock_quantity": p.stock_quantity,
                        "price": p.price,
                        "naver_id": p.naver_product_id,
                        "coupang_id": p.coupang_product_id
                    }
                    for p in products
                ]
            }
    
    async def cleanup(self):
        """서버 종료 시 정리"""
        logger.info("서버 종료 중...")
        
        self.scheduler.shutdown()
        
        if self.naver_client:
            await self.naver_client.close()
        if self.coupang_client:
            await self.coupang_client.close()
        if self.notifier:
            await self.notifier.close()
        
        logger.info("서버 종료 완료")


# FastAPI 앱 생성
settings = get_settings()
server = ShopAutomationServer(settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await server.initialize()
    yield
    await server.cleanup()

app = FastAPI(
    title="쇼핑몰 자동화 MCP 서버",
    description="다채널 통합 쇼핑몰 자동화 시스템",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
from src.api.dashboard import router as dashboard_router
from src.api.orders import router as orders_router
from src.api.products import router as products_router
from src.api.settings import router as settings_router
from src.api.claims import router as claims_router
from src.api.export import router as export_router
from src.api.auth import router as auth_router
from src.api.webhooks import router as webhooks_router

app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(claims_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")

# 정적 파일 서빙
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# 메인 페이지
@app.get("/")
async def root():
    """웹 UI 메인 페이지"""
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "쇼핑몰 자동화 MCP 서버", "docs": "/docs"}

# 설정 마법사
@app.get("/setup")
async def setup_wizard():
    """설정 마법사 페이지"""
    setup_path = os.path.join(static_path, "setup.html")
    if os.path.exists(setup_path):
        return FileResponse(setup_path)
    return {"error": "Setup page not found"}

# SSE 엔드포인트
@app.get("/sse")
async def sse_endpoint():
    from starlette.responses import StreamingResponse
    transport = SseServerTransport("/messages")
    
    async def event_generator():
        async with transport.connect_sse(server.mcp) as streams:
            async for event in streams:
                yield event
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/messages")
async def messages_endpoint(request):
    # MCP 메시지 처리
    pass

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
