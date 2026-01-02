"""
네이버 스마트스토어 커머스 API 클라이언트
https://apicenter.commerce.naver.com
"""
import httpx
import hmac
import hashlib
import base64
import time
from typing import Optional, List
from datetime import datetime, timedelta
from . import BaseChannelClient, ChannelOrder, ChannelOrderItem, ChannelClaim
import structlog

logger = structlog.get_logger()


class NaverCommerceClient(BaseChannelClient):
    """네이버 커머스 API 클라이언트"""
    
    BASE_URL = "https://api.commerce.naver.com/external"
    
    def __init__(self, client_id: str, client_secret: str, seller_id: str):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.seller_id = seller_id
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def channel_name(self) -> str:
        return "naver"
    
    def _generate_signature(self, timestamp: str) -> str:
        """HMAC 서명 생성"""
        message = f"{self.client_id}_{timestamp}"
        signature = hmac.new(
            self.client_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')
    
    async def authenticate(self) -> bool:
        """OAuth 토큰 발급"""
        try:
            # 토큰이 유효하면 재사용
            if self.access_token and self.token_expires_at:
                if datetime.now() < self.token_expires_at - timedelta(minutes=5):
                    return True
            
            timestamp = str(int(time.time() * 1000))
            signature = self._generate_signature(timestamp)
            
            response = await self.http_client.post(
                f"{self.BASE_URL}/v1/oauth2/token",
                data={
                    "client_id": self.client_id,
                    "timestamp": timestamp,
                    "client_secret_sign": signature,
                    "grant_type": "client_credentials",
                    "type": "SELF"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                self.logger.info("네이버 인증 성공")
                return True
            else:
                self.logger.error("네이버 인증 실패", status=response.status_code, body=response.text)
                return False
                
        except Exception as e:
            self.logger.exception("네이버 인증 오류", error=str(e))
            return False
    
    def _get_headers(self) -> dict:
        """API 요청 헤더"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def get_new_orders(self) -> List[ChannelOrder]:
        """신규 주문 조회 (결제완료/발주확인대기 상태)"""
        if not await self.authenticate():
            return []
        
        try:
            # 최근 7일 주문 조회
            params = {
                "orderStatus": "PAYED",  # 결제완료 상태
                "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),
                "to": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "limitCount": 100
            }
            
            response = await self.http_client.get(
                f"{self.BASE_URL}/v1/pay-order/seller/orders",
                params=params,
                headers=self._get_headers()
            )
            
            if response.status_code != 200:
                self.logger.error("주문 조회 실패", status=response.status_code)
                return []
            
            data = response.json()
            orders = []
            
            for order_data in data.get("data", []):
                order = self._parse_order(order_data)
                if order:
                    orders.append(order)
            
            self.logger.info("네이버 주문 조회 완료", count=len(orders))
            return orders
            
        except Exception as e:
            self.logger.exception("주문 조회 오류", error=str(e))
            return []
    
    def _parse_order(self, data: dict) -> Optional[ChannelOrder]:
        """주문 데이터 파싱"""
        try:
            items = []
            for product in data.get("productOrderInfos", []):
                item = ChannelOrderItem(
                    channel_product_id=str(product.get("productId", "")),
                    product_name=product.get("productName", ""),
                    option_name=product.get("optionContent"),
                    quantity=product.get("quantity", 1),
                    unit_price=product.get("unitPrice", 0),
                    total_price=product.get("totalPaymentAmount", 0)
                )
                items.append(item)
            
            order_info = data.get("generalPaymentInfo", {})
            delivery_info = data.get("deliveryInfo", {})
            
            return ChannelOrder(
                channel_order_id=data.get("orderId", ""),
                status=data.get("orderStatus", ""),
                buyer_name=order_info.get("ordererName", ""),
                buyer_phone=order_info.get("ordererTel"),
                buyer_email=order_info.get("ordererEmail"),
                receiver_name=delivery_info.get("name", ""),
                receiver_phone=delivery_info.get("tel1", ""),
                receiver_address=f"{delivery_info.get('baseAddress', '')} {delivery_info.get('detailAddress', '')}",
                receiver_zipcode=delivery_info.get("zipCode"),
                total_amount=order_info.get("totalPaymentAmount", 0),
                shipping_fee=order_info.get("deliveryFee", 0),
                buyer_memo=delivery_info.get("deliveryMemo"),
                ordered_at=datetime.fromisoformat(data.get("orderDate", datetime.now().isoformat()).replace("Z", "+00:00")),
                items=items
            )
        except Exception as e:
            self.logger.error("주문 파싱 오류", error=str(e))
            return None
    
    async def get_order_detail(self, order_id: str) -> Optional[ChannelOrder]:
        """주문 상세 조회"""
        if not await self.authenticate():
            return None
        
        try:
            response = await self.http_client.get(
                f"{self.BASE_URL}/v1/pay-order/seller/orders/{order_id}",
                headers=self._get_headers()
            )
            
            if response.status_code == 200:
                return self._parse_order(response.json().get("data", {}))
            return None
            
        except Exception as e:
            self.logger.exception("주문 상세 조회 오류", error=str(e))
            return None
    
    async def confirm_order(self, order_id: str) -> bool:
        """발주 확인"""
        if not await self.authenticate():
            return False
        
        try:
            response = await self.http_client.post(
                f"{self.BASE_URL}/v1/pay-order/seller/orders/{order_id}/confirm",
                headers=self._get_headers(),
                json={}
            )
            
            if response.status_code in [200, 201]:
                self.logger.info("발주 확인 완료", order_id=order_id)
                return True
            else:
                self.logger.error("발주 확인 실패", order_id=order_id, status=response.status_code)
                return False
                
        except Exception as e:
            self.logger.exception("발주 확인 오류", error=str(e))
            return False
    
    async def register_invoice(self, order_id: str, tracking_number: str, carrier: str = "CJ대한통운") -> bool:
        """송장 등록 (발송 처리)"""
        if not await self.authenticate():
            return False
        
        # 택배사 코드 매핑
        carrier_codes = {
            "CJ대한통운": "CJGLS",
            "한진택배": "HANJIN",
            "롯데택배": "LOTTE",
            "우체국택배": "EPOST",
            "로젠택배": "LOGEN"
        }
        
        try:
            response = await self.http_client.post(
                f"{self.BASE_URL}/v1/pay-order/seller/orders/{order_id}/ship",
                headers=self._get_headers(),
                json={
                    "deliveryCompanyCode": carrier_codes.get(carrier, "CJGLS"),
                    "trackingNumber": tracking_number
                }
            )
            
            if response.status_code in [200, 201]:
                self.logger.info("송장 등록 완료", order_id=order_id, tracking_number=tracking_number)
                return True
            else:
                self.logger.error("송장 등록 실패", order_id=order_id, status=response.status_code)
                return False
                
        except Exception as e:
            self.logger.exception("송장 등록 오류", error=str(e))
            return False
    
    async def get_claims(self) -> List[ChannelClaim]:
        """클레임(반품/교환/취소) 조회"""
        if not await self.authenticate():
            return []
        
        claims = []
        
        try:
            # 반품 요청 조회
            for claim_type, endpoint in [
                ("return", "/v1/pay-order/seller/returns"),
                ("exchange", "/v1/pay-order/seller/exchanges"),
                ("cancel", "/v1/pay-order/seller/cancels")
            ]:
                response = await self.http_client.get(
                    f"{self.BASE_URL}{endpoint}",
                    params={
                        "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S"),
                        "to": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                        "limitCount": 50
                    },
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    for claim_data in response.json().get("data", []):
                        claim = ChannelClaim(
                            channel_claim_id=claim_data.get("claimId", ""),
                            channel_order_id=claim_data.get("orderId", ""),
                            claim_type=claim_type,
                            status=claim_data.get("claimStatus", ""),
                            reason=claim_data.get("claimReason"),
                            requested_at=datetime.fromisoformat(
                                claim_data.get("claimRequestDate", datetime.now().isoformat()).replace("Z", "+00:00")
                            )
                        )
                        claims.append(claim)
            
            self.logger.info("네이버 클레임 조회 완료", count=len(claims))
            return claims
            
        except Exception as e:
            self.logger.exception("클레임 조회 오류", error=str(e))
            return []
    
    async def update_stock(self, product_id: str, quantity: int) -> bool:
        """재고 업데이트"""
        if not await self.authenticate():
            return False
        
        try:
            response = await self.http_client.put(
                f"{self.BASE_URL}/v1/products/{product_id}/stock",
                headers=self._get_headers(),
                json={"stockQuantity": quantity}
            )
            
            if response.status_code in [200, 201]:
                self.logger.info("재고 업데이트 완료", product_id=product_id, quantity=quantity)
                return True
            else:
                self.logger.error("재고 업데이트 실패", product_id=product_id, status=response.status_code)
                return False
                
        except Exception as e:
            self.logger.exception("재고 업데이트 오류", error=str(e))
            return False
    
    async def close(self):
        """리소스 정리"""
        await self.http_client.aclose()
