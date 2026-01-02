"""
클레임(반품/교환/취소) 관리 API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional

from ..database import Claim, Order, ClaimType, ClaimStatus, ChannelType

router = APIRouter(prefix="/claims", tags=["Claims"])


async def get_db():
    from ..main import server
    async with server.db.async_session() as session:
        yield session


@router.get("")
async def list_claims(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    claim_type: Optional[str] = None,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    """클레임 목록 조회"""
    query = select(Claim)
    
    if claim_type:
        query = query.where(Claim.claim_type == ClaimType(claim_type))
    if status:
        query = query.where(Claim.status == ClaimStatus(status))
    if channel:
        query = query.where(Claim.channel == ChannelType(channel))
    
    # 전체 개수
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar()
    
    # 페이지네이션
    query = query.order_by(Claim.requested_at.desc()).offset((page - 1) * limit).limit(limit)
    result = await session.execute(query)
    claims = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "claims": [
            {
                "id": c.id,
                "channel": c.channel.value,
                "channel_claim_id": c.channel_claim_id,
                "order_id": c.order_id,
                "claim_type": c.claim_type.value,
                "status": c.status.value,
                "reason": c.reason,
                "requested_at": c.requested_at.isoformat(),
                "processed_at": c.processed_at.isoformat() if c.processed_at else None
            }
            for c in claims
        ]
    }


@router.get("/sync")
async def sync_claims():
    """채널에서 클레임 동기화"""
    from ..main import server
    
    all_claims = []
    
    # 네이버 클레임 수집
    if server.naver_client:
        try:
            claims = await server.naver_client.get_claims()
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
        except Exception as e:
            pass
    
    # 쿠팡 클레임 수집
    if server.coupang_client:
        try:
            claims = await server.coupang_client.get_claims()
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
        except Exception as e:
            pass
    
    return {
        "success": True,
        "count": len(all_claims),
        "claims": all_claims
    }


@router.get("/stats")
async def get_claim_stats(session: AsyncSession = Depends(get_db)):
    """클레임 통계"""
    # 타입별 통계
    type_result = await session.execute(
        select(
            Claim.claim_type,
            func.count(Claim.id).label('count')
        ).group_by(Claim.claim_type)
    )
    
    # 상태별 통계
    status_result = await session.execute(
        select(
            Claim.status,
            func.count(Claim.id).label('count')
        ).group_by(Claim.status)
    )
    
    return {
        "by_type": {row.claim_type.value: row.count for row in type_result},
        "by_status": {row.status.value: row.count for row in status_result}
    }


@router.get("/{claim_id}")
async def get_claim_detail(claim_id: int, session: AsyncSession = Depends(get_db)):
    """클레임 상세 조회"""
    result = await session.execute(
        select(Claim).where(Claim.id == claim_id)
    )
    claim = result.scalar_one_or_none()
    
    if not claim:
        raise HTTPException(status_code=404, detail="클레임을 찾을 수 없습니다")
    
    # 연결된 주문 정보
    order_result = await session.execute(
        select(Order).where(Order.id == claim.order_id)
    )
    order = order_result.scalar_one_or_none()
    
    return {
        "id": claim.id,
        "channel": claim.channel.value,
        "channel_claim_id": claim.channel_claim_id,
        "claim_type": claim.claim_type.value,
        "status": claim.status.value,
        "reason": claim.reason,
        "requested_at": claim.requested_at.isoformat(),
        "processed_at": claim.processed_at.isoformat() if claim.processed_at else None,
        "order": {
            "id": order.id,
            "channel_order_id": order.channel_order_id,
            "buyer_name": order.buyer_name,
            "total_amount": order.total_amount
        } if order else None
    }
