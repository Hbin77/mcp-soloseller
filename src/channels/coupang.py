"""
쿠팡 WING OPEN API 클라이언트
https://developers.coupangcorp.com
"""
import httpx
import hmac
import hashlib
import time
from typing import Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlencode
from . import BaseChannelClient, ChannelOrder, ChannelOrderItem, ChannelClaim
import structlog

logger = structlog.get_logger()


class CoupangWingClient(BaseChannelClient):
    """쿠팡 WING API 클라이언트"""
    
    BASE_URL = "https://api-gateway.coupang.com"
    
    def __init__(self, vendor_id: str, access_key: str, secret_key: str):
        super().__init__()
        self.vendor_id = vendor_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def channel_name(self) -> str:
        return "coupang"
    
    def _generate_signature(self, method: str, path: str, query_string: str = "") -> dict:
        """HMAC-SHA256 서명 생성"""
        datetime_str = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
        
        # 메시지 구성
        message = datetime_str + method + path
        if query_string:
            message += "?" + query_string
        
        # 서명 생성
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Authorization 헤더 구성
        authorization = f"CEA algorithm=HmacSHA256, access-key={self.access_key}, " \
                       f"signed-date={datetime_str}, signature={signature}"
        
        return {
            "Authorization": authorization,
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-By": self.vendor_id
        }
    
    async def authenticate(self) -> bool:
        """인증 확인 (쿠팡은 각 요청마다 서명하므로 항상 True)"""
        self.logger.info("쿠팡 API 준비 완료")
        return True
    
    async def get_new_orders(self) -> List[ChannelOrder]:
        """신규 주문 조회"""
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets"
            params = {
                "createdAtFrom": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "createdAtTo": datetime.now().strftime("%Y-%m-%d"),
                "status": "ACCEPT"  # 결제완료 상태
            }
            query_string = urlencode(params)
            
            headers = self._generate_signature("GET", path, query_string)
            
            response = await self.http_client.get(
                f"{self.BASE_URL}{path}",
                params=params,
                headers=headers
            )
            
            if response.status_code != 200:
                self.logger.error("주문 조회 실패", status=response.status_code, body=response.text)
                return []
            
            data = response.json()
            orders = []
            
            for order_data in data.get("data", []):
                order = self._parse_order(order_data)
                if order:
                    orders.append(order)
            
            self.logger.info("쿠팡 주문 조회 완료", count=len(orders))
            return orders
            
        except Exception as e:
            self.logger.exception("주문 조회 오류", error=str(e))
            return []
    
    def _parse_order(self, data: dict) -> Optional[ChannelOrder]:
        """주문 데이터 파싱"""
        try:
            items = []
            for product in data.get("orderItems", []):
                item = ChannelOrderItem(
                    channel_product_id=str(product.get("vendorItemId", "")),
                    product_name=product.get("vendorItemName", ""),
                    option_name=product.get("sellerProductItemName"),
                    quantity=product.get("shippingCount", 1),
                    unit_price=product.get("orderPrice", 0),
                    total_price=product.get("orderPrice", 0) * product.get("shippingCount", 1)
                )
                items.append(item)
            
            receiver = data.get("receiver", {})
            orderer = data.get("orderer", {})
            
            return ChannelOrder(
                channel_order_id=str(data.get("shipmentBoxId", "")),
                status=data.get("status", ""),
                buyer_name=orderer.get("name", ""),
                buyer_phone=orderer.get("phone"),
                buyer_email=orderer.get("email"),
                receiver_name=receiver.get("name", ""),
                receiver_phone=receiver.get("phone", ""),
                receiver_address=f"{receiver.get('addr1', '')} {receiver.get('addr2', '')}",
                receiver_zipcode=receiver.get("postCode"),
                total_amount=data.get("totalPaymentPrice", 0),
                shipping_fee=data.get("shippingPrice", 0),
                buyer_memo=data.get("parcelPrintMessage"),
                ordered_at=datetime.fromisoformat(data.get("orderedAt", datetime.now().isoformat()).replace("Z", "+00:00")),
                items=items
            )
        except Exception as e:
            self.logger.error("주문 파싱 오류", error=str(e))
            return None
    
    async def get_order_detail(self, order_id: str) -> Optional[ChannelOrder]:
        """주문 상세 조회"""
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets/{order_id}"
            headers = self._generate_signature("GET", path)
            
            response = await self.http_client.get(
                f"{self.BASE_URL}{path}",
                headers=headers
            )
            
            if response.status_code == 200:
                return self._parse_order(response.json().get("data", {}))
            return None
            
        except Exception as e:
            self.logger.exception("주문 상세 조회 오류", error=str(e))
            return None
    
    async def confirm_order(self, order_id: str) -> bool:
        """발주 확인"""
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets/{order_id}/confirm"
            headers = self._generate_signature("PUT", path)
            
            response = await self.http_client.put(
                f"{self.BASE_URL}{path}",
                headers=headers,
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
        # 택배사 코드 매핑
        carrier_codes = {
            "CJ대한통운": "CJGLS",
            "한진택배": "HANJIN",
            "롯데택배": "LOTTE",
            "우체국택배": "EPOST",
            "로젠택배": "LOGEN"
        }
        
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets/{order_id}/invoices"
            headers = self._generate_signature("POST", path)
            
            response = await self.http_client.post(
                f"{self.BASE_URL}{path}",
                headers=headers,
                json={
                    "vendorId": self.vendor_id,
                    "shipmentBoxId": int(order_id),
                    "deliveryCompanyCode": carrier_codes.get(carrier, "CJGLS"),
                    "invoiceNumber": tracking_number
                }
            )
            
            if response.status_code in [200, 201]:
                self.logger.info("송장 등록 완료", order_id=order_id, tracking_number=tracking_number)
                return True
            else:
                self.logger.error("송장 등록 실패", order_id=order_id, status=response.status_code, body=response.text)
                return False
                
        except Exception as e:
            self.logger.exception("송장 등록 오류", error=str(e))
            return False
    
    async def get_claims(self) -> List[ChannelClaim]:
        """클레임(반품/교환/취소) 조회"""
        claims = []
        
        try:
            # 반품 요청 조회
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/returnRequests"
            params = {
                "createdAtFrom": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "createdAtTo": datetime.now().strftime("%Y-%m-%d")
            }
            query_string = urlencode(params)
            headers = self._generate_signature("GET", path, query_string)
            
            response = await self.http_client.get(
                f"{self.BASE_URL}{path}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                for claim_data in response.json().get("data", []):
                    claim = ChannelClaim(
                        channel_claim_id=str(claim_data.get("receiptId", "")),
                        channel_order_id=str(claim_data.get("shipmentBoxId", "")),
                        claim_type="return",
                        status=claim_data.get("status", ""),
                        reason=claim_data.get("returnReason"),
                        requested_at=datetime.fromisoformat(
                            claim_data.get("createdAt", datetime.now().isoformat()).replace("Z", "+00:00")
                        )
                    )
                    claims.append(claim)
            
            # 취소 요청 조회
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/cancelRequests"
            headers = self._generate_signature("GET", path, query_string)
            
            response = await self.http_client.get(
                f"{self.BASE_URL}{path}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                for claim_data in response.json().get("data", []):
                    claim = ChannelClaim(
                        channel_claim_id=str(claim_data.get("receiptId", "")),
                        channel_order_id=str(claim_data.get("shipmentBoxId", "")),
                        claim_type="cancel",
                        status=claim_data.get("status", ""),
                        reason=claim_data.get("cancelReason"),
                        requested_at=datetime.fromisoformat(
                            claim_data.get("createdAt", datetime.now().isoformat()).replace("Z", "+00:00")
                        )
                    )
                    claims.append(claim)
            
            self.logger.info("쿠팡 클레임 조회 완료", count=len(claims))
            return claims
            
        except Exception as e:
            self.logger.exception("클레임 조회 오류", error=str(e))
            return []
    
    async def update_stock(self, product_id: str, quantity: int) -> bool:
        """재고 업데이트"""
        try:
            path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/products/stocks"
            headers = self._generate_signature("PUT", path)
            
            response = await self.http_client.put(
                f"{self.BASE_URL}{path}",
                headers=headers,
                json=[{
                    "vendorItemId": int(product_id),
                    "quantity": quantity
                }]
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
