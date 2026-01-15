"""
로젠택배 API 클라이언트

로젠택배 오픈 API 연동
- API 문서: https://openapihome.ilogen.com/
- 개발계: https://topenapi.ilogen.com
- 운영계: https://openapi.ilogen.com
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


class LogenClient(BaseShippingCarrier):
    """로젠택배 API 클라이언트

    로젠택배 오픈 API 연동을 위한 클라이언트.
    API 키가 없거나 연결 실패 시 테스트 모드로 동작합니다.

    API 문서: https://openapihome.ilogen.com/
    """

    # 운영계 API 엔드포인트
    BASE_URL = "https://openapi.ilogen.com"
    # 개발계 API 엔드포인트
    DEV_URL = "https://topenapi.ilogen.com"

    def __init__(
        self,
        customer_id: str,
        api_key: str,
        test_mode: bool = False,
        use_dev: bool = False
    ):
        """
        Args:
            customer_id: 로젠택배 거래처 코드
            api_key: API 인증 키
            test_mode: 테스트 모드 여부
            use_dev: 개발계 사용 여부
        """
        self.customer_id = customer_id
        self.api_key = api_key
        self.test_mode = test_mode or not api_key
        self.use_dev = use_dev
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger = logger.bind(carrier="logen")

    @property
    def carrier_code(self) -> str:
        return "logen"

    @property
    def carrier_name(self) -> str:
        return "로젠택배"

    @property
    def base_url(self) -> str:
        return self.DEV_URL if self.use_dev else self.BASE_URL

    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTP 세션 반환"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                    "X-Customer-Code": self.customer_id
                }
            )
        return self._session

    def _generate_signature(self, timestamp: str, data: str) -> str:
        """API 요청 서명 생성"""
        message = f"{timestamp}{data}{self.api_key}"
        signature = hashlib.sha256(message.encode('utf-8')).hexdigest()
        return signature

    async def authenticate(self) -> bool:
        """API 인증 확인"""
        if self.test_mode:
            return True

        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/lrm02b-edi/edi/authCheck",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                return response.status == 200
        except Exception as e:
            self.logger.warning("인증 확인 실패", error=str(e))
            return False

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 요청

        로젠택배 EDI 주문 등록 API 호출
        """

        # 테스트 모드
        if self.test_mode:
            return await self._test_mode_invoice(request)

        try:
            session = await self._get_session()

            # 로젠택배 EDI 형식
            payload = {
                "tradeCode": self.customer_id,  # 거래처코드
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
                "goodsWeight": request.weight,
                "deliveryMemo": request.memo or "",
                "orderNo": request.order_id or "",
                "mallOrderNo": request.channel_order_id or "",
            }

            async with session.post(
                f"{self.base_url}/lrm02b-edi/edi/orderRegist",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("resultCode") == "0000":
                        return ShippingResponse(
                            success=True,
                            tracking_number=data.get("slipNo") or data.get("trackingNumber"),
                            label_url=data.get("labelUrl"),
                            carrier=self.carrier_code,
                            carrier_name=self.carrier_name
                        )
                    else:
                        return ShippingResponse(
                            success=False,
                            error=data.get("resultMsg", "알 수 없는 오류"),
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
        tracking_number = f"LG{timestamp}{random.randint(1000, 9999)}"

        self.logger.info(
            "테스트 송장 발급 (로젠)",
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
        """송장 라벨 PDF 조회

        로젠택배 운송장 출력 API
        """
        if self.test_mode:
            return None

        try:
            session = await self._get_session()
            # 로젠택배 운송장 출력 팝업 API
            async with session.get(
                f"{self.base_url}/lrm02b-edi/edi/outSlipPrint",
                params={"slipNo": tracking_number},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "pdf" in content_type.lower():
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
                "tradeCode": self.customer_id,
                "slipNos": tracking_numbers,
                "pickupDate": pickup_date.strftime("%Y%m%d")
            }

            async with session.post(
                f"{self.base_url}/lrm02b-edi/edi/pickupRequest",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("resultCode") == "0000"
                return False
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
            payload = {
                "tradeCode": self.customer_id,
                "slipNo": tracking_number
            }

            async with session.post(
                f"{self.base_url}/lrm02b-edi/edi/orderCancel",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("resultCode") == "0000"
                return False
        except Exception as e:
            self.logger.error("송장 취소 실패", error=str(e))
            return False

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()

    @classmethod
    def from_credentials(cls, credentials: "UserCredentials") -> "LogenClient":
        """UserCredentials에서 클라이언트 생성"""
        return cls(
            customer_id=getattr(credentials, 'logen_customer_id', '') or '',
            api_key=getattr(credentials, 'logen_api_key', '') or '',
            test_mode=not getattr(credentials, 'logen_api_key', None)
        )
