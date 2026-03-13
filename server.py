"""SoloSeller MCP 서버 - MVP (쿠팡 + CJ대한통운)

실행 방법:
- HTTP 모드 (다중 사용자): python server.py --http --port 8080
- stdio 모드 (로컬 전용): python server.py
"""
import argparse
import asyncio


def main():
    parser = argparse.ArgumentParser(description="SoloSeller MCP 서버 (쿠팡 + CJ대한통운)")
    parser.add_argument("--http", action="store_true", help="HTTP 모드로 실행")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 서버 호스트")
    parser.add_argument("--port", type=int, default=8080, help="HTTP 서버 포트")

    args = parser.parse_args()

    if args.http:
        import uvicorn
        from app import app
        print(f"HTTP 모드로 시작: http://{args.host}:{args.port}")
        print(f"API 문서: http://{args.host}:{args.port}/docs")
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        print("stdio 모드는 로컬 전용입니다. 다중 사용자 지원을 위해 --http 옵션을 사용하세요.")
        asyncio.run(run_stdio())


async def run_stdio():
    """stdio 모드 실행 (로컬 전용)"""
    import os
    import json
    from typing import Any

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    from auth import UserCredentials, set_credentials
    from tools.orders import get_orders
    from tools.shipping import issue_invoice, register_invoice, process_orders
    from tools.config import check_config

    # .env에서 인증 정보 로드
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    creds = UserCredentials(
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
    set_credentials(creds)

    server = Server("soloseller-mvp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="check_config",
                description="현재 설정 상태를 확인합니다. 어떤 기능이 사용 가능한지 점검할 때 사용하세요.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_orders",
                description="쿠팡에서 신규 주문을 조회합니다. 주문 확인만 하고 싶을 때 사용하세요.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 7, "description": "조회 기간 (최근 N일)"}
                    }
                }
            ),
            Tool(
                name="issue_invoice",
                description="CJ대한통운으로 송장을 발급합니다. 개별 주문을 수동 처리할 때 사용하세요.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "receiver_name": {"type": "string"},
                        "receiver_phone": {"type": "string"},
                        "receiver_address": {"type": "string"},
                        "receiver_zipcode": {"type": "string"},
                        "product_name": {"type": "string"}
                    },
                    "required": ["order_id", "receiver_name", "receiver_phone", "receiver_address"]
                }
            ),
            Tool(
                name="register_invoice",
                description="쿠팡에 송장번호를 등록합니다. issue_invoice로 발급받은 송장을 쿠팡에 입력할 때 사용하세요.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "tracking_number": {"type": "string"}
                    },
                    "required": ["order_id", "tracking_number"]
                }
            ),
            Tool(
                name="process_orders",
                description="주문 조회→송장 발급→쿠팡 등록을 한번에 처리합니다. dry_run=true로 미리보기 가능.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 7},
                        "dry_run": {"type": "boolean", "default": False, "description": "true면 미리보기만"}
                    }
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name == "check_config":
                result = await check_config()
            elif name == "get_orders":
                result = await get_orders(days=arguments.get("days", 7))
            elif name == "issue_invoice":
                result = await issue_invoice(
                    order_id=arguments["order_id"],
                    receiver_name=arguments["receiver_name"],
                    receiver_phone=arguments["receiver_phone"],
                    receiver_address=arguments["receiver_address"],
                    receiver_zipcode=arguments.get("receiver_zipcode", ""),
                    product_name=arguments.get("product_name", "상품")
                )
            elif name == "register_invoice":
                result = await register_invoice(
                    order_id=arguments["order_id"],
                    tracking_number=arguments["tracking_number"]
                )
            elif name == "process_orders":
                result = await process_orders(
                    days=arguments.get("days", 7),
                    dry_run=arguments.get("dry_run", False)
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, default=str, indent=2)
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, ensure_ascii=False)
            )]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    main()
