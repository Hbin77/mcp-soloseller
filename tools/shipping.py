"""송장 발급/등록 관련 MCP Tools"""
from typing import Any
from mcp.types import Tool

from auth import get_credentials
from models import CarrierType, ShippingRequest


def issue_invoice_tool() -> Tool:
    """issue_invoice 도구 정의"""
    return Tool(
        name="issue_invoice",
        description="택배사 API로 송장을 발급합니다",
        inputSchema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "채널 주문 ID"},
                "channel": {"type": "string", "enum": ["naver", "coupang"], "description": "주문 채널"},
                "carrier": {"type": "string", "enum": ["cj", "hanjin", "lotte", "logen", "epost"], "description": "택배사"},
                "receiver_name": {"type": "string", "description": "수령인명"},
                "receiver_phone": {"type": "string", "description": "수령인 연락처"},
                "receiver_address": {"type": "string", "description": "배송 주소"},
                "receiver_zipcode": {"type": "string", "description": "우편번호"},
                "product_name": {"type": "string", "description": "상품명"}
            },
            "required": ["order_id", "channel", "receiver_name", "receiver_phone", "receiver_address"]
        }
    )


def batch_issue_invoices_tool() -> Tool:
    """batch_issue_invoices 도구 정의"""
    return Tool(
        name="batch_issue_invoices",
        description="여러 주문에 대해 일괄로 송장을 발급합니다",
        inputSchema={
            "type": "object",
            "properties": {
                "orders": {"type": "array", "description": "발급할 주문 목록"},
                "carrier": {"type": "string", "enum": ["cj", "hanjin", "lotte", "logen", "epost"], "description": "택배사"}
            },
            "required": ["orders"]
        }
    )


def register_invoice_tool() -> Tool:
    """register_invoice 도구 정의"""
    return Tool(
        name="register_invoice",
        description="쇼핑몰(네이버/쿠팡)에 송장번호를 등록합니다",
        inputSchema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "채널 주문 ID"},
                "channel": {"type": "string", "enum": ["naver", "coupang"]},
                "tracking_number": {"type": "string", "description": "송장번호"},
                "carrier": {"type": "string", "enum": ["cj", "hanjin", "lotte", "logen", "epost"]}
            },
            "required": ["order_id", "channel", "tracking_number"]
        }
    )


def batch_register_invoices_tool() -> Tool:
    """batch_register_invoices 도구 정의"""
    return Tool(
        name="batch_register_invoices",
        description="여러 주문에 송장번호를 일괄 등록합니다",
        inputSchema={
            "type": "object",
            "properties": {
                "registrations": {"type": "array"}
            },
            "required": ["registrations"]
        }
    )


def get_available_carriers_tool() -> Tool:
    """get_available_carriers 도구 정의"""
    return Tool(
        name="get_available_carriers",
        description="설정된 택배사 목록과 상태를 조회합니다",
        inputSchema={"type": "object", "properties": {}}
    )


def get_channel_status_tool() -> Tool:
    """get_channel_status 도구 정의"""
    return Tool(
        name="get_channel_status",
        description="네이버/쿠팡 API 연결 상태를 확인합니다",
        inputSchema={"type": "object", "properties": {}}
    )


def _get_carrier_client(carrier_type: CarrierType, creds):
    """사용자 인증 정보로 택배사 클라이언트 생성"""
    from carriers.cj import CJClient
    from carriers.hanjin import HanjinClient
    from carriers.lotte import LotteClient
    from carriers.logen import LogenClient
    from carriers.epost import EpostClient

    if carrier_type == CarrierType.CJ:
        return CJClient(
            customer_id=creds.cj_customer_id or "",
            api_key=creds.cj_api_key or ""
        )
    elif carrier_type == CarrierType.HANJIN:
        return HanjinClient(
            customer_id=creds.hanjin_customer_id or "",
            api_key=creds.hanjin_api_key or ""
        )
    elif carrier_type == CarrierType.LOTTE:
        return LotteClient(
            customer_id=creds.lotte_customer_id or "",
            api_key=creds.lotte_api_key or ""
        )
    elif carrier_type == CarrierType.LOGEN:
        return LogenClient(
            customer_id=creds.logen_customer_id or "",
            api_key=creds.logen_api_key or ""
        )
    elif carrier_type == CarrierType.EPOST:
        return EpostClient(
            customer_id=creds.epost_customer_id or "",
            api_key=creds.epost_api_key or ""
        )
    return None


