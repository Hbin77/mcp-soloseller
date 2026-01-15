"""쇼핑몰 자동화 MCP 서버

실행 방법:
- HTTP 모드 (다중 사용자): python server.py --http --port 8080
- stdio 모드 (로컬 전용): python server.py
"""
import argparse
import asyncio


def main():
    parser = argparse.ArgumentParser(description="쇼핑몰 자동화 MCP 서버")
    parser.add_argument("--http", action="store_true", help="HTTP 모드로 실행")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 서버 호스트")
    parser.add_argument("--port", type=int, default=8080, help="HTTP 서버 포트")

    args = parser.parse_args()

    if args.http:
        # HTTP 모드 (다중 사용자 지원)
        import uvicorn
        from app import app
        print(f"HTTP 모드로 시작: http://{args.host}:{args.port}")
        print("API 문서: http://{args.host}:{args.port}/docs")
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        # stdio 모드 (로컬 전용)
        print("stdio 모드는 로컬 전용입니다. 다중 사용자 지원을 위해 --http 옵션을 사용하세요.")
        asyncio.run(run_stdio())


async def run_stdio():
    """stdio 모드 실행 (로컬 전용)"""
    import json
    from typing import Any

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    from tools.orders import get_orders_tool, get_orders
    from tools.shipping import (
        issue_invoice_tool, issue_invoice,
        batch_issue_invoices_tool, batch_issue_invoices,
        register_invoice_tool, register_invoice,
        batch_register_invoices_tool, batch_register_invoices,
        get_available_carriers_tool, get_available_carriers,
        get_channel_status_tool, get_channel_status
    )

    server = Server("shop-automation")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            get_orders_tool(),
            issue_invoice_tool(),
            batch_issue_invoices_tool(),
            register_invoice_tool(),
            batch_register_invoices_tool(),
            get_available_carriers_tool(),
            get_channel_status_tool(),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name == "get_orders":
                result = await get_orders(
                    channel=arguments.get("channel", "all"),
                    days=arguments.get("days", 7)
                )
            elif name == "issue_invoice":
                result = await issue_invoice(
                    order_id=arguments["order_id"],
                    channel=arguments["channel"],
                    carrier=arguments.get("carrier", "cj"),
                    receiver_name=arguments["receiver_name"],
                    receiver_phone=arguments["receiver_phone"],
                    receiver_address=arguments["receiver_address"],
                    receiver_zipcode=arguments.get("receiver_zipcode", ""),
                    product_name=arguments.get("product_name", "상품")
                )
            elif name == "batch_issue_invoices":
                result = await batch_issue_invoices(
                    orders=arguments["orders"],
                    carrier=arguments.get("carrier", "cj")
                )
            elif name == "register_invoice":
                result = await register_invoice(
                    order_id=arguments["order_id"],
                    channel=arguments["channel"],
                    tracking_number=arguments["tracking_number"],
                    carrier=arguments.get("carrier", "cj")
                )
            elif name == "batch_register_invoices":
                result = await batch_register_invoices(
                    registrations=arguments["registrations"]
                )
            elif name == "get_available_carriers":
                result = await get_available_carriers()
            elif name == "get_channel_status":
                result = await get_channel_status()
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
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    main()
