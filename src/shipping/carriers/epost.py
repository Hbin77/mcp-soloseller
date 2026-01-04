"""
우체국택배 API 클라이언트 (스텁)

추후 구현 예정
"""
from datetime import date
from typing import Optional, List, TYPE_CHECKING

from . import BaseShippingCarrier, ShippingRequest, ShippingResponse

if TYPE_CHECKING:
    from src.auth import UserCredentials


class EpostClient(BaseShippingCarrier):
    """우체국택배 API 클라이언트 (미구현)"""

    def __init__(
        self,
        customer_id: str,
        api_key: str,
        test_mode: bool = False
    ):
        self.customer_id = customer_id
        self.api_key = api_key
        self.test_mode = test_mode

    @property
    def carrier_code(self) -> str:
        return "epost"

    @property
    def carrier_name(self) -> str:
        return "우체국택배"

    async def authenticate(self) -> bool:
        """API 인증 확인"""
        # TODO: 우체국택배 API 인증 구현
        return False

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 요청"""
        return ShippingResponse(
            success=False,
            error="우체국택배 API는 아직 구현되지 않았습니다."
        )

    async def get_label(self, tracking_number: str) -> Optional[bytes]:
        """송장 라벨 PDF 조회"""
        return None

    async def request_pickup(
        self,
        tracking_numbers: List[str],
        pickup_date: date
    ) -> bool:
        """집하 요청"""
        return False

    async def cancel_invoice(self, tracking_number: str) -> bool:
        """송장 취소"""
        return False

    async def close(self):
        """리소스 정리"""
        pass

    @classmethod
    def from_credentials(cls, credentials: "UserCredentials") -> "EpostClient":
        """UserCredentials에서 클라이언트 생성"""
        return cls(
            customer_id=credentials.epost_customer_id or "",
            api_key=credentials.epost_api_key or "",
            test_mode=True
        )
