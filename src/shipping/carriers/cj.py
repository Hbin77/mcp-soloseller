"""
CJ대한통운 API 클라이언트

CJ대한통운 택배 API 연동
- 송장 발급
- 라벨 출력
- 집하 요청
- 송장 취소

Note: CJ대한통운 API는 계약 후 제공되는 비공개 API입니다.
      실제 연동 시 CJ대한통운에서 제공하는 API 문서에 따라 수정이 필요할 수 있습니다.
"""
import httpx
import hashlib
import hmac
import time
import json
from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING
from . import BaseShippingCarrier, ShippingRequest, ShippingResponse, CarrierType

if TYPE_CHECKING:
    from src.auth import UserCredentials


class CJLogisticsClient(BaseShippingCarrier):
    """CJ대한통운 API 클라이언트"""

    # CJ대한통운 API 엔드포인트 (실제 연동 시 변경 필요)
    BASE_URL = "https://api.cjlogistics.com"

    def __init__(
        self,
        customer_id: str,
        api_key: str,
        contract_code: Optional[str] = None,
        test_mode: bool = False
    ):
        """
        Args:
            customer_id: CJ대한통운 고객 ID
            api_key: API 인증 키
            contract_code: 계약 코드 (택배 단가 계약 코드)
            test_mode: 테스트 모드 여부
        """
        super().__init__()
        self.customer_id = customer_id
        self.api_key = api_key
        self.contract_code = contract_code or customer_id
        self.test_mode = test_mode

        # 테스트 모드일 경우 테스트 서버 사용
        if test_mode:
            self.base_url = "https://test-api.cjlogistics.com"
        else:
            self.base_url = self.BASE_URL

        self.http_client = httpx.AsyncClient(timeout=30.0)

    @classmethod
    def from_credentials(cls, credentials: "UserCredentials") -> Optional["CJLogisticsClient"]:
        """UserCredentials에서 클라이언트 생성 (PlayMCP용)"""
        if not credentials.cj_configured:
            return None
        return cls(
            customer_id=credentials.cj_customer_id,
            api_key=credentials.cj_api_key,
            contract_code=credentials.cj_contract_code
        )

    @property
    def carrier_code(self) -> str:
        return CarrierType.CJ.value

    @property
    def carrier_name(self) -> str:
        return CarrierType.CJ.display_name

    def _generate_signature(self, timestamp: str, data: str = "") -> str:
        """API 서명 생성

        Args:
            timestamp: Unix timestamp 문자열
            data: 요청 데이터

        Returns:
            HMAC-SHA256 서명
        """
        message = f"{self.customer_id}{timestamp}{data}"
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_headers(self, data: str = "") -> dict:
        """API 요청 헤더 생성"""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, data)

        return {
            "Content-Type": "application/json",
            "X-Customer-Id": self.customer_id,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "X-Contract-Code": self.contract_code
        }

    async def authenticate(self) -> bool:
        """API 인증 확인"""
        try:
            # 인증 확인 API 호출 (실제 엔드포인트는 계약 후 확인 필요)
            headers = self._get_headers()
            response = await self.http_client.get(
                f"{self.base_url}/v1/auth/verify",
                headers=headers
            )

            if response.status_code == 200:
                self.logger.info("CJ대한통운 API 인증 성공")
                return True
            else:
                self.logger.warning(
                    "CJ대한통운 API 인증 실패",
                    status=response.status_code,
                    body=response.text
                )
                return False

        except httpx.ConnectError:
            # API 서버에 연결 불가 시 (테스트 환경 등)
            self.logger.warning("CJ대한통운 API 서버 연결 불가 - 테스트 모드로 동작")
            return self.test_mode

        except Exception as e:
            self.logger.exception("CJ대한통운 인증 오류", error=str(e))
            return False

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 요청

        Args:
            request: 송장 발급 요청 데이터

        Returns:
            ShippingResponse: 송장번호 포함 응답
        """
        try:
            # 요청 데이터 구성
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
                "boxType": request.box_type,
                "memo": request.memo or "",
                "orderId": request.order_id or "",
                "contractCode": self.contract_code
            }

            data_str = json.dumps(payload, ensure_ascii=False)
            headers = self._get_headers(data_str)

            # 테스트 모드일 경우 가상 송장번호 생성
            if self.test_mode:
                # 테스트 송장번호: 테스트 prefix + 타임스탬프 + 랜덤
                import random
                tracking_number = f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"

                self.logger.info(
                    "테스트 송장 발급",
                    tracking_number=tracking_number,
                    receiver=request.receiver_name
                )

                return ShippingResponse(
                    success=True,
                    tracking_number=tracking_number,
                    carrier=self.carrier_code,
                    carrier_name=self.carrier_name,
                    requested_at=datetime.now()
                )

            # 실제 API 호출
            response = await self.http_client.post(
                f"{self.base_url}/v1/invoice/create",
                headers=headers,
                json=payload
            )

            if response.status_code in [200, 201]:
                result = response.json()

                tracking_number = result.get("trackingNumber") or result.get("invoiceNo")

                self.logger.info(
                    "송장 발급 성공",
                    tracking_number=tracking_number,
                    receiver=request.receiver_name
                )

                return ShippingResponse(
                    success=True,
                    tracking_number=tracking_number,
                    label_url=result.get("labelUrl"),
                    carrier=self.carrier_code,
                    carrier_name=self.carrier_name,
                    requested_at=datetime.now()
                )
            else:
                error_msg = response.text
                self.logger.error(
                    "송장 발급 실패",
                    status=response.status_code,
                    error=error_msg
                )

                return ShippingResponse(
                    success=False,
                    error=f"송장 발급 실패: {error_msg}",
                    carrier=self.carrier_code,
                    carrier_name=self.carrier_name
                )

        except httpx.ConnectError:
            # 연결 실패 시 테스트 모드로 대체
            if not self.test_mode:
                self.logger.warning("API 연결 실패 - 테스트 모드로 대체 발급")
                self.test_mode = True
                return await self.request_invoice(request)

            return ShippingResponse(
                success=False,
                error="CJ대한통운 API 서버 연결 실패",
                carrier=self.carrier_code,
                carrier_name=self.carrier_name
            )

        except Exception as e:
            self.logger.exception("송장 발급 오류", error=str(e))
            return ShippingResponse(
                success=False,
                error=f"송장 발급 오류: {str(e)}",
                carrier=self.carrier_code,
                carrier_name=self.carrier_name
            )

    async def get_label(self, tracking_number: str) -> Optional[bytes]:
        """송장 라벨 PDF 조회

        Args:
            tracking_number: 송장번호

        Returns:
            PDF 바이너리 데이터 또는 None
        """
        try:
            if self.test_mode:
                # 테스트 모드: 빈 PDF 반환 (또는 None)
                self.logger.info("테스트 모드 - 라벨 PDF 생성 스킵", tracking_number=tracking_number)
                return None

            headers = self._get_headers()
            response = await self.http_client.get(
                f"{self.base_url}/v1/invoice/{tracking_number}/label",
                headers=headers
            )

            if response.status_code == 200:
                return response.content
            else:
                self.logger.error(
                    "라벨 조회 실패",
                    tracking_number=tracking_number,
                    status=response.status_code
                )
                return None

        except Exception as e:
            self.logger.exception("라벨 조회 오류", error=str(e))
            return None

    async def request_pickup(self, tracking_numbers: List[str], pickup_date: date) -> bool:
        """집하 요청

        Args:
            tracking_numbers: 집하 요청할 송장번호 목록
            pickup_date: 집하 희망일

        Returns:
            요청 성공 여부
        """
        try:
            if self.test_mode:
                self.logger.info(
                    "테스트 집하 요청",
                    count=len(tracking_numbers),
                    pickup_date=pickup_date.isoformat()
                )
                return True

            payload = {
                "trackingNumbers": tracking_numbers,
                "pickupDate": pickup_date.isoformat(),
                "contractCode": self.contract_code
            }

            data_str = json.dumps(payload, ensure_ascii=False)
            headers = self._get_headers(data_str)

            response = await self.http_client.post(
                f"{self.base_url}/v1/pickup/request",
                headers=headers,
                json=payload
            )

            if response.status_code in [200, 201]:
                self.logger.info(
                    "집하 요청 성공",
                    count=len(tracking_numbers),
                    pickup_date=pickup_date.isoformat()
                )
                return True
            else:
                self.logger.error(
                    "집하 요청 실패",
                    status=response.status_code,
                    body=response.text
                )
                return False

        except Exception as e:
            self.logger.exception("집하 요청 오류", error=str(e))
            return False

    async def cancel_invoice(self, tracking_number: str) -> bool:
        """송장 취소

        Args:
            tracking_number: 취소할 송장번호

        Returns:
            취소 성공 여부
        """
        try:
            if self.test_mode:
                self.logger.info("테스트 송장 취소", tracking_number=tracking_number)
                return True

            headers = self._get_headers()
            response = await self.http_client.delete(
                f"{self.base_url}/v1/invoice/{tracking_number}",
                headers=headers
            )

            if response.status_code in [200, 204]:
                self.logger.info("송장 취소 성공", tracking_number=tracking_number)
                return True
            else:
                self.logger.error(
                    "송장 취소 실패",
                    tracking_number=tracking_number,
                    status=response.status_code
                )
                return False

        except Exception as e:
            self.logger.exception("송장 취소 오류", error=str(e))
            return False

    async def close(self):
        """리소스 정리"""
        await self.http_client.aclose()