async def issue_invoice(
    order_id: str,
    channel: str,
    carrier: str,
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
    receiver_zipcode: str = "",
    product_name: str = "상품"
) -> dict[str, Any]:
    """송장 발급 실행"""
    creds = get_credentials()
    if not creds:
        return {"success": False, "error": "인증 정보가 없습니다. https://mcp.soloseller.cloud 에서 회원가입 후 토큰을 발급받아 사용해주세요."}

    try:
        carrier_type = CarrierType(carrier)
    except ValueError:
        carrier_type = CarrierType.CJ

    client = _get_carrier_client(carrier_type, creds)
    if not client:
        return {"success": False, "error": f"택배사 클라이언트 초기화 실패: {carrier}"}

    # 발송인 정보 확인
    if not creds.sender_configured:
        return {"success": False, "error": "발송인 정보가 설정되지 않았습니다. https://mcp.soloseller.cloud 의 설정 페이지에서 발송인 정보를 등록해주세요."}

    request = ShippingRequest(
        sender_name=creds.sender_name,
        sender_phone=creds.sender_phone,
        sender_address=creds.sender_address,
        sender_zipcode=creds.sender_zipcode or "",
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        receiver_address=receiver_address,
        receiver_zipcode=receiver_zipcode,
        product_name=product_name,
        order_id=order_id,
        channel_order_id=order_id
    )

    response = await client.request_invoice(request)

    return {
        "success": response.success,
        "tracking_number": response.tracking_number,
        "carrier": carrier,
        "carrier_name": carrier_type.display_name,
        "error": response.error
    }


async def batch_issue_invoices(
    orders: list[dict],
    carrier: str = "cj"
) -> dict[str, Any]:
    """일괄 송장 발급"""
    results = []
    issued = 0
    failed = 0

    for order in orders:
        result = await issue_invoice(
            order_id=order["order_id"],
            channel=order["channel"],
            carrier=carrier,
            receiver_name=order["receiver_name"],
            receiver_phone=order["receiver_phone"],
            receiver_address=order["receiver_address"],
            receiver_zipcode=order.get("receiver_zipcode", ""),
            product_name=order.get("product_name", "상품")
        )
        results.append({"order_id": order["order_id"], **result})
        if result["success"]:
            issued += 1
        else:
            failed += 1

    return {
        "success": failed == 0,
        "total": len(orders),
        "issued": issued,
        "failed": failed,
        "results": results
    }


async def register_invoice(
    order_id: str,
    channel: str,
    tracking_number: str,
    carrier: str = "cj"
) -> dict[str, Any]:
    """쇼핑몰에 송장 등록"""
    creds = get_credentials()
    if not creds:
        return {"success": False, "error": "인증 정보가 없습니다. https://mcp.soloseller.cloud 에서 회원가입 후 토큰을 발급받아 사용해주세요."}

    try:
        carrier_type = CarrierType(carrier)
    except ValueError:
        carrier_type = CarrierType.CJ

    if channel == "naver":
        if not creds.naver_configured:
            return {"success": False, "error": "네이버 API 키가 설정되지 않았습니다. https://mcp.soloseller.cloud 의 설정 페이지에서 API 키를 등록해주세요."}

        from channels.naver import NaverClient
        client = NaverClient(
            client_id=creds.naver_client_id,
            client_secret=creds.naver_client_secret,
            seller_id=creds.naver_seller_id
        )
        success = await client.register_invoice(
            order_id=order_id,
            tracking_number=tracking_number,
            carrier_code=carrier_type.marketplace_code
        )

    elif channel == "coupang":
        if not creds.coupang_configured:
            return {"success": False, "error": "쿠팡 API 키가 설정되지 않았습니다. https://mcp.soloseller.cloud 의 설정 페이지에서 API 키를 등록해주세요."}

        from channels.coupang import CoupangClient
        client = CoupangClient(
            vendor_id=creds.coupang_vendor_id,
            access_key=creds.coupang_access_key,
            secret_key=creds.coupang_secret_key
        )
        success = await client.register_invoice(
            order_id=order_id,
            tracking_number=tracking_number,
            carrier_code=carrier_type.marketplace_code
        )
    else:
        return {"success": False, "error": f"지원하지 않는 채널: {channel}"}

    return {
        "success": success,
        "message": "송장 등록 완료" if success else "송장 등록 실패",
        "order_id": order_id,
        "tracking_number": tracking_number
    }


async def batch_register_invoices(registrations: list[dict]) -> dict[str, Any]:
    """일괄 송장 등록"""
    results = []
    registered = 0
    failed = 0

    for reg in registrations:
        result = await register_invoice(
            order_id=reg["order_id"],
            channel=reg["channel"],
            tracking_number=reg["tracking_number"],
            carrier=reg.get("carrier", "cj")
        )
        results.append(result)
        if result["success"]:
            registered += 1
        else:
            failed += 1

    return {
        "success": failed == 0,
        "total": len(registrations),
        "registered": registered,
        "failed": failed,
        "results": results
    }


async def get_available_carriers() -> dict[str, Any]:
    """사용 가능한 택배사 목록"""
    creds = get_credentials()

    carriers = []
    for ct in CarrierType:
        configured = creds.is_carrier_configured(ct.value) if creds else False
        default_carrier = creds.default_carrier if creds else "cj"

        carriers.append({
            "code": ct.value,
            "name": ct.display_name,
            "configured": configured,
            "is_default": ct.value == default_carrier
        })

    return {"carriers": carriers}


async def get_channel_status() -> dict[str, Any]:
    """채널 연결 상태"""
    creds = get_credentials()

    return {
        "naver": {
            "configured": creds.naver_configured if creds else False,
            "seller_id": creds.naver_seller_id if creds and creds.naver_configured else None
        },
        "coupang": {
            "configured": creds.coupang_configured if creds else False,
            "vendor_id": creds.coupang_vendor_id if creds and creds.coupang_configured else None
        }
    }
