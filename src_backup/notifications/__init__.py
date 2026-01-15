"""
알림 시스템
Telegram, Slack, Email 알림 발송
"""
import httpx
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class NotificationResult:
    """알림 발송 결과"""
    success: bool
    channel: str
    message: str
    error: Optional[str] = None


class TelegramNotifier:
    """텔레그램 알림"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.http_client = httpx.AsyncClient(timeout=10.0)
        self.logger = structlog.get_logger(notifier="telegram")
    
    async def send(self, message: str, parse_mode: str = "HTML") -> NotificationResult:
        """메시지 발송"""
        try:
            response = await self.http_client.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode
                }
            )
            
            if response.status_code == 200:
                self.logger.info("텔레그램 발송 성공")
                return NotificationResult(True, "telegram", message)
            else:
                error = response.text
                self.logger.error("텔레그램 발송 실패", error=error)
                return NotificationResult(False, "telegram", message, error)
                
        except Exception as e:
            self.logger.exception("텔레그램 발송 오류", error=str(e))
            return NotificationResult(False, "telegram", message, str(e))
    
    async def close(self):
        await self.http_client.aclose()


class SlackNotifier:
    """슬랙 알림"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.http_client = httpx.AsyncClient(timeout=10.0)
        self.logger = structlog.get_logger(notifier="slack")
    
    async def send(self, message: str, title: Optional[str] = None) -> NotificationResult:
        """메시지 발송"""
        try:
            payload = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message}
                    }
                ]
            }
            
            if title:
                payload["blocks"].insert(0, {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title}
                })
            
            response = await self.http_client.post(
                self.webhook_url,
                json=payload
            )
            
            if response.status_code == 200:
                self.logger.info("슬랙 발송 성공")
                return NotificationResult(True, "slack", message)
            else:
                error = response.text
                self.logger.error("슬랙 발송 실패", error=error)
                return NotificationResult(False, "slack", message, error)
                
        except Exception as e:
            self.logger.exception("슬랙 발송 오류", error=str(e))
            return NotificationResult(False, "slack", message, str(e))
    
    async def close(self):
        await self.http_client.aclose()


class EmailNotifier:
    """이메일 알림"""
    
    def __init__(self, host: str, port: int, user: str, password: str, from_addr: str, to_addr: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.logger = structlog.get_logger(notifier="email")
    
    async def send(self, subject: str, body: str, html: bool = False) -> NotificationResult:
        """메시지 발송"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = self.to_addr
            
            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))
            
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True
            )
            
            self.logger.info("이메일 발송 성공", subject=subject)
            return NotificationResult(True, "email", body)
            
        except Exception as e:
            self.logger.exception("이메일 발송 오류", error=str(e))
            return NotificationResult(False, "email", body, str(e))


class NotificationManager:
    """통합 알림 관리자"""
    
    def __init__(
        self,
        telegram: Optional[TelegramNotifier] = None,
        slack: Optional[SlackNotifier] = None,
        email: Optional[EmailNotifier] = None
    ):
        self.telegram = telegram
        self.slack = slack
        self.email = email
        self.logger = structlog.get_logger(component="notification_manager")
    
    async def notify_batch_complete(self, batch_number: int, results: dict):
        """배치 처리 완료 알림"""
        message = f"""
🚀 <b>{batch_number}차 송장 처리 완료</b>

📦 수집된 주문: {results.get('collected', 0)}건
✅ 발주 확인: {results.get('confirmed', 0)}건
🏷️ 송장 출력: {results.get('printed', 0)}건
❌ 오류: {results.get('errors', 0)}건

⏰ 처리 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await self._send_all(message)
    
    async def notify_low_stock(self, products: List[dict]):
        """재고 부족 알림"""
        if not products:
            return
        
        product_list = "\n".join([
            f"  • {p['name']}: {p['quantity']}개 (임계값: {p['threshold']})"
            for p in products
        ])
        
        message = f"""
⚠️ <b>재고 부족 경고</b>

다음 상품의 재고가 부족합니다:
{product_list}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await self._send_all(message)
    
    async def notify_new_claim(self, claim_type: str, order_id: str, reason: str, channel: str):
        """클레임 접수 알림"""
        type_emoji = {"return": "📦↩️", "exchange": "🔄", "cancel": "❌"}.get(claim_type, "📋")
        type_name = {"return": "반품", "exchange": "교환", "cancel": "취소"}.get(claim_type, claim_type)
        
        message = f"""
{type_emoji} <b>새로운 {type_name} 요청</b>

📍 채널: {channel.upper()}
📋 주문번호: {order_id}
📝 사유: {reason or '미기재'}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await self._send_all(message)
    
    async def notify_delivery_complete(self, order_id: str, tracking_number: str, receiver: str):
        """배송 완료 알림"""
        message = f"""
✅ <b>배송 완료</b>

📋 주문번호: {order_id}
🏷️ 송장번호: {tracking_number}
👤 수령인: {receiver}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await self._send_all(message)
    
    async def notify_error(self, context: str, error: str):
        """오류 알림"""
        message = f"""
🚨 <b>오류 발생</b>

📍 위치: {context}
❌ 오류: {error}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await self._send_all(message)
    
    async def _send_all(self, message: str):
        """모든 채널로 발송"""
        results = []
        
        if self.telegram:
            result = await self.telegram.send(message)
            results.append(result)
        
        if self.slack:
            # 슬랙은 HTML 대신 마크다운 형식으로 변환
            slack_message = message.replace("<b>", "*").replace("</b>", "*")
            result = await self.slack.send(slack_message)
            results.append(result)
        
        return results
    
    async def send_daily_report(self, report: dict):
        """일일 리포트 발송 (이메일)"""
        if not self.email:
            return
        
        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
<h2>📊 일일 판매 리포트 - {report['date']}</h2>

<h3>📦 주문 현황</h3>
<ul>
<li>총 주문: {report.get('total_orders', 0)}건</li>
<li>스마트스토어: {report.get('naver_orders', 0)}건</li>
<li>쿠팡: {report.get('coupang_orders', 0)}건</li>
</ul>

<h3>🚚 배송 현황</h3>
<ul>
<li>발송 완료: {report.get('shipped', 0)}건</li>
<li>배송 완료: {report.get('delivered', 0)}건</li>
</ul>

<h3>📋 클레임 현황</h3>
<ul>
<li>반품 요청: {report.get('returns', 0)}건</li>
<li>교환 요청: {report.get('exchanges', 0)}건</li>
<li>취소 요청: {report.get('cancels', 0)}건</li>
</ul>

<h3>💰 매출 현황</h3>
<ul>
<li>총 매출: {report.get('total_sales', 0):,.0f}원</li>
</ul>

<hr>
<p style="color: #888;">쇼핑몰 자동화 MCP 서버</p>
</body>
</html>
"""
        
        await self.email.send(
            subject=f"[쇼핑몰] 일일 리포트 - {report['date']}",
            body=html_body,
            html=True
        )
    
    async def close(self):
        """리소스 정리"""
        if self.telegram:
            await self.telegram.close()
        if self.slack:
            await self.slack.close()
