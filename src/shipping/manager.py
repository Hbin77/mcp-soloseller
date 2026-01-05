"""
배송 관리자 (ShippingManager)

택배사 선택 및 송장 발급 오케스트레이션
- 주문 정보를 받아 택배사 API로 송장 발급
- 발급된 송장번호를 마켓플레이스에 등록
"""
from datetime import date
from typing import Optional, Dict, List, TYPE_CHECKING
import structlog

from .carriers import (
    BaseShippingCarrier,
    CarrierType,
    ShippingRequest,
    ShippingResponse,
    SenderInfo,
    get_carrier_client
)

if TYPE_CHECKING:
    from src.database import Order
    from src.config import Settings
    from src.auth import UserCredentials

logger = structlog.get_logger()


class ShippingManager:
    """배송 관리자

    택배사 클라이언트 관리 및 송장 발급 오케스트레이션
    """

    def __init__(self, settings: "Settings"):
        """
        Args:
            settings: 애플리케이션 설정
        """
        self.settings = settings
        self.logger = logger.bind(component="ShippingManager")

        # 택배사 클라이언트 캐시
        self._carriers: Dict[CarrierType, BaseShippingCarrier] = {}

        # 발송인 정보
        self._sender_info: Optional[SenderInfo] = None

        # 초기화
        self._initialize()

    def _initialize(self):
        """설정 기반 초기화"""
        # 발송인 정보 로드
        if self.settings.sender_name and self.settings.sender_address:
            self._sender_info = SenderInfo(
                name=self.settings.sender_name,
                phone=self.settings.sender_phone or "",
                zipcode=self.settings.sender_zipcode or "",
                address=self.settings.sender_address
            )
            self.logger.info("발송인 정보 로드 완료", sender=self.settings.sender_name)

        # CJ대한통운 클라이언트 초기화
        if self.settings.cj_configured:
            try:
                from .carriers.cj import CJLogisticsClient
                self._carriers[CarrierType.CJ] = CJLogisticsClient(
                    customer_id=self.settings.cj_customer_id,
                    api_key=self.settings.cj_api_key,
                    contract_code=self.settings.cj_contract_code,
                    test_mode=not self.settings.cj_api_key
                )
                self.logger.info("CJ대한통운 클라이언트 초기화 완료")
            except Exception as e:
                self.logger.error("CJ대한통운 클라이언트 초기화 실패", error=str(e))

        # 한진택배 클라이언트 초기화
        if self.settings.hanjin_configured:
            try:
                from .carriers.hanjin import HanjinClient
                self._carriers[CarrierType.HANJIN] = HanjinClient(
                    customer_id=self.settings.hanjin_customer_id,
                    api_key=self.settings.hanjin_api_key,
                    test_mode=not self.settings.hanjin_api_key
                )
                self.logger.info("한진택배 클라이언트 초기화 완료")
            except Exception as e:
                self.logger.error("한진택배 클라이언트 초기화 실패", error=str(e))

        # 롯데택배 클라이언트 초기화
        if self.settings.lotte_configured:
            try:
                from .carriers.lotte import LotteClient
                self._carriers[CarrierType.LOTTE] = LotteClient(
                    customer_id=self.settings.lotte_customer_id,
                    api_key=self.settings.lotte_api_key,
                    test_mode=not self.settings.lotte_api_key
                )
                self.logger.info("롯데택배 클라이언트 초기화 완료")
            except Exception as e:
                self.logger.error("롯데택배 클라이언트 초기화 실패", error=str(e))

        # 로젠택배 클라이언트 초기화
        if self.settings.logen_configured:
            try:
                from .carriers.logen import LogenClient
                self._carriers[CarrierType.LOGEN] = LogenClient(
                    customer_id=self.settings.logen_customer_id,
                    api_key=self.settings.logen_api_key,
                    test_mode=not self.settings.logen_api_key
                )
                self.logger.info("로젠택배 클라이언트 초기화 완료")
            except Exception as e:
                self.logger.error("로젠택배 클라이언트 초기화 실패", error=str(e))

        # 우체국택배 클라이언트 초기화
        if self.settings.epost_configured:
            try:
                from .carriers.epost import EpostClient
                self._carriers[CarrierType.EPOST] = EpostClient(
                    customer_id=self.settings.epost_customer_id,
                    api_key=self.settings.epost_api_key,
                    test_mode=not self.settings.epost_api_key
                )
                self.logger.info("우체국택배 클라이언트 초기화 완료")
            except Exception as e:
                self.logger.error("우체국택배 클라이언트 초기화 실패", error=str(e))

    @property
    def sender_info(self) -> Optional[SenderInfo]:
        """발송인 정보"""
        return self._sender_info

    @sender_info.setter
    def sender_info(self, info: SenderInfo):
        """발송인 정보 설정"""
        self._sender_info = info

    @property
    def default_carrier(self) -> CarrierType:
        """기본 택배사"""
        return CarrierType(self.settings.default_carrier or "cj")

    def get_available_carriers(self) -> List[Dict]:
        """사용 가능한 택배사 목록

        Returns:
            택배사 정보 목록 (코드, 이름, 설정 여부)
        """
        result = []
        for carrier_type in CarrierType:
            configured = carrier_type in self._carriers
            result.append({
                "code": carrier_type.value,
                "name": carrier_type.display_name,
                "configured": configured,
                "is_default": carrier_type == self.default_carrier
            })
        return result

    def get_carrier(self, carrier_type: Optional[CarrierType] = None) -> Optional[BaseShippingCarrier]:
        """택배사 클라이언트 조회

        Args:
            carrier_type: 택배사 유형 (None이면 기본 택배사)

        Returns:
            택배사 클라이언트 또는 None
        """
        if carrier_type is None:
            carrier_type = self.default_carrier

        return self._carriers.get(carrier_type)

    def set_carrier(self, carrier_type: CarrierType, client: BaseShippingCarrier):
        """택배사 클라이언트 설정

        Args:
            carrier_type: 택배사 유형
            client: 택배사 클라이언트
        """
        self._carriers[carrier_type] = client
        self.logger.info("택배사 클라이언트 설정", carrier=carrier_type.display_name)

    async def request_invoice_for_order(
        self,
        order: "Order",
        carrier_type: Optional[CarrierType] = None
    ) -> ShippingResponse:
        """주문에 대한 송장 발급 요청

        Args:
            order: 주문 정보
            carrier_type: 택배사 유형 (None이면 기본 택배사)

        Returns:
            ShippingResponse: 발급 결과
        """
        # 발송인 정보 확인
        if not self._sender_info:
            return ShippingResponse(
                success=False,
                error="발송인 정보가 설정되지 않았습니다."
            )

        # 택배사 클라이언트 확인
        carrier = self.get_carrier(carrier_type)
        if not carrier:
            carrier_name = (carrier_type or self.default_carrier).display_name
            return ShippingResponse(
                success=False,
                error=f"{carrier_name} 택배사가 설정되지 않았습니다."
            )

        # 상품명 생성 (주문 아이템 기반)
        if order.items:
            if len(order.items) == 1:
                product_name = order.items[0].product_name
            else:
                product_name = f"{order.items[0].product_name} 외 {len(order.items) - 1}건"
        else:
            product_name = "상품"

        # 송장 발급 요청 생성
        request = ShippingRequest(
            sender_name=self._sender_info.name,
            sender_phone=self._sender_info.phone,
            sender_zipcode=self._sender_info.zipcode,
            sender_address=self._sender_info.full_address(),
            receiver_name=order.receiver_name,
            receiver_phone=order.receiver_phone,
            receiver_address=order.receiver_address,
            receiver_zipcode=order.receiver_zipcode or "",
            product_name=product_name,
            quantity=sum(item.quantity for item in order.items) if order.items else 1,
            memo=order.buyer_memo,
            order_id=str(order.id),
            channel_order_id=order.channel_order_id
        )

        # 송장 발급
        response = await carrier.request_invoice(request)

        if response.success:
            self.logger.info(
                "송장 발급 성공",
                order_id=order.id,
                tracking_number=response.tracking_number,
                carrier=response.carrier_name
            )
        else:
            self.logger.error(
                "송장 발급 실패",
                order_id=order.id,
                error=response.error
            )

        return response

    async def request_invoice(
        self,
        request: ShippingRequest,
        carrier_type: Optional[CarrierType] = None
    ) -> ShippingResponse:
        """직접 송장 발급 요청

        Args:
            request: 송장 발급 요청 데이터
            carrier_type: 택배사 유형 (None이면 기본 택배사)

        Returns:
            ShippingResponse: 발급 결과
        """
        carrier = self.get_carrier(carrier_type)
        if not carrier:
            carrier_name = (carrier_type or self.default_carrier).display_name
            return ShippingResponse(
                success=False,
                error=f"{carrier_name} 택배사가 설정되지 않았습니다."
            )

        return await carrier.request_invoice(request)

    async def get_label(
        self,
        tracking_number: str,
        carrier_type: Optional[CarrierType] = None
    ) -> Optional[bytes]:
        """송장 라벨 PDF 조회

        Args:
            tracking_number: 송장번호
            carrier_type: 택배사 유형

        Returns:
            PDF 바이너리 또는 None
        """
        carrier = self.get_carrier(carrier_type)
        if not carrier:
            return None

        return await carrier.get_label(tracking_number)

    async def request_pickup(
        self,
        tracking_numbers: List[str],
        pickup_date: date,
        carrier_type: Optional[CarrierType] = None
    ) -> bool:
        """집하 요청

        Args:
            tracking_numbers: 송장번호 목록
            pickup_date: 집하 희망일
            carrier_type: 택배사 유형

        Returns:
            성공 여부
        """
        carrier = self.get_carrier(carrier_type)
        if not carrier:
            return False

        return await carrier.request_pickup(tracking_numbers, pickup_date)

    async def cancel_invoice(
        self,
        tracking_number: str,
        carrier_type: Optional[CarrierType] = None
    ) -> bool:
        """송장 취소

        Args:
            tracking_number: 송장번호
            carrier_type: 택배사 유형

        Returns:
            성공 여부
        """
        carrier = self.get_carrier(carrier_type)
        if not carrier:
            return False

        return await carrier.cancel_invoice(tracking_number)

    async def close(self):
        """리소스 정리"""
        for carrier in self._carriers.values():
            await carrier.close()
        self._carriers.clear()

    def reload_settings(self, settings: "Settings"):
        """설정 다시 로드

        Args:
            settings: 새로운 설정
        """
        self.settings = settings
        self._initialize()


