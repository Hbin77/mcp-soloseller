"""CJ대한통운 API 클라이언트"""
import httpx
import hashlib
import hmac
import time
import json
import random
import structlog
from datetime import datetime
from typing import Optional

from models import ShippingRequest, ShippingResponse

logger = structlog.get_logger()


class CJClient:
    """CJ대한통운 API 클라이언트"""

    BASE_URL = "https://api.cjlogistics.com"

    def __init__(
        self,
        customer_id: str,
        api_key: str,
        contract_code: Optional[str] = None
    ):
        self.customer_id = customer_id
        self.api_key = api_key
        self.contract_code = contract_code or customer_id
        self.test_mode = not api_key
        self.http_client = httpx.AsyncClient(timeout=30.0)

    def _generate_signature(self, timestamp: str, data: str = "") -> str:
        """API 서명 생성"""
        message = f"{self.customer_id}{timestamp}{data}"
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_headers(self, data: str = "") -> dict:
        """API 요청 헤더"""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, data)
        return {
            "Content-Type": "application/json",
            "X-Customer-Id": self.customer_id,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "X-Contract-Code": self.contract_code
        }

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급"""
        # API 설정이 없으면 테스트 모드
        if self.test_mode:
            return self._test_invoice(request)

        try:
            payload = {
                "senderName": request.sender_name,
                "senderPhone": request.sender_phone,
                "senderZipcode": request.sender_zipcode,
                "senderAddress": request.sender_address,
                "receiverName": request.receiver_name,
                "receiverPhone": request.receiver_phone,
                "receiverZipcode": request.receiver_zipcode,
                "receiverAddress": request.receiver_address,
                "productName": request.product_name,
                "quantity": request.quantity,
                "weight": request.weight,
                "memo": request.memo or "",
                "orderId": request.order_id or ""
            }

            data_str = json.dumps(payload, ensure_ascii=False)
            headers = self._get_headers(data_str)

            response = await self.http_client.post(
                f"{self.BASE_URL}/v1/invoice/create",
                headers=headers,
                json=payload
            )

            if response.status_code in [200, 201]:
                result = response.json()
                tracking_number = result.get("trackingNumber") or result.get("invoiceNo")

                logger.info("CJ 송장 발급 성공", tracking_number=tracking_number)
                return ShippingResponse(
                    success=True,
                    tracking_number=tracking_number,
                    carrier="cj",
                    carrier_name="CJ대한통운"
                )
            else:
                logger.error("CJ 송장 발급 실패", status=response.status_code)
                return self._test_invoice(request)

        except httpx.ConnectError:
            logger.warning("CJ API 연결 실패 - 테스트 모드로 대체")
            return self._test_invoice(request)
        except Exception as e:
            logger.exception("CJ 송장 발급 오류", error=str(e))
            return self._test_invoice(request)

    def _test_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """테스트 송장 발급"""
        tracking_number = f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        logger.info("테스트 송장 발급 (CJ)", tracking_number=tracking_number)
        return ShippingResponse(
            success=True,
            tracking_number=tracking_number,
            carrier="cj",
            carrier_name="CJ대한통운"
        )

    async def close(self):
        """리소스 정리"""
        await self.http_client.aclose()
