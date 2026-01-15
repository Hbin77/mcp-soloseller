"""HTTP 기반 MCP 서버 (다중 사용자 지원)"""
import json
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from auth import (
    extract_credentials_from_headers,
    set_credentials,
    get_credentials,
    AUTH_HEADERS_SPEC
)
from models import CarrierType
from tools.orders import get_orders
from tools.shipping import (
    issue_invoice, batch_issue_invoices,
    register_invoice, batch_register_invoices,
    get_available_carriers, get_channel_status
)


class CredentialsMiddleware(BaseHTTPMiddleware):
    """HTTP 헤더에서 사용자 인증 정보를 추출하는 미들웨어"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            headers = dict(request.headers)
            credentials = extract_credentials_from_headers(headers)
            set_credentials(credentials)
        return await call_next(request)


app = FastAPI(
    title="Shop Automation MCP Server",
    description="쇼핑몰 주문 관리 및 송장 처리 자동화 MCP 서버",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CredentialsMiddleware)


# MCP Tools 정의
MCP_TOOLS = [
    {
        "name": "get_orders",
        "description": "네이버 스마트스토어와 쿠팡에서 신규 주문을 조회합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["all", "naver", "coupang"],
                    "default": "all",
                    "description": "조회할 채널"
                },
                "days": {
                    "type": "integer",
                    "default": 7,
                    "description": "조회 기간 (최근 N일)"
                }
            }
        }
    },
    {
        "name": "issue_invoice",
        "description": "택배사 API로 송장을 발급합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "주문 ID"},
                "channel": {"type": "string", "enum": ["naver", "coupang"]},
                "carrier": {"type": "string", "enum": ["cj", "hanjin", "lotte", "logen", "epost"]},
                "receiver_name": {"type": "string"},
                "receiver_phone": {"type": "string"},
                "receiver_address": {"type": "string"},
                "receiver_zipcode": {"type": "string"},
                "product_name": {"type": "string"}
            },
            "required": ["order_id", "channel", "receiver_name", "receiver_phone", "receiver_address"]
        }
    },
    {
        "name": "batch_issue_invoices",
        "description": "여러 주문에 대해 일괄로 송장을 발급합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "orders": {"type": "array", "description": "주문 목록"},
                "carrier": {"type": "string", "enum": ["cj", "hanjin", "lotte", "logen", "epost"]}
            },
            "required": ["orders"]
        }
    },
    {
        "name": "register_invoice",
        "description": "쇼핑몰에 송장번호를 등록합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "channel": {"type": "string", "enum": ["naver", "coupang"]},
                "tracking_number": {"type": "string"},
                "carrier": {"type": "string"}
            },
            "required": ["order_id", "channel", "tracking_number"]
        }
    },
    {
        "name": "batch_register_invoices",
        "description": "여러 주문에 송장번호를 일괄 등록합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "registrations": {"type": "array"}
            },
            "required": ["registrations"]
        }
    },
    {
        "name": "get_available_carriers",
        "description": "설정된 택배사 목록과 상태를 조회합니다",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_channel_status",
        "description": "네이버/쿠팡 API 연결 상태를 확인합니다",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


async def execute_tool(name: str, arguments: dict) -> dict:
    """MCP Tool 실행"""
    creds = get_credentials()
    default_carrier = creds.default_carrier if creds else "cj"

    if name == "get_orders":
        return await get_orders(
            channel=arguments.get("channel", "all"),
            days=arguments.get("days", 7)
        )
    elif name == "issue_invoice":
        return await issue_invoice(
            order_id=arguments["order_id"],
            channel=arguments["channel"],
            carrier=arguments.get("carrier", default_carrier),
            receiver_name=arguments["receiver_name"],
            receiver_phone=arguments["receiver_phone"],
            receiver_address=arguments["receiver_address"],
            receiver_zipcode=arguments.get("receiver_zipcode", ""),
            product_name=arguments.get("product_name", "상품")
        )
    elif name == "batch_issue_invoices":
        return await batch_issue_invoices(
            orders=arguments["orders"],
            carrier=arguments.get("carrier", default_carrier)
        )
    elif name == "register_invoice":
        return await register_invoice(
            order_id=arguments["order_id"],
            channel=arguments["channel"],
            tracking_number=arguments["tracking_number"],
            carrier=arguments.get("carrier", default_carrier)
        )
    elif name == "batch_register_invoices":
        return await batch_register_invoices(
            registrations=arguments["registrations"]
        )
    elif name == "get_available_carriers":
        return await get_available_carriers()
    elif name == "get_channel_status":
        return await get_channel_status()
    else:
        return {"error": f"Unknown tool: {name}"}


@app.get("/")
async def root():
    """서버 상태 확인"""
    return {
        "name": "shop-automation",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/mcp/info")
async def mcp_info():
    """MCP 서버 정보 (문서화용)"""
    return {
        "name": "shop-automation",
        "description": "쇼핑몰 주문 관리 및 송장 처리 자동화",
        "version": "1.0.0",
        "protocol": "mcp",
        "transport": "streamable-http",
        "authentication": AUTH_HEADERS_SPEC,
        "tools": [{"name": t["name"], "description": t["description"]} for t in MCP_TOOLS]
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 엔드포인트"""
    try:
        body = await request.json()
    except Exception:
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }),
            media_type="application/json",
            status_code=400
        )

    jsonrpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    try:
        # MCP 프로토콜 메서드 처리
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "shop-automation", "version": "1.0.0"}
            }

        elif method == "tools/list":
            result = {"tools": MCP_TOOLS}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            tool_result = await execute_tool(tool_name, tool_args)
            result = {
                "content": [{
                    "type": "text",
                    "text": json.dumps(tool_result, ensure_ascii=False, default=str, indent=2)
                }]
            }

        elif method == "notifications/initialized":
            return Response(status_code=204)

        else:
            return Response(
                content=json.dumps({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": jsonrpc_id
                }),
                media_type="application/json"
            )

        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "result": result,
                "id": jsonrpc_id
            }, ensure_ascii=False),
            media_type="application/json"
        )

    except Exception as e:
        return Response(
            content=json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": jsonrpc_id
            }),
            media_type="application/json",
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
