"""
대시보드 API
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date, timedelta
from typing import Optional

from ..database import Database, Order, Product, Claim, ProcessingLog, OrderStatus, ChannelType

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


async def get_db():
    """DB 세션 의존성"""
    from ..main import server
    async with server.db.async_session() as session:
        yield session


@router.get("/summary")
async def get_dashboard_summary(session: AsyncSession = Depends(get_db)):
    """대시보드 요약 데이터"""
    today = date.today()
    
    # 오늘 주문 수
    today_orders = await session.execute(
        select(func.count(Order.id)).where(func.date(Order.ordered_at) == today)
    )
    
    # 오늘 매출
    today_sales = await session.execute(
        select(func.sum(Order.total_amount)).where(func.date(Order.ordered_at) == today)
    )
    
    # 발송 대기 주문
    pending_orders = await session.execute(
        select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED])
        )
    )
    
    # 재고 부족 상품
    low_stock = await session.execute(
        select(func.count(Product.id)).where(
            Product.stock_quantity <= Product.stock_alert_threshold,
            Product.is_active == True
        )
    )
    
    # 처리 대기 클레임
    pending_claims = await session.execute(
        select(func.count(Claim.id)).where(Claim.status == "requested")
    )
    
    # 채널별 오늘 주문
    channel_orders = await session.execute(
        select(
            Order.channel,
            func.count(Order.id).label('count'),
            func.sum(Order.total_amount).label('total')
        ).where(
            func.date(Order.ordered_at) == today
        ).group_by(Order.channel)
    )
    channel_data = {row.channel.value: {"count": row.count, "total": row.total or 0} for row in channel_orders}
    
    return {
        "today": {
            "orders": today_orders.scalar() or 0,
            "sales": today_sales.scalar() or 0,
            "by_channel": channel_data
        },
        "pending": {
            "orders": pending_orders.scalar() or 0,
            "claims": pending_claims.scalar() or 0
        },
        "alerts": {
            "low_stock": low_stock.scalar() or 0
        },
        "updated_at": datetime.now().isoformat()
    }


@router.get("/chart/orders")
async def get_orders_chart(days: int = 7, session: AsyncSession = Depends(get_db)):
    """주문 차트 데이터 (최근 N일)"""
    start_date = date.today() - timedelta(days=days-1)
    
    result = await session.execute(
        select(
            func.date(Order.ordered_at).label('date'),
            Order.channel,
            func.count(Order.id).label('count'),
            func.sum(Order.total_amount).label('total')
        ).where(
            func.date(Order.ordered_at) >= start_date
        ).group_by(
            func.date(Order.ordered_at),
            Order.channel
        ).order_by(func.date(Order.ordered_at))
    )
    
    data = {}
    for row in result:
        date_str = row.date.isoformat() if row.date else str(row.date)
        if date_str not in data:
            data[date_str] = {"date": date_str, "naver": 0, "coupang": 0, "total": 0}
        data[date_str][row.channel.value] = row.count
        data[date_str]["total"] += row.count
    
    # 빈 날짜 채우기
    result_list = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).isoformat()
        if d in data:
            result_list.append(data[d])
        else:
            result_list.append({"date": d, "naver": 0, "coupang": 0, "total": 0})
    
    return result_list


@router.get("/chart/sales")
async def get_sales_chart(days: int = 7, session: AsyncSession = Depends(get_db)):
    """매출 차트 데이터 (최근 N일)"""
    start_date = date.today() - timedelta(days=days-1)
    
    result = await session.execute(
        select(
            func.date(Order.ordered_at).label('date'),
            func.sum(Order.total_amount).label('total')
        ).where(
            func.date(Order.ordered_at) >= start_date
        ).group_by(
            func.date(Order.ordered_at)
        ).order_by(func.date(Order.ordered_at))
    )
    
    data = {row.date.isoformat(): row.total or 0 for row in result}
    
    result_list = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).isoformat()
        result_list.append({"date": d, "sales": data.get(d, 0)})
    
    return result_list


@router.get("/recent-orders")
async def get_recent_orders(limit: int = 10, session: AsyncSession = Depends(get_db)):
    """최근 주문 목록"""
    result = await session.execute(
        select(Order).order_by(Order.ordered_at.desc()).limit(limit)
    )
    orders = result.scalars().all()
    
    return [
        {
            "id": o.id,
            "channel": o.channel.value,
            "channel_order_id": o.channel_order_id,
            "status": o.status.value,
            "buyer_name": o.buyer_name,
            "total_amount": o.total_amount,
            "ordered_at": o.ordered_at.isoformat()
        }
        for o in orders
    ]


@router.get("/processing-logs")
async def get_processing_logs(limit: int = 10, session: AsyncSession = Depends(get_db)):
    """최근 배치 처리 로그"""
    result = await session.execute(
        select(ProcessingLog).order_by(ProcessingLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    
    return [
        {
            "id": l.id,
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
