"""HTTP 기반 MCP 서버 (다중 사용자 지원) + 웹 UI - MVP (쿠팡 + CJ대한통운)"""
import html
import json
import secrets
import os
import httpx
from typing import Any, Optional

from fastapi import FastAPI, Request, Response, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from auth import extract_credentials_auto, set_credentials, get_credentials, AUTH_HEADERS_SPEC
from tools.orders import get_orders
from tools.shipping import issue_invoice, register_invoice, process_orders
import database as db
from email_service import send_verification_email

# Cloudflare Turnstile 설정
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

# 세션 저장소 (메모리 - 프로덕션에서는 Redis 등 사용 권장)
sessions: dict[str, int] = {}
session_flash: dict[str, dict] = {}
pending_registrations: dict[str, dict] = {}


def get_session_user(session_id: Optional[str]) -> Optional[int]:
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None


def create_session(user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = user_id
    return session_id


async def verify_turnstile(token: str) -> bool:
    if not TURNSTILE_SECRET_KEY:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": TURNSTILE_SECRET_KEY, "response": token}
            )
            return response.json().get("success", False)
    except Exception:
        return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class CredentialsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            headers = dict(request.headers)
            credentials = extract_credentials_auto(headers)
            set_credentials(credentials)
        try:
            return await call_next(request)
        finally:
            if request.url.path.startswith("/mcp"):
                set_credentials(None)


