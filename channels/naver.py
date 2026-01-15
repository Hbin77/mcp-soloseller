"""네이버 스마트스토어 API 클라이언트"""
import httpx
import hmac
import hashlib
import base64
import time
import structlog
from typing import Optional, List
from datetime import datetime, timedelta

from . import ChannelOrder, ChannelOrderItem

logger = structlog.get_logger()


class NaverClient:
    """네이버 커머스 API 클라이언트"""

    BASE_URL = "https://api.commerce.naver.com/external"

    def __init__(self, client_id: str, client_secret: str, seller_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.seller_id = seller_id
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.http_client = httpx.AsyncClient(timeout=30.0)

    def _generate_signature(self, timestamp: str) -> str:
        """HMAC 서명 생성"""
        message = f"{self.client_id}_{timestamp}"
        signature = hmac.new(
            self.client_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    async def authenticate(self) -> bool:
        """OAuth 토큰 발급"""
        try:
            if self.access_token and self.token_expires_at:
                if datetime.now() < self.token_expires_at - timedelta(minutes=5):
                    return True

            timestamp = str(int(time.time() * 1000))
            signature = self._generate_signature(timestamp)

            response = await self.http_client.post(
                f"{self.BASE_URL}/v1/oauth2/token",
                data={
                    "client_id": self.client_id,
                    "timestamp": timestamp,
                    "client_secret_sign": signature,
                    "grant_type": "client_credentials",
                    "type": "SELF"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                logger.info("네이버 인증 성공")
                return True
            else:
                logger.error("네이버 인증 실패", status=response.status_code)
                return False

        except Exception as e:
            logger.exception("네이버 인증 오류", error=str(e))
            return False

    def _get_headers(self) -> dict:
        """API 요청 헤더"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    async def get_new_orders(self, days: int = 7) -> List[dict]:
        """신규 주문 조회"""
        if not await self.authenticate():
            return []

        try:
            params = {
                "orderStatus": "PAYED",
                "from": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
                "to": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "limitCount": 100
            }

            response = await self.http_client.get(
                f"{self.BASE_URL}/v1/pay-order/seller/orders",
                params=params,
                headers=self._get_headers()
            )

            if response.status_code != 200:
                logger.error("주문 조회 실패", status=response.status_code)
                return []

            data = response.json()
            orders = []

            for order_data in data.get("data", []):
                order = self._parse_order(order_data)
                if order:
                    orders.append(order.to_dict())

            logger.info("네이버 주문 조회 완료", count=len(orders))
            return orders

        except Exception as e:
            logger.exception("주문 조회 오류", error=str(e))
            return []

    def _parse_order(self, data: dict) -> Optional[ChannelOrder]:
        """주문 데이터 파싱"""
        try:
            items = []
            for product in data.get("productOrderInfos", []):
                item = ChannelOrderItem(
                    product_id=str(product.get("productId", "")),
                    product_name=product.get("productName", ""),
                    option_name=product.get("optionContent"),
                    quantity=product.get("quantity", 1),
                    unit_price=product.get("unitPrice", 0),
                    total_price=product.get("totalPaymentAmount", 0)
                )
                items.append(item)

            order_info = data.get("generalPaymentInfo", {})
            delivery_info = data.get("deliveryInfo", {})

            ordered_at_str = data.get("orderDate", "")
            try:
                ordered_at = datetime.fromisoformat(ordered_at_str.replace("Z", "+00:00"))
            except Exception:
                ordered_at = datetime.now()

            return ChannelOrder(
                channel="naver",
                order_id=data.get("orderId", ""),
                status=data.get("orderStatus", ""),
                buyer_name=order_info.get("ordererName", ""),
                buyer_phone=order_info.get("ordererTel"),
                buyer_email=order_info.get("ordererEmail"),
                receiver_name=delivery_info.get("name", ""),
                receiver_phone=delivery_info.get("tel1", ""),
                receiver_address=f"{delivery_info.get('baseAddress', '')} {delivery_info.get('detailAddress', '')}".strip(),
                receiver_zipcode=delivery_info.get("zipCode"),
                total_amount=order_info.get("totalPaymentAmount", 0),
                shipping_fee=order_info.get("deliveryFee", 0),
                buyer_memo=delivery_info.get("deliveryMemo"),
                ordered_at=ordered_at,
                items=items
            )
        except Exception as e:
            logger.error("주문 파싱 오류", error=str(e))
            return None

    async def register_invoice(
        self,
        order_id: str,
        tracking_number: str,
        carrier_code: str = "CJGLS"
    ) -> bool:
        """송장 등록"""
        if not await self.authenticate():
            return False

        try:
            response = await self.http_client.post(
                f"{self.BASE_URL}/v1/pay-order/seller/orders/{order_id}/ship",
                headers=self._get_headers(),
                json={
                    "deliveryCompanyCode": carrier_code,
                    "trackingNumber": tracking_number
                }
            )

            if response.status_code in [200, 201]:
                logger.info("송장 등록 완료", order_id=order_id, tracking_number=tracking_number)
                return True
            else:
                logger.error("송장 등록 실패", order_id=order_id, status=response.status_code)
                return False

        except Exception as e:
            logger.exception("송장 등록 오류", error=str(e))
            return False

    async def close(self):
        """리소스 정리"""
        await self.http_client.aclose()
