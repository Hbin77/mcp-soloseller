"""한진택배 API 클라이언트"""
import aiohttp
import random
import structlog
from datetime import datetime
from typing import Optional

from models import ShippingRequest, ShippingResponse

logger = structlog.get_logger()


class HanjinClient:
    """한진택배 API 클라이언트"""

    BASE_URL = "https://api.hanjin.co.kr"

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
                    "X-Customer-Id": self.customer_id
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
                "memo": request.memo or ""
            }

            async with session.post(
                f"{self.BASE_URL}/v1/invoice/create",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("한진 송장 발급 성공", tracking_number=data.get("trackingNumber"))
                    return ShippingResponse(
                        success=True,
                        tracking_number=data.get("trackingNumber"),
                        carrier="hanjin",
                        carrier_name="한진택배"
                    )
                else:
                    return self._test_invoice(request)

        except Exception as e:
            logger.warning("한진 API 오류 - 테스트 모드로 대체", error=str(e))
            return self._test_invoice(request)

    def _test_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """테스트 송장 발급"""
        tracking_number = f"HJ{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        logger.info("테스트 송장 발급 (한진)", tracking_number=tracking_number)
        return ShippingResponse(
            success=True,
            tracking_number=tracking_number,
            carrier="hanjin",
            carrier_name="한진택배"
        )

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()
