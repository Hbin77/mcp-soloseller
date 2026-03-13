"""CJ대한통운 DX API 클라이언트

CJ Logistics DX API 연동:
- 인증: ReqOneDayToken → 24시간 유효 토큰
- 운송장 발급: ReqInvcNo
- 접수: RegBook
"""
import re
import httpx
import secrets
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from models import ShippingRequest, ShippingResponse

logger = structlog.get_logger()

BASE_URL_TEST = "https://dxapi-dev.cjlogistics.com:5054"
BASE_URL_PROD = "https://dxapi.cjlogistics.com:5052"

# CJ DX API 게이트웨이 키 (Postman collection 제공 고정값)
GATEWAY_KEY_TEST = "332d248e-ed7c-470c-8732-ccb223b93be8"
GATEWAY_KEY_PROD = "2c9ec67c-4583-4cb6-84c5-93d3facea345"


class CJClient:
    """CJ대한통운 DX API 클라이언트"""

    def __init__(
        self,
        customer_id: str,
        biz_reg_num: str,
        test_mode: bool = True,
    ):
        self.customer_id = customer_id
        self.biz_reg_num = biz_reg_num
        self.test_mode = test_mode
        self.base_url = BASE_URL_TEST if test_mode else BASE_URL_PROD
        self.gateway_key = GATEWAY_KEY_TEST if test_mode else GATEWAY_KEY_PROD
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Token cache
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    @staticmethod
    def _split_phone(phone: str) -> Tuple[str, str, str]:
        """전화번호를 3분할. '010-3508-4959', '01035084959', '02-1234-5678' 등 처리"""
        digits = re.sub(r"[^0-9]", "", phone)
        if len(digits) < 9:
            return digits, "", ""
        # 서울 02 지역번호
        if digits.startswith("02"):
            return digits[:2], digits[2:-4], digits[-4:]
        # 3-4-4 or 3-3-4 패턴
        return digits[:3], digits[3:-4], digits[-4:]

    @staticmethod
    def _split_address(address: str) -> Tuple[str, str]:
        """주소를 기본주소 + 상세주소로 분리"""
        # 시/구/군/동/읍/면/리 뒤의 공백에서 분리 시도
        match = re.search(r"(.*?(?:시|구|군|동|읍|면|리|로|길)\s+\S+)\s+(.*)", address)
        if match:
            return match.group(1), match.group(2)
        # 패턴 매칭 실패시 절반으로 분리
        mid = len(address) // 2
        space_idx = address.find(" ", mid)
        if space_idx == -1:
            return address, ""
        return address[:space_idx], address[space_idx + 1:]

    async def _get_token(self) -> str:
        """토큰 획득 (23시간 TTL 캐싱)"""
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires and now < self._token_expires:
            return self._token

        logger.info("cj.requesting_token", customer_id=self.customer_id)
        resp = await self.http_client.post(
            f"{self.base_url}/ReqOneDayToken",
            json={
                "DATA": {
                    "CUST_ID": self.customer_id,
                    "BIZ_REG_NUM": self.biz_reg_num,
                }
            },
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("RESULT_CD") != "S":
            detail = body.get("RESULT_DETAIL", body.get("RESULT_MSG", "알 수 없는 오류"))
            raise RuntimeError(f"토큰 발급 실패: {detail}")

        data = body.get("DATA") or {}
        self._token = data.get("TOKEN_NUM")
        if not self._token:
            raise RuntimeError("토큰 발급 응답에 TOKEN_NUM이 없습니다")
        self._token_expires = now + timedelta(hours=23)
        logger.info("cj.token_acquired", expires=self._token_expires.isoformat())
        return self._token

    async def _request_invoice_number(self, token: str) -> str:
        """운송장 번호 발급"""
        logger.info("cj.requesting_invoice_number")
        resp = await self.http_client.post(
            f"{self.base_url}/ReqInvcNo",
            json={
                "DATA": {
                    "CLNTNUM": self.customer_id,
                    "TOKEN_NUM": token,
                }
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "CJ-Gateway-APIKey": self.gateway_key,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("RESULT_CD") != "S":
            detail = body.get("RESULT_DETAIL", body.get("RESULT_MSG", "알 수 없는 오류"))
            raise RuntimeError(f"운송장 번호 발급 실패: {detail}")

        data = body.get("DATA") or {}
        invoice_no = data.get("INVC_NO")
        if not invoice_no:
            raise RuntimeError("운송장 번호 응답에 INVC_NO가 없습니다")
        logger.info("cj.invoice_number_acquired", invoice_no=invoice_no)
        return invoice_no

    async def _register_booking(
        self, token: str, invoice_no: str, request: ShippingRequest
    ) -> None:
        """접수 등록 (RegBook)"""
        now = datetime.now()
        today = now.strftime("%Y%m%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y%m%d")
        order_id = request.order_id or f"ORD{now.strftime('%Y%m%d%H%M%S')}"
        mpck_key = f"{today}_{self.customer_id}_{order_id}"

        s1, s2, s3 = self._split_phone(request.sender_phone)
        r1, r2, r3 = self._split_phone(request.receiver_phone)
        s_addr, s_detail = self._split_address(request.sender_address)
        r_addr, r_detail = self._split_address(request.receiver_address)

        payload = {
            "DATA": {
                "CUST_ID": self.customer_id,
                "TOKEN_NUM": token,
                "RCPT_YMD": today,
                "CUST_USE_NO": order_id,
                "RCPT_DV": "02",
                "WORK_DV_CD": "01",
                "REQ_DV_CD": "01",
                "MPCK_KEY": mpck_key,
                "CAL_DV_CD": "2",
                "FRT_DV_CD": "03",
                "CNTR_ITEM_CD": "01",
                "BOX_TYPE_CD": "02",
                "BOX_QTY": "1",
                "FRT": "0",
                "CUST_MGMT_DLCM_CD": "T00002",
                "SENDR_NM": request.sender_name,
                "SENDR_TEL_NO1": s1,
                "SENDR_TEL_NO2": s2,
                "SENDR_TEL_NO3": s3,
                "SENDR_CELL_NO1": s1,
                "SENDR_CELL_NO2": s2,
                "SENDR_CELL_NO3": s3,
                "SENDR_SAFE_NO1": s1,
                "SENDR_SAFE_NO2": s2,
                "SENDR_SAFE_NO3": s3,
                "SENDR_ZIP_NO": request.sender_zipcode,
                "SENDR_ADDR": s_addr,
                "SENDR_DETAIL_ADDR": s_detail,
                "RCVR_NM": request.receiver_name,
                "RCVR_TEL_NO1": r1,
                "RCVR_TEL_NO2": r2,
                "RCVR_TEL_NO3": r3,
                "RCVR_CELL_NO1": r1,
                "RCVR_CELL_NO2": r2,
                "RCVR_CELL_NO3": r3,
                "RCVR_SAFE_NO1": r1,
                "RCVR_SAFE_NO2": r2,
                "RCVR_SAFE_NO3": r3,
                "RCVR_ZIP_NO": request.receiver_zipcode,
                "RCVR_ADDR": r_addr,
                "RCVR_DETAIL_ADDR": r_detail,
                "ORDRR_NM": request.sender_name,
                "ORDRR_TEL_NO1": s1,
                "ORDRR_TEL_NO2": s2,
                "ORDRR_TEL_NO3": s3,
                "ORDRR_CELL_NO1": s1,
                "ORDRR_CELL_NO2": s2,
                "ORDRR_CELL_NO3": s3,
                "ORDRR_SAFE_NO1": s1,
                "ORDRR_SAFE_NO2": s2,
                "ORDRR_SAFE_NO3": s3,
                "ORDRR_ZIP_NO": request.sender_zipcode,
                "ORDRR_ADDR": s_addr,
                "ORDRR_DETAIL_ADDR": s_detail,
                "INVC_NO": invoice_no,
                "ORI_INVC_NO": invoice_no,
                "ORI_ORD_NO": order_id,
                "COLCT_EXPCT_YMD": tomorrow,
                "COLCT_EXPCT_HOUR": "11",
                "SHIP_EXPCT_YMD": tomorrow,
                "SHIP_EXPCT_HOUR": "11",
                "PRT_ST": "1",
                "ARTICLE_AMT": "1",
                "REMARK_1": request.memo or "",
                "REMARK_2": "",
                "REMARK_3": "",
                "COD_YN": "20",
                "ETC_1": "",
                "ETC_2": "1",
                "ETC_3": "",
                "ETC_4": "",
                "ETC_5": "",
                "DLV_DV": "01",
                "RCPT_SERIAL": "",
                "ARRAY": [
                    {
                        "MPCK_SEQ": "1",
                        "GDS_CD": "01",
                        "GDS_NM": request.product_name,
                        "GDS_QTY": str(request.quantity),
                        "UNIT_CD": "01",
                        "UNIT_NM": "EA",
                        "GDS_AMT": "0",
                    }
                ],
            }
        }

        logger.info("cj.registering_booking", invoice_no=invoice_no, order_id=order_id)
        resp = await self.http_client.post(
            f"{self.base_url}/RegBook",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "CJ-Gateway-APIKey": self.gateway_key,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("RESULT_CD") != "S":
            raise RuntimeError(f"접수 등록 실패: {body.get('RESULT_DETAIL', body.get('RESULT_MSG', body))}")

        logger.info("cj.booking_registered", invoice_no=invoice_no)

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 (토큰 → 운송장번호 → 접수 등록)"""
        # Test mode: customer_id나 biz_reg_num이 없으면 테스트 송장
        if not self.customer_id or not self.biz_reg_num:
            return self._test_invoice(request)

        try:
            token = await self._get_token()
            invoice_no = await self._request_invoice_number(token)
            await self._register_booking(token, invoice_no, request)
            return ShippingResponse(success=True, tracking_number=invoice_no)
        except (httpx.ConnectError, httpx.TimeoutException):
            return ShippingResponse(
                success=False,
                error="CJ DX API 서버에 연결할 수 없습니다. 네트워크를 확인하세요.",
            )
        except httpx.HTTPStatusError as e:
            return ShippingResponse(
                success=False,
                error=f"CJ API 서버 오류 (HTTP {e.response.status_code})",
            )
        except RuntimeError as e:
            return ShippingResponse(success=False, error=str(e))
        except Exception as e:
            logger.exception("cj.unexpected_error")
            return ShippingResponse(
                success=False,
                error=f"CJ 송장 발급 중 오류 발생: {str(e)}",
            )

    def _test_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """테스트 송장 발급"""
        tracking_number = f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.randbelow(10000):04d}"
        return ShippingResponse(
            success=True,
            tracking_number=tracking_number,
            is_test=True,
        )

    async def close(self):
        """리소스 정리"""
        await self.http_client.aclose()
