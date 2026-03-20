"""송장 발급/등록 MCP Tools - MVP (CJ대한통운 + 쿠팡)"""
import os
from collections import defaultdict
from typing import Any

from auth import get_credentials
from models import ShippingRequest
from carriers.cj import CJClient

# CJ 개발기 테스트 모드 (CJ_TEST_MODE=true 설정 시 개발 URL 사용)
CJ_TEST_MODE = os.environ.get("CJ_TEST_MODE", "").lower() in ("true", "1", "yes")

# CJClient 인스턴스 캐시 (고객ID+사업자번호 조합 키, 토큰 24시간 캐싱 활용)
_cj_clients: dict[tuple[str, str], CJClient] = {}


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

    customer_id = creds.cj_customer_id or ""
    biz_reg_num = creds.cj_biz_reg_num or ""
    has_real_creds = bool(customer_id and biz_reg_num)
    cache_key = (customer_id, biz_reg_num)

    # 자격증명 없는 테스트 모드는 캐시하지 않음 (사용자 간 격리)
    if not has_real_creds:
        client = CJClient(customer_id="", biz_reg_num="", test_mode=True)
    else:
        if cache_key not in _cj_clients:
            _cj_clients[cache_key] = CJClient(
                customer_id=customer_id,
                biz_reg_num=biz_reg_num,
                test_mode=CJ_TEST_MODE,
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
    try:
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
    finally:
        await client.http_client.aclose()


async def process_orders(days: int = 7, dry_run: bool = False) -> dict[str, Any]:
    """주문 조회 → 송장 발급 → 쿠팡 등록을 한번에 처리합니다"""
    from tools.orders import get_orders

    # 1. 주문 조회
    orders_result = await get_orders(days=days)
    if not orders_result.get("success"):
        return orders_result

    orders = orders_result.get("orders", [])
    if not orders:
        return {"success": True, "message": "처리할 신규 주문이 없습니다.", "processed": 0}

    # 수령인 기준 그룹핑 (합포장) - 이름 + 주소 + 전화번호로 그룹핑
    groups = defaultdict(list)
    for order in orders:
        name = order.get("receiver_name", "").strip()
        addr = " ".join(order.get("receiver_address", "").split())  # 공백 정규화
        phone = order.get("receiver_phone", "").strip()
        key = (name, addr, phone)
        groups[key].append(order)

    # dry_run: 미리보기 (합포장 그룹 표시)
    if dry_run:
        preview = []
        for (recv_name, _), group_orders in groups.items():
            for order in group_orders:
                items = order.get("items", [])
                product_summary = ", ".join(
                    item.get("product_name", "상품") for item in items
                ) if items else "상품"
                entry = {
                    "order_id": order.get("order_id"),
                    "receiver_name": order.get("receiver_name"),
                    "product_summary": product_summary,
                }
                if len(group_orders) > 1:
                    entry["consolidated_with"] = [
                        o.get("order_id") for o in group_orders
                        if o.get("order_id") != order.get("order_id")
                    ]
                preview.append(entry)

        consolidated_count = sum(1 for g in groups.values() if len(g) > 1)
        msg = f"{len(orders)}건의 주문이 처리 대기 중입니다."
        if consolidated_count:
            msg += f" ({consolidated_count}개 합포장 그룹 포함)"

        return {
            "success": True,
            "dry_run": True,
            "message": msg,
            "total": len(orders),
            "orders": preview,
        }

    # 2. 그룹별로 송장 발급 + 등록
    results = []
    processed = 0
    failed = 0
    creds = get_credentials()
    sender_data = {
        "sender_name": creds.sender_name if creds else "",
        "sender_phone": creds.sender_phone if creds else "",
        "sender_address": creds.sender_address if creds else "",
        "sender_zipcode": creds.sender_zipcode if creds else "",
    }

    for (_recv_name, _recv_addr, _recv_phone), group_orders in groups.items():
        if len(group_orders) == 1:
            # 단건 처리 (기존 로직)
            order = group_orders[0]
            order_id = order.get("order_id", "")
            receiver = order.get("receiver_name", "")
            phone = order.get("receiver_phone", "")
            address = order.get("receiver_address", "")
            zipcode = order.get("receiver_zipcode", "")
            items = order.get("items", [])
            product = items[0].get("product_name", "상품") if items else "상품"

            invoice_result = await issue_invoice(
                order_id=order_id,
                receiver_name=receiver,
                receiver_phone=phone,
                receiver_address=address,
                receiver_zipcode=zipcode,
                product_name=product
            )

            if not invoice_result.get("success"):
                results.append({"order_id": order_id, "status": "발급실패", **invoice_result})
                failed += 1
                continue

            tracking = invoice_result.get("tracking_number", "")
            is_test = "warning" in invoice_result
            label_data = {
                "receiver_name": receiver, "receiver_phone": phone,
                "receiver_address": address, "receiver_zipcode": zipcode,
                "product_name": product, **sender_data,
            }

            if is_test:
                results.append({"order_id": order_id, "status": "테스트", "tracking_number": tracking, "warning": "테스트 모드 - 쿠팡 등록 생략", **label_data})
                processed += 1
                continue

            reg_result = await register_invoice(order_id=order_id, tracking_number=tracking)
            if reg_result.get("success"):
                results.append({"order_id": order_id, "status": "완료", "tracking_number": tracking, **label_data})
                processed += 1
            else:
                results.append({"order_id": order_id, "status": "등록실패", "tracking_number": tracking, "error": reg_result.get("error"), **label_data})
                failed += 1
        else:
            # 합포장 처리: 같은 수령인의 여러 주문을 하나의 운송장으로
            order_ids = [o.get("order_id", "") for o in group_orders]
            first_order = group_orders[0]
            receiver = first_order.get("receiver_name", "")
            phone = first_order.get("receiver_phone", "")
            address = first_order.get("receiver_address", "")
            zipcode = first_order.get("receiver_zipcode", "")

            # ShippingRequest 목록 생성 (주문 내 모든 아이템 포함)
            shipping_requests = []
            product_names = []
            for order in group_orders:
                items = order.get("items", [])
                if not items:
                    items = [{"product_name": "상품", "shippingCount": 1}]
                for item in items:
                    pname = item.get("product_name", "상품")
                    qty = item.get("shippingCount", 1) or 1
                    product_names.append(pname)
                    shipping_requests.append(ShippingRequest(
                        sender_name=creds.sender_name if creds else "",
                        sender_phone=creds.sender_phone if creds else "",
                        sender_address=creds.sender_address if creds else "",
                        sender_zipcode=creds.sender_zipcode if creds else "",
                        receiver_name=receiver,
                        receiver_phone=phone,
                        receiver_address=address,
                        receiver_zipcode=zipcode,
                        product_name=pname,
                        quantity=qty,
                        order_id=order.get("order_id", ""),
                    ))

            # CJ 클라이언트로 합포장 발급
            customer_id = creds.cj_customer_id or "" if creds else ""
            biz_reg_num = creds.cj_biz_reg_num or "" if creds else ""
            has_real_creds = bool(customer_id and biz_reg_num)
            cache_key = (customer_id, biz_reg_num)

            if not has_real_creds:
                client = CJClient(customer_id="", biz_reg_num="", test_mode=True)
            else:
                if cache_key not in _cj_clients:
                    _cj_clients[cache_key] = CJClient(
                        customer_id=customer_id, biz_reg_num=biz_reg_num, test_mode=CJ_TEST_MODE,
                    )
                client = _cj_clients[cache_key]

            response = await client.request_consolidated_invoice(shipping_requests)

            if not response.success:
                for oid in order_ids:
                    results.append({"order_id": oid, "status": "합포장발급실패", "error": response.error})
                    failed += 1
                continue

            tracking = response.tracking_number or ""
            is_test = response.is_test
            product_summary = ", ".join(product_names)
            label_data = {
                "receiver_name": receiver, "receiver_phone": phone,
                "receiver_address": address, "receiver_zipcode": zipcode,
                "product_name": product_summary, **sender_data,
            }

            # 각 주문에 대해 쿠팡에 동일 송장 등록
            for oid in order_ids:
                if is_test:
                    results.append({"order_id": oid, "status": "테스트(합포장)", "tracking_number": tracking, "consolidated_orders": order_ids, "warning": "테스트 모드 - 쿠팡 등록 생략", **label_data})
                    processed += 1
                    continue

                reg_result = await register_invoice(order_id=oid, tracking_number=tracking)
                if reg_result.get("success"):
                    results.append({"order_id": oid, "status": "완료(합포장)", "tracking_number": tracking, "consolidated_orders": order_ids, **label_data})
                    processed += 1
                else:
                    results.append({"order_id": oid, "status": "등록실패(합포장)", "tracking_number": tracking, "consolidated_orders": order_ids, "error": reg_result.get("error"), **label_data})
                    failed += 1

    consolidated_groups = sum(1 for g in groups.values() if len(g) > 1)
    return {
        "success": failed == 0,
        "total": len(orders),
        "processed": processed,
        "failed": failed,
        "consolidated_groups": consolidated_groups,
        "results": results
    }
