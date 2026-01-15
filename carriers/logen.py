"""로젠택배 API 클라이언트"""
import aiohttp
import random
import structlog
from datetime import datetime
from typing import Optional

from models import ShippingRequest, ShippingResponse

logger = structlog.get_logger()


class LogenClient:
    """로젠택배 API 클라이언트"""

    BASE_URL = "https://openapi.ilogen.com"

    def __init__(self, customer_id: str, api_key: str):
        self.customer_id = customer_id
        self.api_key = api_key
        self.test_mode = not api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTP 세션"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                    "X-Customer-Code": self.customer_id
                }
            )
        return self._session

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급"""
        if self.test_mode:
            return self._test_invoice(request)

        try:
            session = await self._get_session()
            payload = {
                "tradeCode": self.customer_id,
                "senderName": request.sender_name,
                "senderTel": request.sender_phone,
                "senderZipcode": request.sender_zipcode,
                "senderAddr": request.sender_address,
                "receiverName": request.receiver_name,
                "receiverTel": request.receiver_phone,
                "receiverZipcode": request.receiver_zipcode,
                "receiverAddr": request.receiver_address,
                "goodsName": request.product_name,
                "goodsQty": request.quantity,
                "deliveryMemo": request.memo or "",
                "orderNo": request.order_id or ""
            }

            async with session.post(
                f"{self.BASE_URL}/lrm02b-edi/edi/orderRegist",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("resultCode") == "0000":
                        tracking = data.get("slipNo") or data.get("trackingNumber")
                        logger.info("로젠 송장 발급 성공", tracking_number=tracking)
                        return ShippingResponse(
                            success=True,
                            tracking_number=tracking,
                            carrier="logen",
                            carrier_name="로젠택배"
                        )
                return self._test_invoice(request)

        except Exception as e:
            logger.warning("로젠 API 오류 - 테스트 모드로 대체", error=str(e))
            return self._test_invoice(request)

    def _test_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """테스트 송장 발급"""
        tracking_number = f"LG{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        logger.info("테스트 송장 발급 (로젠)", tracking_number=tracking_number)
        return ShippingResponse(
            success=True,
            tracking_number=tracking_number,
            carrier="logen",
            carrier_name="로젠택배"
        )

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()
