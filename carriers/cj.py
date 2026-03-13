"""CJ대한통운 API 클라이언트

NOTE: CJ대한통운 API는 비공개 B2B API입니다.
아래 엔드포인트와 인증 방식은 추정값이며, 실제 API Portal에서
스펙을 확인한 후 수정이 필요합니다.

실제 연동 시: https://openapi.cjlogistics.com/ 에서 API 문서 확인
"""
import httpx
import hashlib
import hmac
import time
import json
import os
import secrets
from datetime import datetime
from typing import Optional

from models import ShippingRequest, ShippingResponse


class CJClient:
    """CJ대한통운 API 클라이언트"""

    # NOTE: 실제 API URL은 CJ API Portal에서 확인 필요
    BASE_URL = "https://api.cjlogistics.com"

    def __init__(
        self,
        customer_id: str,
        api_key: str,
        test_mode: Optional[bool] = None
    ):
        self.customer_id = customer_id
        self.api_key = api_key
        # test_mode: 명시적으로 지정하지 않으면 API 키 유무로 판단
        if test_mode is not None:
            self.test_mode = test_mode
        else:
            self.test_mode = not api_key or os.environ.get("CJ_TEST_MODE", "").lower() == "true"
        self.http_client = httpx.AsyncClient(timeout=30.0)

    def _generate_signature(self, timestamp: str, data: str = "") -> str:
        """API 서명 생성 (NOTE: 실제 인증 방식은 확인 필요)"""
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
        }

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급"""
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
                return ShippingResponse(
                    success=True,
                    tracking_number=tracking_number
                )
            else:
                error_detail = response.text[:200] if response.text else f"HTTP {response.status_code}"
                return ShippingResponse(
                    success=False,
                    error=f"CJ API 오류: {error_detail}"
                )

        except httpx.ConnectError:
            return ShippingResponse(
                success=False,
                error="CJ API 서버에 연결할 수 없습니다. 네트워크를 확인하세요."
            )
        except Exception as e:
            return ShippingResponse(
                success=False,
                error=f"CJ 송장 발급 중 오류 발생: {str(e)}"
            )

    def _test_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """테스트 송장 발급 (명시적 테스트 모드)"""
        tracking_number = f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.randbelow(10000):04d}"
        return ShippingResponse(
            success=True,
            tracking_number=tracking_number,
            is_test=True
        )

    async def close(self):
        """리소스 정리"""
        await self.http_client.aclose()
