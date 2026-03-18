"""CJ대한통운 DX API 클라이언트

CJ Logistics DX API 연동:
- 인증: ReqOneDayToken → 24시간 유효 토큰
- 주소 검증: ReqAddrRfnSm → 배송 가능 여부 확인
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




# 주소 정제 오류 코드 → 메시지 매핑 (문서 p.11)
_ADDR_ERROR_MESSAGES = {
    "-20000": "입력 파라미터 값이 잘못되었습니다.",
    "-20001": "CJ 대한통운에 등록되지 않은 고객 ID입니다.",
    "-20002": "주소 분석에 실패했습니다.",
    "-20003": "집배권역 설정값을 찾지 못했습니다.",
    "-20004": "집배권역 점소정보가 폐점이거나 사용중지 상태입니다.",
    "-20005": "배송/집화 담당 사원이 설정되지 않았습니다.",
    "-20006": "도착지 코드 추출에 실패했습니다.",
    "-20007": "분류주소 추출에 실패했습니다.",
    "-20008": "고객 ID 계약이 만료되었거나 존재하지 않습니다.",
    "-20009": "배송이 불가능한 주소지입니다.",
    "-20010": "배송지연이 발생할 수 있는 지역입니다.",
}


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

    async def validate_delivery_address(self, address: str) -> dict:
        """CJ DX API 주소 정제 (ReqAddrRfnSm) - 배송 가능 여부 검증

        주소를 CJ 시스템에 조회하여 배송 가능 여부와 라우팅 정보를 반환합니다.
        주소 분리(기본/상세) 용도가 아닌, 배송 가능성 사전 검증 용도입니다.

        Returns:
            {
                "success": True,
                "deliverable": True,
                "branch_name": "중구소공",  # 배송집배점명
                "region": "01",            # 권역 구분
                "address_code": "5D32",    # 도착지 코드
                "warning": "..."           # 배송지연 경고 (있는 경우)
            }
            또는 실패 시 {"success": False, "deliverable": False, "error": "..."}
        """
        if not self.customer_id or not self.biz_reg_num:
            return {"success": False, "deliverable": False, "error": "CJ 자격증명 없음 (테스트 모드)"}

        if not address or len(address) > 100:
            return {"success": False, "deliverable": False, "error": "주소가 비어있거나 너무 깁니다 (최대 100자)"}

        try:
            token = await self._get_token()
            resp = await self.http_client.post(
                f"{self.base_url}/ReqAddrRfnSm",
                json={
                    "DATA": {
                        "TOKEN_NUM": token,
                        "CLNTNUM": self.customer_id,
                        "CLNTMGMCUSTCD": self.customer_id,
                        "ADDRESS": address,
                    }
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "CJ-Gateway-APIKey": token,
                },
            )
            resp.raise_for_status()
            body = resp.json()

            result_cd = body.get("RESULT_CD", "")

            # 배송 불가능 주소
            if result_cd == "-20009":
                return {
                    "success": True,
                    "deliverable": False,
                    "error": _ADDR_ERROR_MESSAGES.get(result_cd, "배송 불가능 주소"),
                }

            # 배송 지연 가능 지역
            if result_cd == "-20010":
                data = body.get("DATA") or {}
                return {
                    "success": True,
                    "deliverable": True,
                    "branch_name": data.get("CLLDLVBRANNM", ""),
                    "region": data.get("RSPSDIV", ""),
                    "address_code": data.get("CLSFCD", ""),
                    "warning": _ADDR_ERROR_MESSAGES.get(result_cd, "배송지연 가능"),
                }

            # 기타 오류
            if result_cd != "S":
                error_msg = _ADDR_ERROR_MESSAGES.get(result_cd, body.get("RESULT_DETAIL", "주소 검증 실패"))
                logger.warning("cj.address_validate_failed", result_cd=result_cd)
                return {"success": False, "deliverable": False, "error": error_msg}

            # 성공
            data = body.get("DATA") or {}
            return {
                "success": True,
                "deliverable": True,
                "branch_name": data.get("CLLDLVBRANNM", ""),
                "region": data.get("RSPSDIV", ""),
                "address_code": data.get("CLSFCD", ""),
                "address_summary": data.get("CLSFADDR", ""),
            }
        except Exception as e:
            logger.warning("cj.address_validate_error", error=str(e))
            return {"success": False, "deliverable": True, "error": "주소 검증 중 오류 발생"}

    async def _get_token(self) -> str:
        """토큰 획득 (TOKEN_EXPRTN_DTM 기반 캐싱)"""
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

        # TOKEN_EXPRTN_DTM 파싱 (format: YYYYMMDDHHMMSS)
        expiry_str = data.get("TOKEN_EXPRTN_DTM", "").strip()
        if expiry_str:
            try:
                self._token_expires = datetime.strptime(expiry_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                # 만료 30분 전에 갱신하도록 여유 확보
                self._token_expires -= timedelta(minutes=30)
            except ValueError:
                self._token_expires = now + timedelta(hours=23)
        else:
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
                "CJ-Gateway-APIKey": token,
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
                "RCPT_DV": "01",
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
                "ORI_INVC_NO": "",
                "ORI_ORD_NO": order_id,
                "COLCT_EXPCT_YMD": "",
                "COLCT_EXPCT_HOUR": "",
                "SHIP_EXPCT_YMD": "",
                "SHIP_EXPCT_HOUR": "",
                "PRT_ST": "01",
                "ARTICLE_AMT": "1",
                "REMARK_1": request.memo or "",
                "REMARK_2": "",
                "REMARK_3": "",
                "COD_YN": "N",
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
                "CJ-Gateway-APIKey": token,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("RESULT_CD") != "S":
            raise RuntimeError(f"접수 등록 실패: {body.get('RESULT_DETAIL', body.get('RESULT_MSG', body))}")

        logger.info("cj.booking_registered", invoice_no=invoice_no)

    async def request_invoice(self, request: ShippingRequest) -> ShippingResponse:
        """송장 발급 (주소검증 → 토큰 → 운송장번호 → 접수 등록)"""
        # Test mode: customer_id나 biz_reg_num이 없으면 테스트 송장
        if not self.customer_id or not self.biz_reg_num:
            return self._test_invoice(request)

        try:
            # 수신자 주소 배송 가능 여부 사전 검증 (실패해도 진행)
            validation = await self.validate_delivery_address(request.receiver_address)
            if validation.get("success") and not validation.get("deliverable"):
                return ShippingResponse(
                    success=False,
                    error=f"배송 불가능 주소: {validation.get('error', '확인 필요')}",
                )

            token = await self._get_token()
            invoice_no = await self._request_invoice_number(token)
            await self._register_booking(token, invoice_no, request)

            response = ShippingResponse(success=True, tracking_number=invoice_no)
            # 배송 지연 경고가 있으면 첨부
            if validation.get("warning"):
                response.error = validation["warning"]
            return response
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
