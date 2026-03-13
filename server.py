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
    import json
    from typing import Any

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    from tools.orders import get_orders
    from tools.shipping import issue_invoice, register_invoice, process_orders

    server = Server("soloseller-mvp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="get_orders",
                description="쿠팡에서 신규 주문을 조회합니다",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 7, "description": "조회 기간 (최근 N일)"}
                    }
                }
            ),
            Tool(
                name="issue_invoice",
                description="CJ대한통운 API로 송장을 발급합니다",
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
                description="쿠팡에 송장번호를 등록합니다",
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
                description="쿠팡 주문 조회 → CJ 송장 발급 → 쿠팡 송장 등록을 한번에 자동 처리합니다",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 7}
                    }
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name == "get_orders":
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
                result = await process_orders(days=arguments.get("days", 7))
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
