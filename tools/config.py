"""설정 상태 확인 MCP Tool"""
from typing import Any

from auth import get_credentials


async def check_config() -> dict[str, Any]:
    """현재 설정 상태를 확인합니다."""
    creds = get_credentials()

    if not creds:
        return {
            "configured": False,
            "message": "인증 정보가 없습니다. https://soloseller.cloud 에서 회원가입 후 토큰을 발급받아 사용해주세요.",
            "coupang_configured": False,
            "cj_configured": False,
            "sender_configured": False,
        }

    result: dict[str, Any] = {"configured": True, "integrations": {}}

    if creds.coupang_configured:
        result["integrations"]["coupang"] = {
            "configured": True,
            "message": "쿠팡 API가 설정되어 있습니다. 주문 조회 및 송장 등록이 가능합니다.",
        }
    else:
        result["integrations"]["coupang"] = {
            "configured": False,
            "message": "쿠팡 API 키가 설정되지 않았습니다. COUPANG_VENDOR_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY를 설정해주세요.",
        }

    if creds.cj_configured:
        result["integrations"]["cj"] = {
            "configured": True,
            "message": "CJ대한통운이 설정되어 있습니다. 송장 발급이 가능합니다.",
        }
    else:
        result["integrations"]["cj"] = {
            "configured": False,
            "message": "CJ대한통운 고객정보가 설정되지 않았습니다. CJ_CUSTOMER_ID, CJ_BIZ_REG_NUM을 설정해주세요. 미설정 시 테스트 모드로 동작합니다.",
        }

    if creds.sender_configured:
        result["integrations"]["sender"] = {
            "configured": True,
            "message": "발송인 정보가 설정되어 있습니다.",
        }
    else:
        result["integrations"]["sender"] = {
            "configured": False,
            "message": "발송인 정보가 설정되지 않았습니다. SENDER_NAME, SENDER_PHONE, SENDER_ADDRESS를 설정해주세요.",
        }

    result["coupang_configured"] = creds.coupang_configured
    result["cj_configured"] = creds.cj_configured
    result["sender_configured"] = creds.sender_configured

    return result
