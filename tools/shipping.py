"""송장 발급/등록 MCP Tools - MVP (CJ대한통운 + 쿠팡)"""
from typing import Any

from auth import get_credentials
from models import ShippingRequest
from carriers.cj import CJClient

# CJClient 인스턴스 캐시 (고객ID별, 토큰 24시간 캐싱 활용)
_cj_clients: dict[str, CJClient] = {}


async def issue_invoice(
    order_id: str,
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
    receiver_zipcode: str = "",
    product_name: str = "상품"
) -> dict[str, Any]:
    """CJ대한통운으로 송장을 발급합니다"""
    creds = get_credentials()
    if not creds:
        return {"success": False, "error": "인증 정보가 없습니다. https://soloseller.cloud 에서 토큰을 발급받아 사용해주세요."}

    if not creds.sender_configured:
        return {"success": False, "error": "발송인 정보가 설정되지 않았습니다. https://soloseller.cloud/settings 에서 등록해주세요."}

    cache_key = creds.cj_customer_id or ""
    if cache_key not in _cj_clients:
        _cj_clients[cache_key] = CJClient(
            customer_id=creds.cj_customer_id or "",
            biz_reg_num=creds.cj_biz_reg_num or "",
        )
    client = _cj_clients[cache_key]

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
        order_id=order_id
    )

    response = await client.request_invoice(request)
    result = {
        "success": response.success,
        "tracking_number": response.tracking_number,
        "carrier": "CJ대한통운",
        "error": response.error
    }
    if response.is_test:
        result["warning"] = "테스트 모드 송장입니다. 실제 배송에 사용할 수 없습니다."
    return result


async def register_invoice(
    order_id: str,
    tracking_number: str
) -> dict[str, Any]:
    """쿠팡에 송장번호를 등록합니다"""
    creds = get_credentials()
    if not creds:
        return {"success": False, "error": "인증 정보가 없습니다."}

    if not creds.coupang_configured:
        return {"success": False, "error": "쿠팡 API 키가 설정되지 않았습니다. https://soloseller.cloud/settings 에서 등록해주세요."}

    from channels.coupang import CoupangClient
    client = CoupangClient(
        vendor_id=creds.coupang_vendor_id,
        access_key=creds.coupang_access_key,
        secret_key=creds.coupang_secret_key
    )
    success = await client.register_invoice(
        order_id=order_id,
        tracking_number=tracking_number,
        carrier_code="CJGLS"
    )

    return {
        "success": success,
        "message": "쿠팡에 송장 등록 완료" if success else "쿠팡 송장 등록 실패",
        "order_id": order_id,
        "tracking_number": tracking_number
    }


async def process_orders(days: int = 7) -> dict[str, Any]:
    """주문 조회 → 송장 발급 → 쿠팡 등록을 한번에 처리합니다"""
    from tools.orders import get_orders

    # 1. 주문 조회
    orders_result = await get_orders(days=days)
    if not orders_result.get("success"):
        return orders_result

    orders = orders_result.get("orders", [])
    if not orders:
        return {"success": True, "message": "처리할 신규 주문이 없습니다.", "processed": 0}

    # 2. 각 주문에 대해 송장 발급 + 등록
    results = []
    processed = 0
    failed = 0

    for order in orders:
        order_id = order.get("order_id", "")
        receiver = order.get("receiver_name", "")
        phone = order.get("receiver_phone", "")
        address = order.get("receiver_address", "")
        zipcode = order.get("receiver_zipcode", "")
        product = ""
        items = order.get("items", [])
        if items:
            product = items[0].get("product_name", "상품")

        # 송장 발급
        invoice_result = await issue_invoice(
            order_id=order_id,
            receiver_name=receiver,
            receiver_phone=phone,
            receiver_address=address,
            receiver_zipcode=zipcode,
            product_name=product or "상품"
        )

        if not invoice_result.get("success"):
            results.append({"order_id": order_id, "status": "발급실패", **invoice_result})
            failed += 1
            continue

        tracking = invoice_result.get("tracking_number", "")
        is_test = "warning" in invoice_result

        # 테스트 모드 송장은 쿠팡에 등록하지 않음
        if is_test:
            results.append({
                "order_id": order_id,
                "status": "테스트",
                "tracking_number": tracking,
                "warning": "테스트 모드 - 쿠팡 등록 생략"
            })
            processed += 1
            continue

        # 쿠팡에 송장 등록
        reg_result = await register_invoice(
            order_id=order_id,
            tracking_number=tracking
        )

        if reg_result.get("success"):
            results.append({
                "order_id": order_id,
                "status": "완료",
                "tracking_number": tracking
            })
            processed += 1
        else:
            results.append({
                "order_id": order_id,
                "status": "등록실패",
                "tracking_number": tracking,
                "error": reg_result.get("error")
            })
            failed += 1

    return {
        "success": failed == 0,
        "total": len(orders),
        "processed": processed,
        "failed": failed,
        "results": results
    }
