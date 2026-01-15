"""
웹훅 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional, List

from ..webhooks import get_webhook_manager, WebhookEvent

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None


@router.get("")
async def list_webhooks():
    """웹훅 목록"""
    manager = get_webhook_manager()
    webhooks = manager.list_webhooks()
    
    return {
        "webhooks": [
            {
                "id": w.id,
                "name": w.name,
                "url": w.url,
                "events": w.events,
                "enabled": w.enabled,
                "created_at": w.created_at,
                "last_triggered": w.last_triggered,
                "failure_count": w.failure_count
            }
            for w in webhooks
        ]
    }


@router.get("/events")
async def list_events():
    """사용 가능한 웹훅 이벤트 목록"""
    return {
        "events": [
            {"code": e.value, "description": _get_event_description(e)}
            for e in WebhookEvent
        ]
    }


def _get_event_description(event: WebhookEvent) -> str:
    """이벤트 설명"""
    descriptions = {
        WebhookEvent.ORDER_NEW: "새로운 주문이 수집되었을 때",
        WebhookEvent.ORDER_CONFIRMED: "주문이 확인되었을 때",
        WebhookEvent.ORDER_SHIPPED: "주문이 발송되었을 때",
        WebhookEvent.ORDER_DELIVERED: "주문이 배송 완료되었을 때",
        WebhookEvent.STOCK_LOW: "재고가 임계값 이하로 떨어졌을 때",
        WebhookEvent.STOCK_UPDATE: "재고가 업데이트되었을 때",
        WebhookEvent.CLAIM_NEW: "새로운 클레임이 접수되었을 때",
        WebhookEvent.BATCH_COMPLETE: "배치 처리가 완료되었을 때"
    }
    return descriptions.get(event, "")


@router.post("")
async def create_webhook(webhook: WebhookCreate):
    """웹훅 생성"""
    manager = get_webhook_manager()
    
    # 이벤트 유효성 검사
    valid_events = [e.value for e in WebhookEvent]
    for event in webhook.events:
        if event not in valid_events:
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 이벤트: {event}. 사용 가능: {valid_events}"
            )
    
    result = manager.add_webhook(
        name=webhook.name,
        url=webhook.url,
        events=webhook.events,
        secret=webhook.secret
    )
    
    return {
        "success": True,
        "webhook": {
            "id": result.id,
            "name": result.name,
            "url": result.url,
            "events": result.events
        }
    }


@router.get("/{webhook_id}")
async def get_webhook(webhook_id: str):
    """웹훅 상세"""
    manager = get_webhook_manager()
    webhook = manager.get_webhook(webhook_id)
    
    if not webhook:
        raise HTTPException(status_code=404, detail="웹훅을 찾을 수 없습니다")
    
    return {
        "id": webhook.id,
        "name": webhook.name,
        "url": webhook.url,
        "events": webhook.events,
        "enabled": webhook.enabled,
        "created_at": webhook.created_at,
        "last_triggered": webhook.last_triggered,
        "failure_count": webhook.failure_count
    }


@router.patch("/{webhook_id}")
async def update_webhook(webhook_id: str, update: WebhookUpdate):
    """웹훅 수정"""
    manager = get_webhook_manager()
    
    result = manager.update_webhook(
        webhook_id=webhook_id,
        name=update.name,
        url=update.url,
        events=update.events,
        enabled=update.enabled
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="웹훅을 찾을 수 없습니다")
    
    return {"success": True, "message": "웹훅이 수정되었습니다"}


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """웹훅 삭제"""
    manager = get_webhook_manager()
    
    if not manager.remove_webhook(webhook_id):
        raise HTTPException(status_code=404, detail="웹훅을 찾을 수 없습니다")
    
    return {"success": True, "message": "웹훅이 삭제되었습니다"}


@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """웹훅 테스트"""
    manager = get_webhook_manager()
    
    result = await manager.test_webhook(webhook_id)
    
    return {
        "success": result.success,
        "status_code": result.status_code,
        "response": result.response,
        "error": result.error,
        "duration_ms": result.duration_ms
    }
