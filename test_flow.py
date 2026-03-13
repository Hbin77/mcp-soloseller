"""MVP 테스트 스크립트 - 쿠팡 주문 조회 → CJ 송장 발급 → 쿠팡 송장 등록

사용법:
  1. .env 파일에 쿠팡 API 키와 발송인 정보 입력
  2. python test_flow.py
"""
import asyncio
import json
import os

# .env 파일 로드
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

from auth import UserCredentials, set_credentials
from tools.orders import get_orders
from tools.shipping import issue_invoice, register_invoice


def get_creds_from_env() -> UserCredentials:
    return UserCredentials(
        coupang_vendor_id=os.environ.get("COUPANG_VENDOR_ID"),
        coupang_access_key=os.environ.get("COUPANG_ACCESS_KEY"),
        coupang_secret_key=os.environ.get("COUPANG_SECRET_KEY"),
        cj_customer_id=os.environ.get("CJ_CUSTOMER_ID"),
        cj_biz_reg_num=os.environ.get("CJ_BIZ_REG_NUM"),
        sender_name=os.environ.get("SENDER_NAME"),
        sender_phone=os.environ.get("SENDER_PHONE"),
        sender_zipcode=os.environ.get("SENDER_ZIPCODE"),
        sender_address=os.environ.get("SENDER_ADDRESS"),
    )


def pp(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def step1_get_orders():
    """1단계: 쿠팡 주문 조회"""
    print("\n" + "="*50)
    print("📦 1단계: 쿠팡 신규 주문 조회")
    print("="*50)

    result = await get_orders(days=7)
    pp(result)

    if not result.get("success"):
        print(f"\n❌ 실패: {result.get('error')}")
        return None

    orders = result.get("orders", [])
    print(f"\n✅ {len(orders)}건의 주문을 찾았습니다.")
    return orders


async def step2_issue_invoice(order: dict):
    """2단계: CJ대한통운 송장 발급"""
    print("\n" + "="*50)
    print(f"🏷️  2단계: 송장 발급 (주문: {order.get('order_id')})")
    print("="*50)

    result = await issue_invoice(
        order_id=order.get("order_id", ""),
        receiver_name=order.get("receiver_name", ""),
        receiver_phone=order.get("receiver_phone", ""),
        receiver_address=order.get("receiver_address", ""),
        receiver_zipcode=order.get("receiver_zipcode", ""),
        product_name=order.get("items", [{}])[0].get("product_name", "상품") if order.get("items") else "상품"
    )
    pp(result)

    if result.get("warning"):
        print(f"\n⚠️  {result['warning']}")

    if result.get("success"):
        print(f"\n✅ 송장번호: {result.get('tracking_number')}")
    else:
        print(f"\n❌ 실패: {result.get('error')}")

    return result


async def step3_register_invoice(order_id: str, tracking_number: str):
    """3단계: 쿠팡에 송장 등록"""
    print("\n" + "="*50)
    print(f"📝 3단계: 쿠팡에 송장 등록 ({tracking_number})")
    print("="*50)

    result = await register_invoice(
        order_id=order_id,
        tracking_number=tracking_number
    )
    pp(result)

    if result.get("success"):
        print("\n✅ 쿠팡에 송장 등록 완료!")
    else:
        print(f"\n❌ 실패: {result.get('error')}")

    return result


async def main():
    creds = get_creds_from_env()
    set_credentials(creds)

    # 설정 확인
    print("="*50)
    print("🔧 설정 확인")
    print("="*50)
    print(f"  쿠팡 API: {'✅ 설정됨' if creds.coupang_configured else '❌ 미설정'}")
    print(f"  CJ 대한통운: {'✅ 설정됨' if creds.cj_configured else '⚠️  테스트 모드'}")
    print(f"  발송인 정보: {'✅ 설정됨' if creds.sender_configured else '❌ 미설정'}")

    if not creds.coupang_configured:
        print("\n❌ .env 파일에 쿠팡 API 키를 입력해주세요.")
        print("   COUPANG_VENDOR_ID=")
        print("   COUPANG_ACCESS_KEY=")
        print("   COUPANG_SECRET_KEY=")
        return

    if not creds.sender_configured:
        print("\n❌ .env 파일에 발송인 정보를 입력해주세요.")
        print("   SENDER_NAME=")
        print("   SENDER_PHONE=")
        print("   SENDER_ADDRESS=")
        return

    # === 1단계: 주문 조회 ===
    orders = await step1_get_orders()

    if orders:
        # 실제 주문이 있으면 전체 플로우 진행
        first_order = orders[0]
        invoice_result = await step2_issue_invoice(first_order)

        if not invoice_result.get("success"):
            return

        tracking = invoice_result.get("tracking_number", "")

        if invoice_result.get("warning"):
            print("\n⚠️  테스트 모드 송장이므로 쿠팡 등록을 건너뜁니다.")
            return

        await step3_register_invoice(first_order["order_id"], tracking)

        print("\n" + "="*50)
        print("🎉 전체 플로우 완료!")
        print("="*50)
    else:
        # 주문이 없으면 CJ 송장 발급만 단독 테스트
        print("\n⚠️  조회된 주문이 없어 CJ 송장 발급 단독 테스트를 진행합니다.")
        import secrets as _secrets
        test_order = {
            "order_id": f"TEST_{_secrets.randbelow(1000000):06d}",
            "receiver_name": "테스트수신자",
            "receiver_phone": "010-1234-5678",
            "receiver_address": "서울특별시 강남구 테헤란로 123 테스트빌딩 301호",
            "receiver_zipcode": "06234",
            "items": [{"product_name": "테스트상품"}],
        }
        invoice_result = await step2_issue_invoice(test_order)
        if invoice_result.get("success"):
            print("\n" + "="*50)
            print("🎉 CJ 송장 발급 테스트 완료!")
            print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
