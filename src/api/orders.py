"""
주문 관리 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, date, timedelta
from typing import Optional, List
from pydantic import BaseModel

from ..database import Order, OrderItem, OrderStatus, ChannelType

router = APIRouter(prefix="/orders", tags=["Orders"])


async def get_db():
    from ..main import server
    async with server.db.async_session() as session:
        yield session


class OrderFilter(BaseModel):
    status: Optional[str] = None
    channel: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    search: Optional[str] = None


@router.get("")
async def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    channel: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """주문 목록 조회"""
    query = select(Order).options(selectinload(Order.items))
    
    # 필터 적용
    if status:
        query = query.where(Order.status == OrderStatus(status))
    if channel:
        query = query.where(Order.channel == ChannelType(channel))
    if date_from:
        query = query.where(Order.ordered_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.where(Order.ordered_at <= datetime.fromisoformat(date_to + "T23:59:59"))
    if search:
        query = query.where(
            or_(
                Order.channel_order_id.contains(search),
                Order.buyer_name.contains(search),
                Order.receiver_name.contains(search),
                Order.tracking_number.contains(search)
            )
        )
    
    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar()
    
    # 페이지네이션
    query = query.order_by(Order.ordered_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await session.execute(query)
    orders = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "orders": [
            {
                "id": o.id,
                "channel": o.channel.value,
                "channel_order_id": o.channel_order_id,
                "status": o.status.value,
                "buyer_name": o.buyer_name,
                "receiver_name": o.receiver_name,
                "receiver_address": o.receiver_address,
                "total_amount": o.total_amount,
                "tracking_number": o.tracking_number,
                "ordered_at": o.ordered_at.isoformat(),
                "confirmed_at": o.confirmed_at.isoformat() if o.confirmed_at else None,
                "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
                "items": [
                    {
                        "product_name": item.channel_product_name,
                        "option_name": item.channel_option_name,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "total_price": item.total_price
                    }
                    for item in o.items
                ]
            }
            for o in orders
        ]
    }


@router.get("/pending")
async def get_pending_orders(session: AsyncSession = Depends(get_db)):
    """발송 대기 주문 목록"""
    result = await session.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED]))
        .order_by(Order.ordered_at.asc())
    )
    orders = result.scalars().all()
    
    return {
        "count": len(orders),
        "orders": [
            {
                "id": o.id,
                "channel": o.channel.value,
                "channel_order_id": o.channel_order_id,
                "status": o.status.value,
                "buyer_name": o.buyer_name,
                "receiver_name": o.receiver_name,
                "receiver_phone": o.receiver_phone,
                "receiver_address": o.receiver_address,
                "total_amount": o.total_amount,
                "buyer_memo": o.buyer_memo,
                "ordered_at": o.ordered_at.isoformat(),
                "items": [
                    {
                        "product_name": item.channel_product_name,
                        "option_name": item.channel_option_name,
                        "quantity": item.quantity
                    }
                    for item in o.items
                ]
            }
            for o in orders
        ]
    }


@router.get("/{order_id}")
async def get_order_detail(order_id: int, session: AsyncSession = Depends(get_db)):
    """주문 상세 조회"""
    result = await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다")
    
    return {
        "id": order.id,
        "channel": order.channel.value,
        "channel_order_id": order.channel_order_id,
        "status": order.status.value,
        "buyer_name": order.buyer_name,
        "buyer_phone": order.buyer_phone,
        "buyer_email": order.buyer_email,
        "receiver_name": order.receiver_name,
        "receiver_phone": order.receiver_phone,
        "receiver_address": order.receiver_address,
        "receiver_zipcode": order.receiver_zipcode,
        "total_amount": order.total_amount,
        "shipping_fee": order.shipping_fee,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
        "buyer_memo": order.buyer_memo,
        "seller_memo": order.seller_memo,
        "ordered_at": order.ordered_at.isoformat(),
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "items": [
            {
                "id": item.id,
                "channel_product_id": item.channel_product_id,
                "product_name": item.channel_product_name,
                "option_name": item.channel_option_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price
            }
            for item in order.items
        ]
    }


@router.post("/collect")
async def collect_orders():
    """신규 주문 수집 (수동 실행)"""
    from ..main import server
    orders = await server._collect_new_orders()
    
    return {
        "success": True,
        "collected": len(orders),
        "message": f"{len(orders)}건의 신규 주문을 수집했습니다"
    }


@router.post("/process-batch/{batch_number}")
async def process_batch(batch_number: int):
    """배치 처리 수동 실행"""
    if batch_number not in [1, 2]:
        raise HTTPException(status_code=400, detail="배치 번호는 1 또는 2여야 합니다")
    
    from ..main import server
    await server._run_batch_processing(batch_number)
    
    return {
        "success": True,
        "message": f"{batch_number}차 송장 처리를 완료했습니다"
    }


class UpdateMemoRequest(BaseModel):
    seller_memo: str


@router.patch("/{order_id}/memo")
async def update_order_memo(
    order_id: int,
    request: UpdateMemoRequest,
    session: AsyncSession = Depends(get_db)
):
    """주문 메모 업데이트"""
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다")
    
    order.seller_memo = request.seller_memo
    await session.commit()
    
    return {"success": True, "message": "메모가 업데이트되었습니다"}


@router.get("/stats/summary")
async def get_order_stats(
    period: str = Query("today", regex="^(today|week|month)$"),
    session: AsyncSession = Depends(get_db)
):
    """주문 통계"""
    if period == "today":
        start_date = date.today()
    elif period == "week":
        start_date = date.today() - timedelta(days=7)
    else:
        start_date = date.today() - timedelta(days=30)
    
    # 상태별 주문 수
    status_result = await session.execute(
        select(
            Order.status,
            func.count(Order.id).label('count')
        ).where(
            func.date(Order.ordered_at) >= start_date
        ).group_by(Order.status)
    )
    
    # 채널별 주문 수
    channel_result = await session.execute(
        select(
            Order.channel,
            func.count(Order.id).label('count'),
            func.sum(Order.total_amount).label('total')
        ).where(
            func.date(Order.ordered_at) >= start_date
        ).group_by(Order.channel)
    )
    
    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "by_status": {row.status.value: row.count for row in status_result},
        "by_channel": {
            row.channel.value: {"count": row.count, "total": row.total or 0}
            for row in channel_result
        }
    }
