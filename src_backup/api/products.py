"""
상품/재고 관리 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from ..database import Product, StockHistory, StockChangeReason

router = APIRouter(prefix="/products", tags=["Products"])


async def get_db():
    from ..main import server
    async with server.db.async_session() as session:
        yield session


class ProductCreate(BaseModel):
    sku: str
    name: str
    stock_quantity: int = 0
    stock_alert_threshold: int = 5
    price: float = 0
    naver_product_id: Optional[str] = None
    coupang_product_id: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    stock_alert_threshold: Optional[int] = None
    price: Optional[float] = None
    naver_product_id: Optional[str] = None
    coupang_product_id: Optional[str] = None
    is_active: Optional[bool] = None


class StockUpdate(BaseModel):
    quantity: int
    reason: str  # incoming, adjustment
    memo: Optional[str] = None


@router.get("")
async def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    low_stock_only: bool = False,
    session: AsyncSession = Depends(get_db)
):
    """상품 목록 조회"""
    query = select(Product).where(Product.is_active == True)
    
    if search:
        query = query.where(
            Product.sku.contains(search) | Product.name.contains(search)
        )
    
    if low_stock_only:
        query = query.where(Product.stock_quantity <= Product.stock_alert_threshold)
    
    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar()
    
    # 페이지네이션
    query = query.order_by(Product.name).offset((page - 1) * limit).limit(limit)
    result = await session.execute(query)
    products = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "products": [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "stock_quantity": p.stock_quantity,
                "stock_alert_threshold": p.stock_alert_threshold,
                "is_low_stock": p.stock_quantity <= p.stock_alert_threshold,
                "price": p.price,
                "naver_product_id": p.naver_product_id,
                "coupang_product_id": p.coupang_product_id,
                "created_at": p.created_at.isoformat()
            }
            for p in products
        ]
    }


@router.get("/low-stock")
async def get_low_stock_products(session: AsyncSession = Depends(get_db)):
    """재고 부족 상품 목록"""
    result = await session.execute(
        select(Product).where(
            Product.stock_quantity <= Product.stock_alert_threshold,
            Product.is_active == True
        ).order_by(Product.stock_quantity)
    )
    products = result.scalars().all()
    
    return {
        "count": len(products),
        "products": [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "stock_quantity": p.stock_quantity,
                "stock_alert_threshold": p.stock_alert_threshold
            }
            for p in products
        ]
    }


@router.post("")
async def create_product(
    product: ProductCreate,
    session: AsyncSession = Depends(get_db)
):
    """상품 등록"""
    # SKU 중복 체크
    existing = await session.execute(
        select(Product).where(Product.sku == product.sku)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 존재하는 SKU입니다")
    
    new_product = Product(
        sku=product.sku,
        name=product.name,
        stock_quantity=product.stock_quantity,
        stock_alert_threshold=product.stock_alert_threshold,
        price=product.price,
        naver_product_id=product.naver_product_id,
        coupang_product_id=product.coupang_product_id
    )
    session.add(new_product)
    await session.commit()
    await session.refresh(new_product)
    
    return {
        "success": True,
        "product": {
            "id": new_product.id,
            "sku": new_product.sku,
            "name": new_product.name
        }
    }


@router.get("/{product_id}")
async def get_product(product_id: int, session: AsyncSession = Depends(get_db)):
    """상품 상세 조회"""
    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "stock_quantity": product.stock_quantity,
        "stock_alert_threshold": product.stock_alert_threshold,
        "is_low_stock": product.stock_quantity <= product.stock_alert_threshold,
        "price": product.price,
        "naver_product_id": product.naver_product_id,
        "coupang_product_id": product.coupang_product_id,
        "is_active": product.is_active,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat()
    }


@router.patch("/{product_id}")
async def update_product(
    product_id: int,
    update: ProductUpdate,
    session: AsyncSession = Depends(get_db)
):
    """상품 정보 수정"""
    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    
    await session.commit()
    
    return {"success": True, "message": "상품이 수정되었습니다"}


@router.delete("/{product_id}")
async def delete_product(product_id: int, session: AsyncSession = Depends(get_db)):
    """상품 삭제 (비활성화)"""
    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    product.is_active = False
    await session.commit()
    
    return {"success": True, "message": "상품이 삭제되었습니다"}


@router.post("/{product_id}/stock")
async def update_stock(
    product_id: int,
    update: StockUpdate,
    session: AsyncSession = Depends(get_db)
):
    """재고 업데이트"""
    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    
    before = product.stock_quantity
    product.stock_quantity += update.quantity
    
    if product.stock_quantity < 0:
        raise HTTPException(status_code=400, detail="재고가 0 미만이 될 수 없습니다")
    
    # 재고 이력 저장
    history = StockHistory(
        product_id=product.id,
        quantity_before=before,
        quantity_change=update.quantity,
        quantity_after=product.stock_quantity,
        reason=StockChangeReason(update.reason),
        memo=update.memo
    )
    session.add(history)
    await session.commit()
    
    return {
        "success": True,
        "stock": {
            "before": before,
            "change": update.quantity,
            "after": product.stock_quantity
        }
    }


@router.get("/{product_id}/stock-history")
async def get_stock_history(
    product_id: int,
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db)
):
    """재고 변동 이력"""
    result = await session.execute(
        select(StockHistory)
        .where(StockHistory.product_id == product_id)
        .order_by(StockHistory.created_at.desc())
        .limit(limit)
    )
    history = result.scalars().all()
    
    return {
        "history": [
            {
                "id": h.id,
                "quantity_before": h.quantity_before,
                "quantity_change": h.quantity_change,
                "quantity_after": h.quantity_after,
                "reason": h.reason.value,
                "memo": h.memo,
                "reference_id": h.reference_id,
                "created_at": h.created_at.isoformat()
            }
            for h in history
        ]
    }


@router.post("/sync-channels")
async def sync_stock_all_channels():
    """모든 채널 재고 동기화"""
    from ..main import server
    
    results = {"naver": 0, "coupang": 0, "errors": []}
    
    async with server.db.async_session() as session:
        result = await session.execute(
            select(Product).where(Product.is_active == True)
        )
        products = result.scalars().all()
        
        for product in products:
            # 네이버 동기화
            if product.naver_product_id and server.naver_client:
                try:
                    success = await server.naver_client.update_stock(
                        product.naver_product_id,
                        product.stock_quantity
                    )
                    if success:
                        results["naver"] += 1
                except Exception as e:
                    results["errors"].append(f"네이버 {product.sku}: {str(e)}")
            
            # 쿠팡 동기화
            if product.coupang_product_id and server.coupang_client:
                try:
                    success = await server.coupang_client.update_stock(
                        product.coupang_product_id,
                        product.stock_quantity
                    )
                    if success:
                        results["coupang"] += 1
                except Exception as e:
                    results["errors"].append(f"쿠팡 {product.sku}: {str(e)}")
    
    return {
        "success": True,
        "results": results
    }


@router.post("/import")
async def import_products(
    products: List[ProductCreate],
    session: AsyncSession = Depends(get_db)
):
    """상품 일괄 등록"""
    created = 0
    skipped = 0
    errors = []
    
    for product_data in products:
        try:
            # SKU 중복 체크
            existing = await session.execute(
                select(Product).where(Product.sku == product_data.sku)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            
            new_product = Product(
                sku=product_data.sku,
                name=product_data.name,
                stock_quantity=product_data.stock_quantity,
                stock_alert_threshold=product_data.stock_alert_threshold,
                price=product_data.price,
                naver_product_id=product_data.naver_product_id,
                coupang_product_id=product_data.coupang_product_id
            )
            session.add(new_product)
            created += 1
        except Exception as e:
            errors.append(f"{product_data.sku}: {str(e)}")
    
    await session.commit()
    
    return {
        "success": True,
        "created": created,
        "skipped": skipped,
        "errors": errors
    }
