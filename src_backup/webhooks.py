"""
웹훅 모듈
외부 서비스에 이벤트 전달
"""
import httpx
import json
import hashlib
import hmac
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum
import structlog
import asyncio

logger = structlog.get_logger()

# 웹훅 설정 파일
WEBHOOK_FILE = Path("data/webhooks.json")


class WebhookEvent(str, Enum):
    """웹훅 이벤트 타입"""
    ORDER_NEW = "order.new"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_SHIPPED = "order.shipped"
    ORDER_DELIVERED = "order.delivered"
    STOCK_LOW = "stock.low"
    STOCK_UPDATE = "stock.update"
    CLAIM_NEW = "claim.new"
    BATCH_COMPLETE = "batch.complete"


@dataclass
class WebhookConfig:
    """웹훅 설정"""
    id: str
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_triggered: Optional[str] = None
    failure_count: int = 0


@dataclass
class WebhookDelivery:
    """웹훅 전송 결과"""
    success: bool
    webhook_id: str
    event: str
    status_code: Optional[int] = None
    response: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0


def load_webhooks() -> List[WebhookConfig]:
    """웹훅 설정 로드"""
    if WEBHOOK_FILE.exists():
        with open(WEBHOOK_FILE, "r") as f:
            data = json.load(f)
            return [WebhookConfig(**w) for w in data.get("webhooks", [])]
    return []


def save_webhooks(webhooks: List[WebhookConfig]):
    """웹훅 설정 저장"""
    WEBHOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WEBHOOK_FILE, "w") as f:
        json.dump(
            {"webhooks": [w.__dict__ for w in webhooks]},
            f,
            ensure_ascii=False,
            indent=2
        )


class WebhookManager:
    """웹훅 관리자"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.webhooks = load_webhooks()
    
    def add_webhook(
        self,
        name: str,
        url: str,
        events: List[str],
        secret: Optional[str] = None
    ) -> WebhookConfig:
        """웹훅 추가"""
        import uuid
        
        webhook = WebhookConfig(
            id=str(uuid.uuid4())[:8],
            name=name,
            url=url,
            events=events,
            secret=secret
        )
        
        self.webhooks.append(webhook)
        save_webhooks(self.webhooks)
        
        logger.info("웹훅 추가됨", name=name, url=url, events=events)
        return webhook
    
    def remove_webhook(self, webhook_id: str) -> bool:
        """웹훅 제거"""
        for i, w in enumerate(self.webhooks):
            if w.id == webhook_id:
                del self.webhooks[i]
                save_webhooks(self.webhooks)
                logger.info("웹훅 제거됨", webhook_id=webhook_id)
                return True
        return False
    
    def update_webhook(
        self,
        webhook_id: str,
        name: Optional[str] = None,
        url: Optional[str] = None,
        events: Optional[List[str]] = None,
        enabled: Optional[bool] = None
    ) -> Optional[WebhookConfig]:
        """웹훅 업데이트"""
        for webhook in self.webhooks:
            if webhook.id == webhook_id:
                if name is not None:
                    webhook.name = name
                if url is not None:
                    webhook.url = url
                if events is not None:
                    webhook.events = events
                if enabled is not None:
                    webhook.enabled = enabled
                
                save_webhooks(self.webhooks)
                return webhook
        return None
    
    def list_webhooks(self) -> List[WebhookConfig]:
        """웹훅 목록"""
        return self.webhooks
    
    def get_webhook(self, webhook_id: str) -> Optional[WebhookConfig]:
        """웹훅 조회"""
        for w in self.webhooks:
            if w.id == webhook_id:
                return w
        return None
    
    def _generate_signature(self, payload: str, secret: str) -> str:
        """HMAC 서명 생성"""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
    
    async def trigger(
        self,
        event: str,
        data: Dict[str, Any]
    ) -> List[WebhookDelivery]:
        """웹훅 트리거"""
        results = []
        
        # 해당 이벤트를 구독하는 웹훅 찾기
        target_webhooks = [
            w for w in self.webhooks
            if w.enabled and event in w.events
        ]
        
        if not target_webhooks:
            return results
        
        # 페이로드 생성
        payload = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        payload_json = json.dumps(payload, ensure_ascii=False)
        
        # 병렬로 웹훅 전송
        tasks = [
            self._send_webhook(webhook, event, payload_json)
            for webhook in target_webhooks
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 결과 처리
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(WebhookDelivery(
                    success=False,
                    webhook_id=target_webhooks[i].id,
                    event=event,
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _send_webhook(
        self,
        webhook: WebhookConfig,
        event: str,
        payload: str
    ) -> WebhookDelivery:
        """개별 웹훅 전송"""
        start_time = datetime.now()
        
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Event": event,
                "X-Webhook-Delivery-Id": f"{webhook.id}-{datetime.now().timestamp()}"
            }
            
            # 서명 추가
            if webhook.secret:
                signature = self._generate_signature(payload, webhook.secret)
                headers["X-Webhook-Signature"] = f"sha256={signature}"
            
            response = await self.client.post(
                webhook.url,
                content=payload,
                headers=headers
            )
            
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            # 성공 여부 판단 (2xx 상태 코드)
            success = 200 <= response.status_code < 300
            
            # 웹훅 상태 업데이트
            webhook.last_triggered = datetime.now().isoformat()
            if not success:
                webhook.failure_count += 1
            else:
                webhook.failure_count = 0
            save_webhooks(self.webhooks)
            
            logger.info(
                "웹훅 전송",
                webhook_id=webhook.id,
                event=event,
                success=success,
                status_code=response.status_code,
                duration_ms=duration
            )
            
            return WebhookDelivery(
                success=success,
                webhook_id=webhook.id,
                event=event,
                status_code=response.status_code,
                response=response.text[:500] if response.text else None,
                duration_ms=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            
            webhook.failure_count += 1
            save_webhooks(self.webhooks)
            
            logger.error(
                "웹훅 전송 실패",
                webhook_id=webhook.id,
                event=event,
                error=str(e)
            )
            
            return WebhookDelivery(
                success=False,
                webhook_id=webhook.id,
                event=event,
                error=str(e),
                duration_ms=duration
            )
    
    async def test_webhook(self, webhook_id: str) -> WebhookDelivery:
        """웹훅 테스트"""
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return WebhookDelivery(
                success=False,
                webhook_id=webhook_id,
                event="test",
                error="웹훅을 찾을 수 없습니다"
            )
        
        test_payload = json.dumps({
            "event": "test",
            "timestamp": datetime.now().isoformat(),
            "data": {"message": "웹훅 테스트입니다"}
        })
        
        return await self._send_webhook(webhook, "test", test_payload)
    
    async def close(self):
        """클라이언트 종료"""
        await self.client.aclose()


# 전역 웹훅 매니저
webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """웹훅 매니저 싱글톤"""
    global webhook_manager
    if webhook_manager is None:
        webhook_manager = WebhookManager()
    return webhook_manager


async def trigger_webhook(event: str, data: Dict[str, Any]):
    """편의 함수: 웹훅 트리거"""
    manager = get_webhook_manager()
    return await manager.trigger(event, data)
