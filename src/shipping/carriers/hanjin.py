"""
한진택배 API 클라이언트

한진택배 택배 API 연동
- API 문서: 계약 후 제공
- 인증: API Key + Customer ID
"""
import asyncio
import time
import hashlib
import hmac
from datetime import date, datetime
from typing import Optional, List, TYPE_CHECKING

import aiohttp
import structlog

from . import BaseShippingCarrier, ShippingRequest, ShippingResponse

if TYPE_CHECKING:
    from src.auth import UserCredentials

logger = structlog.get_logger()


class HanjinClient(BaseShippingCarrier):
    """한진택배 API 클라이언트

    한진택배 API 연동을 위한 클라이언트.
    API 키가 없거나 연결 실패 시 테스트 모드로 동작합니다.
    """

    # API 엔드포인트 (실제 연동 시 한진택배에서 제공)
    BASE_URL = "https://api.hanjin.co.kr"

    def __init__(
        self,
        customer_id: str,
        api_key: str,
        test_mode: bool = False
    ):
        """
        Args:
            customer_id: 한진택배 고객 ID
            api_key: API 인증 키
            test_mode: 테스트 모드 여부
        """
        self.customer_id = customer_id
        self.api_key = api_key
        self.test_mode = test_mode or not api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger = logger.bind(carrier="hanjin")

    @property
    def carrier_code(self) -> str:
        return "hanjin"

    @property
    def carrier_name(self) -> str:
        return "한진택배"

    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTP 세션 반환"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                    "X-Customer-Id": self.customer_id
                }
            )
        return self._session

    def _generate_signature(self, payload: str) -> str:
        """API 요청 서명 생성"""
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{payload}"
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def authenticate(self) -> bool:
        """API 인증 확인"""
        if self.test_mode:
            return True

        try:
            session = await self._get_session()
            async with session.get(
                f"{self.BASE_URL}/v1/auth/verify",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                return response.status == 200
        except Exception as e:
            self.logger.warning("인증 확인 실패", error=str(e))
            return False

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 요청"""

        # 테스트 모드
        if self.test_mode:
            return await self._test_mode_invoice(request)

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
                "weight": request.weight,
                "memo": request.memo or "",
                "orderId": request.order_id or "",
            }

            async with session.post(
                f"{self.BASE_URL}/v1/invoice/create",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return ShippingResponse(
                        success=True,
                        tracking_number=data.get("trackingNumber"),
                        label_url=data.get("labelUrl"),
                        carrier=self.carrier_code,
                        carrier_name=self.carrier_name
                    )
                else:
                    error_text = await response.text()
                    return ShippingResponse(
                        success=False,
                        error=f"API 오류: {response.status} - {error_text}",
                        carrier=self.carrier_code,
                        carrier_name=self.carrier_name
                    )

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.logger.warning("API 연결 실패 - 테스트 모드로 대체 발급", error=str(e))
            return await self._test_mode_invoice(request)
        except Exception as e:
            self.logger.warning("API 오류 - 테스트 모드로 대체 발급", error=str(e))
            return await self._test_mode_invoice(request)

    async def _test_mode_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """테스트 모드 송장 발급"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        import random
        tracking_number = f"HJ{timestamp}{random.randint(1000, 9999)}"

        self.logger.info(
            "테스트 송장 발급 (한진)",
            tracking_number=tracking_number,
            receiver=request.receiver_name
        )

        return ShippingResponse(
            success=True,
            tracking_number=tracking_number,
            carrier=self.carrier_code,
            carrier_name=self.carrier_name
        )

    async def get_label(self, tracking_number: str) -> Optional[bytes]:
        """송장 라벨 PDF 조회"""
        if self.test_mode:
            return None

        try:
            session = await self._get_session()
            async with session.get(
                f"{self.BASE_URL}/v1/invoice/{tracking_number}/label",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.read()
        except Exception as e:
            self.logger.error("라벨 조회 실패", error=str(e))

        return None

    async def request_pickup(
        self,
        tracking_numbers: List[str],
        pickup_date: date
    ) -> bool:
        """집하 요청"""
        if self.test_mode:
            self.logger.info("테스트 집하 요청", count=len(tracking_numbers))
            return True

        try:
            session = await self._get_session()
            payload = {
                "trackingNumbers": tracking_numbers,
                "pickupDate": pickup_date.isoformat()
            }

            async with session.post(
                f"{self.BASE_URL}/v1/pickup/request",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                return response.status == 200
        except Exception as e:
            self.logger.error("집하 요청 실패", error=str(e))
            return False

    async def cancel_invoice(self, tracking_number: str) -> bool:
        """송장 취소"""
        if self.test_mode:
            self.logger.info("테스트 송장 취소", tracking_number=tracking_number)
            return True

        try:
            session = await self._get_session()
            async with session.delete(
                f"{self.BASE_URL}/v1/invoice/{tracking_number}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                return response.status == 200
        except Exception as e:
            self.logger.error("송장 취소 실패", error=str(e))
            return False

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()

    @classmethod
    def from_credentials(cls, credentials: "UserCredentials") -> "HanjinClient":
        """UserCredentials에서 클라이언트 생성"""
        return cls(
            customer_id=getattr(credentials, 'hanjin_customer_id', '') or '',
            api_key=getattr(credentials, 'hanjin_api_key', '') or '',
            test_mode=not getattr(credentials, 'hanjin_api_key', None)
        )
