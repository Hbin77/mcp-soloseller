"""주문 조회 MCP Tool - MVP (쿠팡 전용)"""
from typing import Any

from auth import get_credentials


async def get_orders(days: int = 7) -> dict[str, Any]:
    """쿠팡에서 신규 주문을 조회합니다"""
    creds = get_credentials()
    if not creds:
        return {"success": False, "error": "인증 정보가 없습니다. https://soloseller.cloud 에서 토큰을 발급받아 사용해주세요."}

    if not creds.coupang_configured:
        return {"success": False, "error": "쿠팡 API 키가 설정되지 않았습니다. https://soloseller.cloud/settings 에서 등록해주세요."}

    try:
        from channels.coupang import CoupangClient
        client = CoupangClient(
            vendor_id=creds.coupang_vendor_id,
            access_key=creds.coupang_access_key,
            secret_key=creds.coupang_secret_key
        )
        orders = await client.get_new_orders(days=days)

        return {
            "success": True,
            "total_count": len(orders),
            "orders": orders
        }
    except Exception as e:
        return {"success": False, "error": f"쿠팡 주문 조회 실패: {str(e)}"}
