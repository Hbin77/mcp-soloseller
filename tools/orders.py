"""주문 조회 관련 MCP Tools"""
from typing import Any
from mcp.types import Tool

from auth import get_credentials


def get_orders_tool() -> Tool:
    """get_orders 도구 정의"""
    return Tool(
        name="get_orders",
        description="네이버 스마트스토어와 쿠팡에서 신규 주문을 조회합니다",
        inputSchema={
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["all", "naver", "coupang"],
                    "default": "all",
                    "description": "조회할 채널 (all: 전체, naver: 네이버만, coupang: 쿠팡만)"
                },
                "days": {
                    "type": "integer",
                    "default": 7,
                    "description": "조회 기간 (최근 N일)"
                }
            }
        }
    )


async def get_orders(channel: str = "all", days: int = 7) -> dict[str, Any]:
    """주문 조회 실행"""
    from channels.naver import NaverClient
    from channels.coupang import CoupangClient

    # 사용자 인증 정보 가져오기
    creds = get_credentials()

    result = {
        "success": True,
        "total_count": 0,
        "naver_count": 0,
        "coupang_count": 0,
        "orders": []
    }

    errors = []

    # 네이버 주문 조회
    if channel in ["all", "naver"]:
        if creds and creds.naver_configured:
            try:
                naver = NaverClient(
                    client_id=creds.naver_client_id,
                    client_secret=creds.naver_client_secret,
                    seller_id=creds.naver_seller_id
                )
                naver_orders = await naver.get_new_orders(days=days)
                result["naver_count"] = len(naver_orders)
                result["orders"].extend(naver_orders)
            except Exception as e:
                errors.append(f"네이버 조회 실패: {str(e)}")
        else:
            errors.append("네이버 API 키가 설정되지 않았습니다. https://mcp.soloseller.cloud 에서 회원가입 후 설정 페이지에서 API 키를 등록해주세요.")

    # 쿠팡 주문 조회
    if channel in ["all", "coupang"]:
        if creds and creds.coupang_configured:
            try:
                coupang = CoupangClient(
                    vendor_id=creds.coupang_vendor_id,
                    access_key=creds.coupang_access_key,
                    secret_key=creds.coupang_secret_key
                )
                coupang_orders = await coupang.get_new_orders(days=days)
                result["coupang_count"] = len(coupang_orders)
                result["orders"].extend(coupang_orders)
            except Exception as e:
                errors.append(f"쿠팡 조회 실패: {str(e)}")
        else:
            errors.append("쿠팡 API 키가 설정되지 않았습니다. https://mcp.soloseller.cloud 에서 회원가입 후 설정 페이지에서 API 키를 등록해주세요.")

    result["total_count"] = len(result["orders"])

    if errors:
        result["errors"] = errors

    return result
