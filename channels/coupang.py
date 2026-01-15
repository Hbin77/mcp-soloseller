"""쿠팡 WING API 클라이언트"""
import httpx
import hmac
import hashlib
import time
import structlog
from typing import Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlencode

from . import ChannelOrder, ChannelOrderItem

logger = structlog.get_logger()


class CoupangClient:
    """쿠팡 WING API 클라이언트"""

    BASE_URL = "https://api-gateway.coupang.com"

    def __init__(self, vendor_id: str, access_key: str, secret_key: str):
        self.vendor_id = vendor_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.http_client = httpx.AsyncClient(timeout=30.0)

    def _generate_signature(self, method: str, path: str, query_string: str = "") -> dict:
        """HMAC-SHA256 서명 생성"""
        datetime_str = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())

        message = datetime_str + method + path
        if query_string:
            message += "?" + query_string

        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        authorization = f"CEA algorithm=HmacSHA256, access-key={self.access_key}, " \
                       f"signed-date={datetime_str}, signature={signature}"

        return {
            "Authorization": authorization,
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-By": self.vendor_id
        }

    async def get_new_orders(self, days: int = 7) -> List[dict]:
        """신규 주문 조회"""
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets"
            params = {
                "createdAtFrom": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
                "createdAtTo": datetime.now().strftime("%Y-%m-%d"),
                "status": "ACCEPT"
            }
            query_string = urlencode(params)
            headers = self._generate_signature("GET", path, query_string)

            response = await self.http_client.get(
                f"{self.BASE_URL}{path}",
                params=params,
                headers=headers
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

            logger.info("쿠팡 주문 조회 완료", count=len(orders))
            return orders

        except Exception as e:
            logger.exception("주문 조회 오류", error=str(e))
            return []

    def _parse_order(self, data: dict) -> Optional[ChannelOrder]:
        """주문 데이터 파싱"""
        try:
            items = []
            for product in data.get("orderItems", []):
                item = ChannelOrderItem(
                    product_id=str(product.get("vendorItemId", "")),
                    product_name=product.get("vendorItemName", ""),
                    option_name=product.get("sellerProductItemName"),
                    quantity=product.get("shippingCount", 1),
                    unit_price=product.get("orderPrice", 0),
                    total_price=product.get("orderPrice", 0) * product.get("shippingCount", 1)
                )
                items.append(item)

            receiver = data.get("receiver", {})
            orderer = data.get("orderer", {})

            ordered_at_str = data.get("orderedAt", "")
            try:
                ordered_at = datetime.fromisoformat(ordered_at_str.replace("Z", "+00:00"))
            except Exception:
                ordered_at = datetime.now()

            return ChannelOrder(
                channel="coupang",
                order_id=str(data.get("shipmentBoxId", "")),
                status=data.get("status", ""),
                buyer_name=orderer.get("name", ""),
                buyer_phone=orderer.get("phone"),
                buyer_email=orderer.get("email"),
                receiver_name=receiver.get("name", ""),
                receiver_phone=receiver.get("phone", ""),
                receiver_address=f"{receiver.get('addr1', '')} {receiver.get('addr2', '')}".strip(),
                receiver_zipcode=receiver.get("postCode"),
                total_amount=data.get("totalPaymentPrice", 0),
                shipping_fee=data.get("shippingPrice", 0),
                buyer_memo=data.get("parcelPrintMessage"),
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
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets/{order_id}/invoices"
            headers = self._generate_signature("POST", path)

            response = await self.http_client.post(
                f"{self.BASE_URL}{path}",
                headers=headers,
                json={
                    "vendorId": self.vendor_id,
                    "shipmentBoxId": int(order_id),
                    "deliveryCompanyCode": carrier_code,
                    "invoiceNumber": tracking_number
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
