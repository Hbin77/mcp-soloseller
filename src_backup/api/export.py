"""
내보내기 API
엑셀, CSV, PDF 내보내기
"""
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, date, timedelta
from typing import Optional
import io

from ..database import Order, Product, OrderStatus
from ..utils.export import ExcelExporter, CSVExporter, InvoicePDFGenerator, BackupManager

router = APIRouter(prefix="/export", tags=["Export"])


async def get_db():
    from ..main import server
    async with server.db.async_session() as session:
        yield session


@router.get("/orders/excel")
async def export_orders_excel(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """주문 목록 엑셀 내보내기"""
    query = select(Order).options(selectinload(Order.items))
    
    if status:
        query = query.where(Order.status == OrderStatus(status))
    if date_from:
        query = query.where(Order.ordered_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.where(Order.ordered_at <= datetime.fromisoformat(date_to + "T23:59:59"))
    
    query = query.order_by(Order.ordered_at.desc())
    result = await session.execute(query)
    orders = result.scalars().all()
    
    orders_data = [
        {
            "channel": o.channel.value,
            "channel_order_id": o.channel_order_id,
            "buyer_name": o.buyer_name,
            "receiver_name": o.receiver_name,
            "receiver_phone": o.receiver_phone,
            "receiver_address": o.receiver_address,
            "total_amount": o.total_amount,
            "status": o.status.value,
            "tracking_number": o.tracking_number,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else ""
        }
        for o in orders
    ]
    
    export_result = ExcelExporter.export_orders(orders_data)
    
    if not export_result.success:
        return {"error": export_result.error}
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )


@router.get("/orders/csv")
async def export_orders_csv(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """주문 목록 CSV 내보내기"""
    query = select(Order).options(selectinload(Order.items))
    
    if status:
        query = query.where(Order.status == OrderStatus(status))
    
    query = query.order_by(Order.ordered_at.desc())
    result = await session.execute(query)
    orders = result.scalars().all()
    
    orders_data = [
        {
            "channel": o.channel.value,
            "channel_order_id": o.channel_order_id,
            "buyer_name": o.buyer_name,
            "receiver_name": o.receiver_name,
            "receiver_phone": o.receiver_phone,
            "receiver_address": o.receiver_address,
            "total_amount": o.total_amount,
            "status": o.status.value,
            "tracking_number": o.tracking_number,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else ""
        }
        for o in orders
    ]
    
    export_result = CSVExporter.export_orders(orders_data)
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )


@router.get("/products/excel")
async def export_products_excel(session: AsyncSession = Depends(get_db)):
    """상품 목록 엑셀 내보내기"""
    result = await session.execute(
        select(Product).where(Product.is_active == True).order_by(Product.name)
    )
    products = result.scalars().all()
    
    products_data = [
        {
            "sku": p.sku,
            "name": p.name,
            "stock_quantity": p.stock_quantity,
            "stock_alert_threshold": p.stock_alert_threshold,
            "price": p.price,
            "naver_product_id": p.naver_product_id,
            "coupang_product_id": p.coupang_product_id,
            "is_active": p.is_active
        }
        for p in products
    ]
    
    export_result = ExcelExporter.export_products(products_data)
    
    if not export_result.success:
        return {"error": export_result.error}
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )


@router.get("/products/csv")
async def export_products_csv(session: AsyncSession = Depends(get_db)):
    """상품 목록 CSV 내보내기"""
    result = await session.execute(
        select(Product).where(Product.is_active == True).order_by(Product.name)
    )
    products = result.scalars().all()
    
    products_data = [
        {
            "sku": p.sku,
            "name": p.name,
            "stock_quantity": p.stock_quantity,
            "stock_alert_threshold": p.stock_alert_threshold,
            "price": p.price,
            "naver_product_id": p.naver_product_id,
            "coupang_product_id": p.coupang_product_id
        }
        for p in products
    ]
    
    export_result = CSVExporter.export_products(products_data)
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )


@router.get("/invoice/{order_id}/pdf")
async def export_invoice_pdf(order_id: int, session: AsyncSession = Depends(get_db)):
    """송장 라벨 PDF 생성"""
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        return {"error": "주문을 찾을 수 없습니다"}
    
    if not order.tracking_number:
        return {"error": "송장번호가 없습니다"}
    
    order_data = {
        "channel": order.channel.value,
        "channel_order_id": order.channel_order_id,
        "receiver_name": order.receiver_name,
        "receiver_phone": order.receiver_phone,
        "receiver_address": order.receiver_address,
        "receiver_zipcode": order.receiver_zipcode,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
        "buyer_memo": order.buyer_memo
    }
    
    export_result = InvoicePDFGenerator.generate_invoice_label(order_data)
    
    if not export_result.success:
        return {"error": export_result.error}
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )


@router.get("/backup")
async def create_backup(session: AsyncSession = Depends(get_db)):
    """전체 데이터 백업"""
    # 상품 데이터
    products_result = await session.execute(select(Product))
    products = [
        {
            "sku": p.sku,
            "name": p.name,
            "stock_quantity": p.stock_quantity,
            "stock_alert_threshold": p.stock_alert_threshold,
            "price": p.price,
            "naver_product_id": p.naver_product_id,
            "coupang_product_id": p.coupang_product_id,
            "is_active": p.is_active
        }
        for p in products_result.scalars().all()
    ]
    
    # 최근 주문 (30일)
    orders_result = await session.execute(
        select(Order).where(
            Order.ordered_at >= datetime.now() - timedelta(days=30)
        )
    )
    orders = [
        {
            "channel": o.channel.value,
            "channel_order_id": o.channel_order_id,
            "status": o.status.value,
            "buyer_name": o.buyer_name,
            "receiver_name": o.receiver_name,
            "total_amount": o.total_amount,
            "tracking_number": o.tracking_number,
            "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None
        }
        for o in orders_result.scalars().all()
    ]
    
    backup_data = {
        "products": products,
        "orders": orders
    }
    
    export_result = BackupManager.create_backup(backup_data)
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )


@router.get("/daily-report/excel")
async def export_daily_report(
    report_date: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """일일 리포트 엑셀 내보내기"""
    from ..api.dashboard import get_db
    
    target_date = date.fromisoformat(report_date) if report_date else date.today()
    
    # 간단한 리포트 데이터 생성
    report = {
        "date": target_date.isoformat(),
        "orders": {"total": 0, "naver": 0, "coupang": 0},
        "sales": {"total": 0, "naver": 0, "coupang": 0},
        "shipping": {"shipped": 0, "delivered": 0}
    }
    
    export_result = ExcelExporter.export_daily_report(report)
    
    if not export_result.success:
        return {"error": export_result.error}
    
    return Response(
        content=export_result.content,
        media_type=export_result.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={export_result.filename}"
        }
    )