app = FastAPI(
    title="SoloSeller MCP Server",
    description="쿠팡 주문 관리 및 CJ대한통운 송장 자동화 MCP 서버",
    version="2.0.0-mvp"
)

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "https://soloseller.cloud").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(CredentialsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ============ HTML 템플릿 ============

OG_TAGS = """
<meta property="og:title" content="SoloSeller - 쿠팡 송장 자동화 MCP">
<meta property="og:description" content="쿠팡 판매자를 위한 주문 관리 및 송장 자동화 MCP 서버">
<meta property="og:image" content="https://soloseller.cloud/static/logo.png">
<meta property="og:url" content="https://soloseller.cloud">
<meta property="og:type" content="website">
<link rel="icon" type="image/png" href="/static/logo.png">
"""

BASE_STYLE = """
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f0f; color: #e0e0e0; min-height: 100vh; }
    .container { max-width: 600px; margin: 0 auto; padding: 40px 20px; }
    h1 { color: #fff; margin-bottom: 30px; font-size: 28px; }
    h2 { color: #fff; margin: 30px 0 20px; font-size: 20px; border-bottom: 1px solid #333; padding-bottom: 10px; }
    .card { background: #1a1a1a; border-radius: 12px; padding: 24px; margin-bottom: 20px; }
    label { display: block; margin-bottom: 6px; color: #aaa; font-size: 14px; }
    input[type="text"], input[type="password"], input[type="email"] {
        width: 100%; padding: 12px; border: 1px solid #333; border-radius: 8px;
        background: #0f0f0f; color: #fff; font-size: 14px; margin-bottom: 16px;
    }
    input:focus { outline: none; border-color: #4a9eff; }
    button, .btn {
        display: inline-block; padding: 12px 24px; background: #4a9eff; color: #fff;
        border: none; border-radius: 8px; font-size: 14px; cursor: pointer;
        text-decoration: none; text-align: center;
    }
    button:hover, .btn:hover { background: #3a8eef; }
    .btn-danger { background: #ef4444; }
    .btn-danger:hover { background: #dc2626; }
    .error { background: #7f1d1d; color: #fca5a5; padding: 12px; border-radius: 8px; margin-bottom: 20px; }
    .success { background: #14532d; color: #86efac; padding: 12px; border-radius: 8px; margin-bottom: 20px; }
    .token-box { background: #0f0f0f; padding: 12px; border-radius: 8px; font-family: monospace; word-break: break-all; margin: 10px 0; font-size: 13px; }
    .token-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; background: #0f0f0f; border-radius: 8px; margin-bottom: 10px; }
    .token-name { font-weight: bold; }
    .token-meta { font-size: 12px; color: #888; }
    a { color: #4a9eff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .nav { margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #333; }
    .nav a { margin-right: 20px; }
    .field-group-title { font-size: 16px; color: #4a9eff; margin-bottom: 16px; }
    small { color: #666; font-size: 12px; }
</style>
"""


def render_page(title: str, content: str, user_id: Optional[int] = None) -> str:
    nav = ""
    if user_id:
        user = db.get_user_by_id(user_id)
        email = html.escape(user["email"]) if user else ""
        nav = f"""
        <div class="nav">
            <a href="/settings">API 설정</a>
            <a href="/tokens">토큰 관리</a>
            <span style="float: right; color: #888;">{email} | <a href="/logout">로그아웃</a></span>
        </div>
        """
    return f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - SoloSeller MCP</title>
    {OG_TAGS}{BASE_STYLE}</head>
    <body><div class="container">{nav}
    <div style="text-align: center; margin-bottom: 20px;">
        <img src="/static/logo.png" alt="SoloSeller" style="height: 60px;">
    </div>
    <h1 style="text-align: center;">{title}</h1>{content}</div></body></html>
    """


# ============ MCP Tools 정의 ============

MCP_TOOLS = [
    {
        "name": "get_orders",
        "description": "쿠팡에서 신규 주문을 조회합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "조회 기간 (최근 N일)"}
            }
        }
    },
    {
        "name": "issue_invoice",
        "description": "CJ대한통운 API로 송장을 발급합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "쿠팡 주문 ID"},
                "receiver_name": {"type": "string", "description": "수령인명"},
                "receiver_phone": {"type": "string", "description": "수령인 연락처"},
                "receiver_address": {"type": "string", "description": "배송 주소"},
                "receiver_zipcode": {"type": "string", "description": "우편번호"},
                "product_name": {"type": "string", "description": "상품명"}
            },
            "required": ["order_id", "receiver_name", "receiver_phone", "receiver_address"]
        }
    },
    {
        "name": "register_invoice",
        "description": "쿠팡에 송장번호를 등록합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "쿠팡 주문 ID"},
                "tracking_number": {"type": "string", "description": "송장번호"}
            },
            "required": ["order_id", "tracking_number"]
        }
    },
    {
        "name": "process_orders",
        "description": "쿠팡 주문 조회 → CJ 송장 발급 → 쿠팡 송장 등록을 한번에 자동 처리합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "조회 기간 (최근 N일)"}
            }
        }
    }
]


async def execute_tool(name: str, arguments: dict) -> dict:
    """MCP Tool 실행"""
    if name == "get_orders":
        return await get_orders(days=arguments.get("days", 7))
    elif name == "issue_invoice":
        return await issue_invoice(
            order_id=arguments["order_id"],
            receiver_name=arguments["receiver_name"],
            receiver_phone=arguments["receiver_phone"],
            receiver_address=arguments["receiver_address"],
            receiver_zipcode=arguments.get("receiver_zipcode", ""),
            product_name=arguments.get("product_name", "상품")
        )
    elif name == "register_invoice":
        return await register_invoice(
            order_id=arguments["order_id"],
            tracking_number=arguments["tracking_number"]
        )
    elif name == "process_orders":
        return await process_orders(days=arguments.get("days", 7))
    return {"error": f"Unknown tool: {name}"}


# ============ 기본 엔드포인트 ============

@app.get("/")
async def root():
    return {"name": "soloseller-mvp", "version": "2.0.0", "status": "running"}


@app.get("/mcp/info")
async def mcp_info():
    return {
        "name": "soloseller-mvp",
        "description": "쿠팡 주문 관리 + CJ대한통운 송장 자동화",
        "version": "2.0.0",
        "protocol": "mcp",
        "transport": "streamable-http",
        "authentication": AUTH_HEADERS_SPEC,
        "tools": [{"name": t["name"], "description": t["description"]} for t in MCP_TOOLS]
    }


@app.get("/mcp")
async def mcp_get():
    return {
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "soloseller-mvp", "version": "2.0.0"}
        },
        "id": None
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return Response(
            content=json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}),
            media_type="application/json", status_code=400
        )

    jsonrpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "soloseller-mvp", "version": "2.0.0"}
            }
        elif method == "tools/list":
            result = {"tools": MCP_TOOLS}
        elif method == "tools/call":
            tool_result = await execute_tool(params.get("name", ""), params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(tool_result, ensure_ascii=False, default=str, indent=2)}]}
        elif method == "notifications/initialized":
            return Response(status_code=204)
        else:
            return Response(
                content=json.dumps({"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": jsonrpc_id}),
                media_type="application/json"
            )

        return Response(
            content=json.dumps({"jsonrpc": "2.0", "result": result, "id": jsonrpc_id}, ensure_ascii=False),
            media_type="application/json"
        )
    except Exception as e:
        print(f"[MCP] Internal error: {e}")
        return Response(
            content=json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal server error"}, "id": jsonrpc_id}),
            media_type="application/json", status_code=500
        )


# ============ 웹 UI - 인증 ============

def get_turnstile_widget() -> str:
    if not TURNSTILE_SITE_KEY:
        return ""
    return f'''
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
    <div class="cf-turnstile" data-sitekey="{TURNSTILE_SITE_KEY}" data-theme="dark" style="margin-bottom: 16px;"></div>
    '''


@app.get("/register", response_class=HTMLResponse)
async def register_page(error: str = "", success: str = ""):
    msg = f'<div class="error">{html.escape(error)}</div>' if error else ""
    msg += f'<div class="success">{html.escape(success)}</div>' if success else ""
    turnstile = get_turnstile_widget()
    content = f"""
    {msg}
    <div class="card">
        <form method="post">
            <label>이메일</label>
            <input type="email" name="email" required placeholder="example@email.com">
            <label>비밀번호</label>
            <input type="password" name="password" required placeholder="8자 이상">
            <label>비밀번호 확인</label>
            <input type="password" name="password2" required>
            {turnstile}
            <button type="submit">회원가입</button>
        </form>
        <p style="margin-top: 20px;">이미 계정이 있나요? <a href="/login">로그인</a></p>
    </div>
    """
    return HTMLResponse(render_page("회원가입", content))


@app.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request, email: str = Form(...), password: str = Form(...), password2: str = Form(...)):
    form = await request.form()
    turnstile_token = form.get("cf-turnstile-response", "")
    if not await verify_turnstile(turnstile_token):
        return RedirectResponse("/register?error=로봇 확인에 실패했습니다", status_code=303)
    if len(password) < 8:
        return RedirectResponse("/register?error=비밀번호는 8자 이상이어야 합니다", status_code=303)
    if password != password2:
        return RedirectResponse("/register?error=비밀번호가 일치하지 않습니다", status_code=303)

    existing_user = db.get_user_by_email(email)
    if existing_user:
        return RedirectResponse("/register?error=이미 등록된 이메일입니다", status_code=303)

    code = db.create_verification_code(email, "register")
    if not send_verification_email(email, code):
        return RedirectResponse("/register?error=인증 이메일 발송에 실패했습니다", status_code=303)

    reg_token = secrets.token_urlsafe(32)
    pending_registrations[reg_token] = {"email": email, "password_hash": db.hash_password(password)}

    return RedirectResponse(f"/verify-email?token={reg_token}&email={email}", status_code=303)


@app.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(token: str = "", email: str = "", error: str = ""):
    if not token or token not in pending_registrations:
        return RedirectResponse("/register?error=유효하지 않은 요청입니다", status_code=303)

    safe_email = html.escape(email)
    safe_token = html.escape(token)
    msg = f'<div class="error">{html.escape(error)}</div>' if error else ""
    content = f"""
    {msg}
    <div class="card">
        <p style="margin-bottom: 20px; color: #aaa;">
            <strong>{safe_email}</strong>으로 인증 코드를 발송했습니다.<br>
            이메일을 확인하고 6자리 코드를 입력해주세요.
        </p>
        <form method="post">
            <input type="hidden" name="token" value="{safe_token}">
            <input type="hidden" name="email" value="{safe_email}">
            <label>인증 코드</label>
            <input type="text" name="code" required placeholder="000000" maxlength="6"
                   style="font-size: 24px; letter-spacing: 8px; text-align: center;">
            <button type="submit">인증 확인</button>
        </form>
        <p style="margin-top: 20px; font-size: 14px; color: #888;">
            코드를 받지 못하셨나요? <a href="/resend-code?token={safe_token}&email={safe_email}">다시 보내기</a>
        </p>
    </div>
    """
    return HTMLResponse(render_page("이메일 인증", content))


@app.post("/verify-email")
async def verify_email_submit(token: str = Form(...), email: str = Form(...), code: str = Form(...)):
    if token not in pending_registrations:
        return RedirectResponse("/register?error=유효하지 않은 요청입니다", status_code=303)
    if not db.verify_code(email, code, "register"):
        return RedirectResponse(f"/verify-email?token={token}&email={email}&error=인증 코드가 올바르지 않습니다", status_code=303)

    reg_data = pending_registrations.pop(token)
    user_id = db.create_user_with_hash(reg_data["email"], reg_data["password_hash"])
    if not user_id:
        return RedirectResponse("/register?error=회원가입에 실패했습니다", status_code=303)

    db.mark_email_verified(email)
    return RedirectResponse("/login?success=회원가입이 완료되었습니다! 로그인해주세요", status_code=303)


@app.get("/resend-code")
async def resend_code(token: str = "", email: str = ""):
    if token not in pending_registrations:
        return RedirectResponse("/register?error=유효하지 않은 요청입니다", status_code=303)
    code = db.create_verification_code(email, "register")
    send_verification_email(email, code)
    return RedirectResponse(f"/verify-email?token={token}&email={email}", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = "", success: str = ""):
    msg = f'<div class="error">{html.escape(error)}</div>' if error else ""
    msg += f'<div class="success">{html.escape(success)}</div>' if success else ""
    turnstile = get_turnstile_widget()
    content = f"""
    {msg}
    <div class="card">
        <form method="post">
            <label>이메일</label>
            <input type="email" name="email" required>
            <label>비밀번호</label>
            <input type="password" name="password" required>
            {turnstile}
            <button type="submit">로그인</button>
        </form>
        <p style="margin-top: 20px;">계정이 없나요? <a href="/register">회원가입</a></p>
    </div>
    """
    return HTMLResponse(render_page("로그인", content))


@app.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    form = await request.form()
    turnstile_token = form.get("cf-turnstile-response", "")
    if not await verify_turnstile(turnstile_token):
        return RedirectResponse("/login?error=로봇 확인에 실패했습니다", status_code=303)

    user_id = db.authenticate_user(email, password)
    if not user_id:
        return RedirectResponse("/login?error=이메일 또는 비밀번호가 잘못되었습니다", status_code=303)
    if not db.is_email_verified(email):
        return RedirectResponse("/login?error=이메일 인증이 필요합니다", status_code=303)

    session_id = create_session(user_id)
    response = RedirectResponse("/settings", status_code=303)
    response.set_cookie("session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400*30)
    return response


@app.get("/logout")
async def logout(session: Optional[str] = Cookie(None)):
    if session:
        sessions.pop(session, None)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


# ============ 웹 UI - API 설정 ============

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(session: Optional[str] = Cookie(None), success: str = ""):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    creds = db.get_user_credentials(user_id) or {}
    msg = f'<div class="success">{html.escape(success)}</div>' if success else ""

    def field(name: str, label: str, type: str = "text"):
        val = html.escape(creds.get(name) or "", quote=True)
        return f'<label>{label}</label><input type="{type}" name="{name}" value="{val}">'

    content = f"""
    {msg}
    <form method="post">
        <div class="card">
            <div class="field-group-title">쿠팡 WING</div>
            {field("coupang_vendor_id", "Vendor ID")}
            {field("coupang_access_key", "Access Key")}
            {field("coupang_secret_key", "Secret Key", "password")}
        </div>

        <div class="card">
            <div class="field-group-title">CJ대한통운</div>
            {field("cj_customer_id", "고객 ID")}
            {field("cj_biz_reg_num", "사업자등록번호")}
        </div>

        <div class="card">
            <div class="field-group-title">발송인 정보</div>
            {field("sender_name", "발송인 이름")}
            {field("sender_phone", "연락처")}
            {field("sender_zipcode", "우편번호")}
            {field("sender_address", "주소")}
        </div>

        <button type="submit">저장</button>
    </form>
    """
    return HTMLResponse(render_page("API 설정", content, user_id))


@app.post("/settings")
async def settings_submit(request: Request, session: Optional[str] = Cookie(None)):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    credentials = {k: v for k, v in form.items()}
    db.update_user_credentials(user_id, credentials)
    return RedirectResponse("/settings?success=저장되었습니다", status_code=303)


# ============ 웹 UI - 토큰 관리 ============

@app.get("/tokens", response_class=HTMLResponse)
async def tokens_page(session: Optional[str] = Cookie(None)):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    tokens = db.get_user_tokens(user_id)

    flash = session_flash.pop(session, {}) if session else {}
    if len(session_flash) > 1000:
        session_flash.clear()
    new_token = flash.get("new_token", "")

    new_token_html = ""
    if new_token:
        new_token_html = f"""
        <div class="success">
            <strong>새 토큰이 생성되었습니다!</strong><br>
            <small>이 토큰은 다시 표시되지 않으니 안전한 곳에 저장하세요.</small>
            <div class="token-box">{html.escape(new_token)}</div>
        </div>
        """

    token_list = ""
    for t in tokens:
        status = "활성" if t["is_active"] else "비활성"
        status_color = "#86efac" if t["is_active"] else "#fca5a5"
        last_used = t["last_used_at"] or "사용 안 함"
        token_list += f"""
        <div class="token-item">
            <div>
                <div class="token-name">{html.escape(t["name"])}</div>
                <div class="token-meta">생성: {t["created_at"][:10]} | 마지막 사용: {last_used}</div>
            </div>
            <div>
                <span style="color: {status_color}; margin-right: 10px;">{status}</span>
                <form method="post" action="/tokens/delete" style="display: inline;">
                    <input type="hidden" name="token_id" value="{t["id"]}">
                    <button type="submit" class="btn btn-danger" style="padding: 6px 12px; font-size: 12px;">삭제</button>
                </form>
            </div>
        </div>
        """

    if not tokens:
        token_list = '<p style="color: #888; text-align: center; padding: 20px;">생성된 토큰이 없습니다</p>'

    content = f"""
    {new_token_html}
    <div class="card">
        <h2 style="margin-top: 0;">새 토큰 생성</h2>
        <form method="post" action="/tokens/create">
            <label>토큰 이름 (선택)</label>
            <input type="text" name="name" placeholder="예: Claude Desktop용">
            <button type="submit">토큰 생성</button>
        </form>
    </div>
    <div class="card">
        <h2 style="margin-top: 0;">내 토큰</h2>
        {token_list}
    </div>
    <div class="card">
        <h2 style="margin-top: 0;">사용 방법</h2>
        <p style="color: #aaa; line-height: 1.8;">
            생성된 토큰을 MCP 클라이언트의 <code>Authorization</code> 헤더에 설정하세요:<br>
            <code style="background: #0f0f0f; padding: 8px 12px; border-radius: 4px; display: inline-block; margin-top: 10px;">
                Authorization: Bearer YOUR_TOKEN_HERE
            </code>
        </p>
    </div>
    """
    return HTMLResponse(render_page("토큰 관리", content, user_id))


@app.post("/tokens/create")
async def create_token_submit(session: Optional[str] = Cookie(None), name: str = Form("default")):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    token = db.create_token(user_id, name or "default")
    if session:
        session_flash[session] = {"new_token": token}
    return RedirectResponse("/tokens", status_code=303)


@app.post("/tokens/delete")
async def delete_token_submit(session: Optional[str] = Cookie(None), token_id: int = Form(...)):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    db.delete_token(token_id, user_id)
    return RedirectResponse("/tokens", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