# PlayMCP용 팩토리 함수
def create_shipping_manager_from_credentials(
    credentials: "UserCredentials",
    default_sender: Optional[SenderInfo] = None
) -> ShippingManager:
    """UserCredentials에서 ShippingManager 생성

    Args:
        credentials: PlayMCP 사용자 인증 정보
        default_sender: 기본 발송인 정보

    Returns:
        ShippingManager 인스턴스
    """
    from src.config import get_settings

    # 기본 설정 가져오기
    settings = get_settings()

    # ShippingManager 생성
    manager = ShippingManager(settings)

    # 사용자 credentials로 클라이언트 재설정
    if getattr(credentials, 'cj_configured', False):
        from .carriers.cj import CJLogisticsClient
        manager.set_carrier(
            CarrierType.CJ,
            CJLogisticsClient.from_credentials(credentials)
        )

    if getattr(credentials, 'hanjin_configured', False):
        from .carriers.hanjin import HanjinClient
        manager.set_carrier(
            CarrierType.HANJIN,
            HanjinClient.from_credentials(credentials)
        )

    if getattr(credentials, 'lotte_configured', False):
        from .carriers.lotte import LotteClient
        manager.set_carrier(
            CarrierType.LOTTE,
            LotteClient.from_credentials(credentials)
        )

    if getattr(credentials, 'logen_configured', False):
        from .carriers.logen import LogenClient
        manager.set_carrier(
            CarrierType.LOGEN,
            LogenClient.from_credentials(credentials)
        )

    if getattr(credentials, 'epost_configured', False):
        from .carriers.epost import EpostClient
        manager.set_carrier(
            CarrierType.EPOST,
            EpostClient.from_credentials(credentials)
        )

    # 발송인 정보 설정
    if default_sender:
        manager.sender_info = default_sender

    return manager
