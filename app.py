"""HTTP 기반 MCP 서버 (다중 사용자 지원) + 웹 UI - MVP (쿠팡 + CJ대한통운)"""
import html
import json
import secrets
import os
import httpx
import time
from collections import defaultdict
from typing import Any, Optional

from fastapi import FastAPI, Request, Response, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from auth import extract_credentials_auto, set_credentials, get_credentials, AUTH_HEADERS_SPEC
from tools.orders import get_orders
from tools.shipping import issue_invoice, register_invoice, process_orders
from tools.config import check_config
import database as db
from email_service import send_verification_email

# Cloudflare Turnstile 설정
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

# 세션 저장소 (메모리 - 프로덕션에서는 Redis 등 사용 권장)
MAX_SESSIONS = 10000
sessions: dict[str, int] = {}
session_csrf: dict[str, str] = {}
session_flash: dict[str, dict] = {}
pending_registrations: dict[str, dict] = {}

# 레이트 리밋 (IP별 요청 시각 기록)
_rate_limits: dict[str, list[float]] = defaultdict(list)


MAX_RATE_LIMIT_KEYS = 10000


def _check_rate_limit(ip: str, max_requests: int = 5, window_seconds: int = 600) -> bool:
    """IP 기반 레이트 리밋. 제한 초과 시 False 반환."""
    now = time.time()
    # 메모리 제한: 키가 너무 많으면 전체 초기화
    if len(_rate_limits) > MAX_RATE_LIMIT_KEYS:
        _rate_limits.clear()
    timestamps = _rate_limits[ip]
    # 윈도우 밖의 오래된 기록 제거
    _rate_limits[ip] = [t for t in timestamps if now - t < window_seconds]
    if len(_rate_limits[ip]) >= max_requests:
        return False
    _rate_limits[ip].append(now)
    return True


def get_session_user(session_id: Optional[str]) -> Optional[int]:
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None


def create_session(user_id: int) -> str:
    if len(sessions) >= MAX_SESSIONS:
        # 가장 오래된 세션 절반 제거
        to_remove = list(sessions.keys())[:MAX_SESSIONS // 2]
        for k in to_remove:
            sessions.pop(k, None)
            session_csrf.pop(k, None)
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = user_id
    session_csrf[session_id] = secrets.token_urlsafe(32)
    return session_id


def get_csrf_token(session_id: Optional[str]) -> str:
    if session_id and session_id in session_csrf:
        return session_csrf[session_id]
    return ""


def verify_csrf(session_id: Optional[str], token: str) -> bool:
    expected = get_csrf_token(session_id)
    if not expected:
        return False
    return secrets.compare_digest(expected, token)


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
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com https://static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline'; "
            "frame-src https://challenges.cloudflare.com; "
            "connect-src 'self' https://cloudflareinsights.com"
        )
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


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    from scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(
    title="SoloSeller MCP Server",
    description="쿠팡 주문 관리 및 CJ대한통운 송장 자동화 MCP 서버",
    version="2.1.0",
    lifespan=lifespan,
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
            <a href="/dashboard">대시보드</a>
            <a href="/settings">설정</a>
            <a href="/tokens">토큰</a>
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
        "name": "check_config",
        "description": "현재 설정 상태를 확인합니다. 어떤 기능이 사용 가능한지 점검할 때 사용하세요.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_orders",
        "description": "쿠팡에서 신규 주문을 조회합니다. 주문 확인만 하고 싶을 때 사용하세요. 설정 필요: 쿠팡 API 키",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "조회 기간 (최근 N일)"}
            }
        }
    },
    {
        "name": "issue_invoice",
        "description": "CJ대한통운으로 송장을 발급합니다. 개별 주문을 수동 처리할 때 사용하세요. 설정 필요: CJ대한통운 고객정보, 발송인 정보",
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
        "description": "쿠팡에 송장번호를 등록합니다. issue_invoice로 발급받은 송장을 쿠팡에 입력할 때 사용하세요. 설정 필요: 쿠팡 API 키",
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
        "description": "주문 조회→송장 발급→쿠팡 등록을 한번에 처리합니다. 일상적인 주문 처리에 이 도구를 사용하세요. dry_run=true로 미리보기 가능. 설정 필요: 쿠팡 API 키, CJ대한통운 고객정보, 발송인 정보",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "조회 기간 (최근 N일)"},
                "dry_run": {"type": "boolean", "default": False, "description": "true면 미리보기만 (송장 발급 안 함)"}
            }
        }
    }
]


async def execute_tool(name: str, arguments: dict) -> dict:
    """MCP Tool 실행"""
    if name == "check_config":
        return await check_config()
    elif name == "get_orders":
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
        return await process_orders(
            days=arguments.get("days", 7),
            dry_run=arguments.get("dry_run", False)
        )
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
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"register:{client_ip}", max_requests=5, window_seconds=600):
        return RedirectResponse("/register?error=요청이 너무 많습니다. 잠시 후 다시 시도해주세요", status_code=303)
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

    if len(pending_registrations) >= 1000:
        pending_registrations.clear()
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
    reg_data = pending_registrations.get(token)
    if not db.verify_code(reg_data["email"], code, "register"):
        return RedirectResponse(f"/verify-email?token={token}&email={email}&error=인증 코드가 올바르지 않습니다", status_code=303)

    pending_registrations.pop(token)
    user_id = db.create_user_with_hash(reg_data["email"], reg_data["password_hash"])
    if not user_id:
        return RedirectResponse("/register?error=회원가입에 실패했습니다", status_code=303)

    db.mark_email_verified(reg_data["email"])
    return RedirectResponse("/login?success=회원가입이 완료되었습니다! 로그인해주세요", status_code=303)


@app.get("/resend-code")
async def resend_code(request: Request, token: str = "", email: str = ""):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"resend:{client_ip}", max_requests=3, window_seconds=600):
        return RedirectResponse(f"/verify-email?token={token}&email={email}&error=요청이 너무 많습니다. 잠시 후 다시 시도해주세요", status_code=303)
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
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"login:{client_ip}", max_requests=10, window_seconds=600):
        return RedirectResponse("/login?error=로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요", status_code=303)
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
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400*30)
    return response


@app.get("/logout")
async def logout(session: Optional[str] = Cookie(None)):
    if session:
        sessions.pop(session, None)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


# ============ 웹 UI - 대시보드 ============

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(session: Optional[str] = Cookie(None)):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    creds = db.get_user_credentials(user_id) or {}
    coupang_ok = all(creds.get(k) for k in ["coupang_vendor_id", "coupang_access_key", "coupang_secret_key"])
    cj_ok = all(creds.get(k) for k in ["cj_customer_id", "cj_biz_reg_num"])
    sender_ok = all(creds.get(k) for k in ["sender_name", "sender_phone", "sender_address"])
    all_ok = coupang_ok and cj_ok and sender_ok

    auto = db.get_automation_settings(user_id) or {}
    auto_enabled = "checked" if auto.get("enabled") else ""
    auto_interval = auto.get("interval_minutes", 60)
    auto_last_run = auto.get("last_run_at", "")
    auto_last_result = auto.get("last_result", "")

    def interval_selected(val):
        return "selected" if auto_interval == val else ""

    setup_msg = ""
    if not all_ok:
        setup_msg = '<div class="error" style="margin-top:12px;">설정을 완료해야 사용할 수 있습니다. <a href="/settings" style="color:#fca5a5;">설정하기 →</a></div>'

    dis = "" if all_ok else "disabled style='opacity:0.4;pointer-events:none;'"

    content = f"""
    <!-- 연동 상태 -->
    <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div class="field-group-title" style="margin:0;">연동 상태</div>
            <span style="font-size:13px;color:{'#86efac' if all_ok else '#fca5a5'};">{'모두 연동됨' if all_ok else '설정 필요'}</span>
        </div>
        <div style="margin-top:12px;">
            {''.join(f'<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:13px;margin:4px;background:{chr(35)}14532d;color:{chr(35)}86efac;" >✓ {l}</span>' if ok else f'<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:13px;margin:4px;background:{chr(35)}7f1d1d;color:{chr(35)}fca5a5;">✗ {l}</span>' for l, ok in [("쿠팡", coupang_ok), ("CJ대한통운", cj_ok), ("발송인", sender_ok)])}
        </div>
        {setup_msg}
    </div>

    <!-- 자동화 -->
    <div class="card" {dis}>
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div class="field-group-title" style="margin:0;">자동 처리</div>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0;">
                <input type="checkbox" id="auto-toggle" {auto_enabled} onchange="toggleAuto()" style="width:18px;height:18px;">
                <span style="font-size:13px;" id="auto-label">{('ON' if auto_enabled else 'OFF')}</span>
            </label>
        </div>
        <div style="margin-top:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
            <select id="auto-interval" onchange="updateInterval()" style="padding:8px 12px;border-radius:8px;background:#0f0f0f;color:#fff;border:1px solid #333;font-size:13px;">
                <option value="30" {interval_selected(30)}>30분마다</option>
                <option value="60" {interval_selected(60)}>1시간마다</option>
                <option value="120" {interval_selected(120)}>2시간마다</option>
                <option value="240" {interval_selected(240)}>4시간마다</option>
            </select>
            <span style="font-size:12px;color:#888;" id="auto-status">
                {'마지막: ' + html.escape(str(auto_last_run)[:16] + ' — ' + str(auto_last_result)) if auto_last_run else '아직 실행 기록 없음'}
            </span>
        </div>
    </div>

    <!-- 주문 조회 + 처리 -->
    <div class="card" {dis}>
        <div class="field-group-title">주문 처리</div>
        <p style="color:#aaa;margin-bottom:16px;font-size:13px;">쿠팡 신규 주문 조회 → CJ대한통운 송장 발급 → 쿠팡 송장 등록</p>
        <div id="orders-table" style="margin-bottom:16px;"><p style="color:#666;font-size:13px;">로딩 중...</p></div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button onclick="fetchOrders()" style="background:#333;">새로고침</button>
            <button onclick="processConfirm()" style="background:#22c55e;" id="process-btn">일괄 처리</button>
            <button onclick="testPrint()" style="background:#6366f1;">테스트 출력</button>
        </div>
    </div>

    <!-- 처리 내역 -->
    <div class="card">
        <div class="field-group-title">처리 내역</div>
        <div id="logs-area" style="font-size:13px;"><p style="color:#666;">로딩 중...</p></div>
    </div>

    <!-- 확인 모달 -->
    <div id="confirm-modal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:100;align-items:center;justify-content:center;">
        <div style="background:#1a1a1a;border-radius:12px;padding:32px;max-width:400px;margin:auto;margin-top:20vh;text-align:center;">
            <p style="font-size:16px;margin-bottom:8px;">일괄 처리를 시작합니다</p>
            <p style="color:#aaa;font-size:13px;margin-bottom:24px;" id="confirm-msg">모든 신규 주문에 송장을 발급하고 쿠팡에 등록합니다.</p>
            <div style="display:flex;gap:10px;justify-content:center;">
                <button onclick="closeModal()" style="background:#333;">취소</button>
                <button onclick="doProcess()" style="background:#22c55e;">확인</button>
            </div>
        </div>
    </div>

    <script>
    function esc(s) {{ const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }}

    async function api(action, body={{}}) {{
        const res = await fetch('/api/dashboard/' + action, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json', 'X-Requested-With': 'SoloSeller'}},
            body: JSON.stringify(body)
        }});
        return await res.json();
    }}

    // 주문 테이블
    function renderOrders(data) {{
        const el = document.getElementById('orders-table');
        if (!data.success && data.error) {{ el.innerHTML = '<div class="error">' + esc(data.error) + '</div>'; return; }}
        const orders = data.orders || [];
        if (orders.length === 0) {{ el.innerHTML = '<p style="color:#666;font-size:13px;">신규 주문이 없습니다.</p>'; return; }}
        let h = '<table style="width:100%;font-size:13px;border-collapse:collapse;"><tr style="color:#888;"><th style="text-align:left;padding:8px;">주문번호</th><th style="text-align:left;">수령인</th><th style="text-align:left;">상품</th></tr>';
        orders.forEach(o => {{
            const items = o.items || [];
            const pname = items.length > 0 ? (items[0].product_name || '상품') : '상품';
            h += '<tr style="border-top:1px solid #222;"><td style="padding:8px;font-family:monospace;font-size:12px;">' + esc(o.order_id||'') + '</td><td>' + esc(o.receiver_name||'') + '</td><td>' + esc(pname) + '</td></tr>';
        }});
        h += '</table><p style="margin-top:8px;color:#888;font-size:12px;">' + orders.length + '건의 신규 주문</p>';
        el.innerHTML = h;
    }}

    async function fetchOrders() {{
        document.getElementById('orders-table').innerHTML = '<p style="color:#666;font-size:13px;">조회 중...</p>';
        renderOrders(await api('orders'));
    }}

    // 처리
    function processConfirm() {{ document.getElementById('confirm-modal').style.display = 'flex'; }}
    function closeModal() {{ document.getElementById('confirm-modal').style.display = 'none'; }}

    let lastResults = [];
    async function doProcess() {{
        closeModal();
        document.getElementById('process-btn').textContent = '처리 중...';
        document.getElementById('process-btn').disabled = true;
        const data = await api('process', {{dry_run: false}});
        document.getElementById('process-btn').textContent = '일괄 처리';
        document.getElementById('process-btn').disabled = false;
        if (data.results) {{
            lastResults = data.results;
            let h = '<table style="width:100%;font-size:13px;"><tr style="color:#888;"><th style="text-align:left;padding:8px;">주문</th><th>송장번호</th><th>상태</th></tr>';
            data.results.forEach(r => {{
                const st = (r.status === '완료' || r.status === '테스트') ? '<span style="color:#86efac;">' + esc(r.status) + '</span>' : '<span style="color:#fca5a5;">' + esc(r.error || r.status) + '</span>';
                h += '<tr style="border-top:1px solid #222;"><td style="padding:8px;font-size:12px;">' + esc(r.order_id) + '</td><td style="font-family:monospace;">' + esc(r.tracking_number||'-') + '</td><td>' + st + '</td></tr>';
            }});
            h += '</table><p style="color:#888;font-size:12px;margin-top:8px;">총 ' + (data.total||0) + '건 | 성공 ' + (data.processed||0) + '건 | 실패 ' + (data.failed||0) + '건</p>';
            const printable = data.results.filter(r => r.tracking_number);
            if (printable.length > 0) {{
                h += '<button onclick="printLabels()" style="margin-top:12px;background:#2563eb;padding:10px 24px;">송장 출력 (' + printable.length + '건)</button>';
            }}
            document.getElementById('orders-table').innerHTML = h;
            // 송장번호가 있으면 자동으로 출력 창 열기
            if (printable.length > 0) {{
                printLabels();
            }}
        }} else {{
            document.getElementById('orders-table').innerHTML = '<p style="color:#888;font-size:13px;">' + esc(data.message || '완료') + '</p>';
        }}
        loadLogs();
    }}

    function printLabels() {{
        const printable = lastResults.filter(r => r.tracking_number);
        if (printable.length === 0) return;
        const w = window.open('', '_blank');
        if (!w) {{ alert('팝업이 차단되었습니다. 팝업을 허용해주세요.'); return; }}
        const e = s => {{ const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }};
        let labels = '';
        const today = new Date();
        const dateStr = today.getFullYear() + '.' + String(today.getMonth()+1).padStart(2,'0') + '.' + String(today.getDate()).padStart(2,'0');
        printable.forEach((r, idx) => {{
            const rc = e(r.routing_code||'');
            const bn = e(r.branch_name||'');
            const nm = e(r.receiver_name||'');
            const masked = nm.length >= 2 ? nm[0] + '*'.repeat(nm.length - 2) + nm[nm.length-1] : nm;
            const addr = e(r.receiver_address||'');
            // 상세주소: 아파트/빌라/동/호 부분만 추출 (괄호, 대괄호 제외)
            const cleaned = addr.replace(/\\s*\\[.*?\\]/g, '').replace(/\\s*\\(.*?\\)/g, '');
            const parts = cleaned.split(/\\s+/);
            // 뒤에서 동/호/층 포함된 부분 찾기
            let detIdx = parts.length;
            for (let i = parts.length - 1; i >= 0; i--) {{
                if (/\\d+[동호층]|아파트|빌라|오피스텔|타워|빌딩/.test(parts[i])) {{ detIdx = i; }}
                else if (detIdx < parts.length) break;
            }}
            const detailAddr = detIdx < parts.length ? parts.slice(detIdx).join(' ') : nm;
            labels += `
            <div class="label">
                <!-- 1행: 운송장번호 바코드 -->
                <div class="r1">
                    <div class="r1-left">
                        <span class="r1-label">운송장번호</span>
                        <span class="r1-num">${{e(r.tracking_number)}}</span>
                    </div>
                    <svg class="bc1" data-value="${{e(r.tracking_number)}}"></svg>
                    <div class="r1-right">
                        <span>${{dateStr}}</span>
                        <span class="r1-qty">1/1</span>
                        <span class="r1-cs">고객센터 1588-1255</span>
                    </div>
                </div>
                <!-- 2행: 분류코드 -->
                <div class="r2">
                    <svg class="bc-route" data-value="${{e(r.tracking_number)}}"></svg>
                    <span class="r2-code">${{rc || ''}}</span>
                </div>
                <!-- 3행: 받는분 -->
                <div class="r3">
                    <div class="r3-tag"><span class="vtag vtag-r">받<br>는<br>분</span></div>
                    <div class="r3-content">
                        <div class="r3-line1">${{masked}} ${{e(r.receiver_phone)}}</div>
                        <div class="r3-addr">${{addr}}</div>
                        <div class="r3-detail">${{detailAddr}}</div>
                    </div>
                </div>
                <!-- 4행: 보내는분 + 수량/운임/정산 -->
                <div class="r4">
                    <div class="r4-tag"><span class="vtag vtag-s">보<br>내<br>는<br>분</span></div>
                    <div class="r4-content">
                        <span>${{e(r.sender_name)}} &nbsp; ${{e(r.sender_phone)}}</span>
                        <div class="r4-addr">${{e(r.sender_address)}}</div>
                    </div>
                    <div class="r4-boxes">
                        <div class="info-box"><div class="info-head">수량</div><div class="info-val">극소C 1</div></div>
                        <div class="info-box"><div class="info-head">운임</div><div class="info-val">0</div></div>
                        <div class="info-box"><div class="info-head">정산</div><div class="info-val">선불</div></div>
                    </div>
                </div>
                <!-- 5행: 상품 -->
                <div class="r5">
                    <span>${{e(r.product_name)}}</span>
                    <span class="r5-qty">총수량:1</span>
                </div>
                <!-- 6행: 주의사항 -->
                <div class="r6">고객님(받는 분)의 소중한 상품을 안전하게 배송하겠습니다. 개인정보 유출우려가 있으니 운송장은 폐기바랍니다.</div>
                <!-- 7행: 하단 -->
                <div class="r7">
                    <div class="r7-branch">${{bn ? '대한통운 - ' + bn : '대한통운'}}</div>
                    <div class="r7-bc"><svg class="bc2" data-value="${{e(r.tracking_number)}}"></svg></div>
                    <span class="r7-num">${{e(r.tracking_number)}}</span>
                </div>
            </div>`;
        }});
        w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>송장 출력</title>
        <style>
            @page {{ size: 121.5mm 100mm; margin: 0; }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; margin: 0; padding: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .label {{
                width: 121.5mm; height: 100mm; padding: 1.5mm 2mm;
                page-break-after: always; border: 1px solid #aaa;
                display: flex; flex-direction: column; overflow: hidden;
            }}
            /* 1행: 운송장번호 */
            .r1 {{
                display: flex; align-items: center; justify-content: space-between;
                border-bottom: 2px solid #000; padding: 0.8mm 0;
            }}
            .r1-left {{ display: flex; align-items: baseline; gap: 1mm; }}
            .r1-label {{ font-size: 6pt; color: #e67300; font-weight: bold; border: 1px solid #e67300; padding: 0 1mm; }}
            .r1-num {{ font-size: 9pt; font-weight: bold; font-family: 'Courier New', monospace; }}
            .bc1 {{ height: 9mm; }}
            .r1-right {{ display: flex; align-items: center; gap: 1.5mm; font-size: 6.5pt; }}
            .r1-qty {{ border: 1px solid #000; padding: 0 1.5mm; font-weight: bold; }}
            .r1-cs {{ color: #e67300; font-weight: bold; }}
            /* 2행: 분류코드 */
            .r2 {{
                display: flex; align-items: center; justify-content: center; gap: 3mm;
                border-bottom: 2px solid #000; padding: 1mm 0;
                min-height: 13mm;
            }}
            .bc-route {{ height: 10mm; }}
            .r2-code {{ font-size: 32pt; font-weight: 900; letter-spacing: 2px; }}
            /* 3행: 받는분 */
            .r3 {{
                flex: 1; display: flex;
                border-bottom: 2px solid #000; padding: 0.5mm 0;
            }}
            .r3-tag {{ display: flex; align-items: flex-start; padding-right: 1mm; }}
            .r3-content {{ flex: 1; }}
            .vtag {{
                writing-mode: vertical-lr; text-orientation: upright;
                font-size: 5.5pt; font-weight: bold; color: #fff;
                padding: 1mm 0.5mm; text-align: center; letter-spacing: 0.5mm;
                line-height: 1;
            }}
            .vtag-r {{ background: #cc0000; }}
            .vtag-s {{ background: #0056b3; }}
            .r3-line1 {{ font-size: 8pt; font-weight: bold; margin-bottom: 0.3mm; }}
            .r3-addr {{ font-size: 7pt; color: #333; line-height: 1.2; }}
            .r3-detail {{ font-size: 16pt; font-weight: 900; margin-top: 0.5mm; line-height: 1.15; }}
            /* 4행: 보내는분 */
            .r4 {{
                display: flex; align-items: stretch;
                padding: 0.5mm 0; border-bottom: 1px solid #999;
                font-size: 6.5pt; line-height: 1.2;
            }}
            .r4-tag {{ display: flex; align-items: flex-start; padding-right: 1mm; }}
            .r4-content {{ flex: 1; }}
            .r4-addr {{ color: #555; }}
            .r4-boxes {{ display: flex; gap: 0; flex-shrink: 0; margin-left: 1mm; }}
            .info-box {{ border: 1px solid #ccc; text-align: center; min-width: 10mm; }}
            .info-head {{ background: #f0f0f0; font-size: 5.5pt; font-weight: bold; color: #e67300; padding: 0.2mm 1mm; border-bottom: 1px solid #ccc; }}
            .info-val {{ font-size: 6pt; padding: 0.2mm 1mm; }}
            /* 5행: 상품 */
            .r5 {{
                display: flex; justify-content: space-between; align-items: center;
                padding: 0.3mm 0; font-size: 6.5pt; border-bottom: 1px solid #ccc;
            }}
            .r5-qty {{ font-size: 6pt; color: #555; }}
            /* 6행: 주의사항 */
            .r6 {{ font-size: 5pt; color: #888; padding: 0.3mm 0; line-height: 1.15; }}
            /* 7행: 하단 */
            .r7 {{
                display: flex; align-items: center; gap: 1mm;
                margin-top: auto; padding-top: 0.5mm; border-top: 2px solid #000;
            }}
            .r7-branch {{ background: #e67300; color: #fff; padding: 0.8mm 2mm; font-size: 7pt; font-weight: bold; white-space: nowrap; flex-shrink: 0; }}
            .r7-bc {{ flex: 1; text-align: center; }}
            .bc2 {{ height: 6mm; }}
            .r7-num {{ font-size: 6pt; font-family: 'Courier New', monospace; flex-shrink: 0; }}
            @media print {{ .label {{ border: none; }} }}
        </style>
        <script src="/static/jsbarcode.min.js"><\\/script>
        </head><body>${{labels}}
        <script>
            document.querySelectorAll('.bc1').forEach(svg => {{
                JsBarcode(svg, svg.dataset.value, {{ format: 'CODE128', width: 1.3, height: 28, displayValue: false, margin: 0 }});
            }});
            document.querySelectorAll('.bc-route').forEach(svg => {{
                JsBarcode(svg, svg.dataset.value, {{ format: 'CODE128', width: 1, height: 30, displayValue: false, margin: 0 }});
            }});
            document.querySelectorAll('.bc2').forEach(svg => {{
                JsBarcode(svg, svg.dataset.value, {{ format: 'CODE128', width: 1.2, height: 18, displayValue: false, margin: 0 }});
            }});
            setTimeout(() => window.print(), 500);
        <\\/script></body></html>`);
        w.document.close();
    }}

    function testPrint() {{
        lastResults = [{{
            order_id: 'TEST-20260320-001',
            tracking_number: '6970-4079-7621',
            receiver_name: '최민수',
            receiver_phone: '0502-2703-4885',
            receiver_address: '서울특별시 동대문구 천호대로35길 32 (용두동, 다솜) 다솜빌라 203호 [용두동, 다솜]',
            receiver_zipcode: '02580',
            sender_name: '주식회사 지너스인터내셔널',
            sender_phone: '061-725-7298',
            sender_address: '전라남도 순천시 가곡동 741번지 지너스인터내셔널',
            sender_zipcode: '57900',
            product_name: '헤어용품 500ml',
            routing_code: '2 T25 -1b',
            branch_name: '용두중앙-B47-6구역',
            status: '테스트',
        }}];
        printLabels();
    }}

    // 자동화
    async function toggleAuto() {{
        const enabled = document.getElementById('auto-toggle').checked;
        const interval = parseInt(document.getElementById('auto-interval').value);
        document.getElementById('auto-label').textContent = enabled ? 'ON' : 'OFF';
        await api('automation', {{enabled, interval_minutes: interval}});
    }}
    async function updateInterval() {{
        const enabled = document.getElementById('auto-toggle').checked;
        const interval = parseInt(document.getElementById('auto-interval').value);
        await api('automation', {{enabled, interval_minutes: interval}});
    }}

    // 로그
    async function loadLogs() {{
        const data = await api('logs');
        const el = document.getElementById('logs-area');
        const logs = data.logs || [];
        if (logs.length === 0) {{ el.innerHTML = '<p style="color:#666;">아직 처리 내역이 없습니다.</p>'; return; }}
        let h = '<table style="width:100%;font-size:12px;border-collapse:collapse;"><tr style="color:#888;"><th style="text-align:left;padding:6px;">시간</th><th>유형</th><th>건수</th><th>결과</th></tr>';
        logs.forEach(l => {{
            const t = l.trigger_type === 'auto' ? '🤖 자동' : '👆 수동';
            const color = l.failed > 0 ? '#fca5a5' : '#86efac';
            h += '<tr style="border-top:1px solid #222;"><td style="padding:6px;">' + esc((l.created_at||'').substring(0,16)) + '</td><td>' + t + '</td><td>' + l.total_orders + '건</td><td style="color:' + color + ';">성공 ' + l.processed + ' / 실패 ' + l.failed + '</td></tr>';
        }});
        h += '</table>';
        el.innerHTML = h;
    }}

    // 페이지 로드 시 주문 + 로그 조회
    fetchOrders();
    loadLogs();
    </script>
    """
    return HTMLResponse(render_page("대시보드", content, user_id))


def _dashboard_auth(request: Request, session: Optional[str]):
    """대시보드 API 인증 + CSRF 검증"""
    if request.headers.get("X-Requested-With") != "SoloSeller":
        return None, {"success": False, "error": "잘못된 요청입니다."}
    user_id = get_session_user(session)
    if not user_id:
        return None, {"success": False, "error": "로그인이 필요합니다."}
    return user_id, None


def _load_user_creds(user_id: int):
    """사용자 인증 정보 로드 + ContextVar 설정"""
    from auth import UserCredentials, set_credentials
    creds_dict = db.get_user_credentials(user_id) or {}
    creds = UserCredentials(
        coupang_vendor_id=creds_dict.get("coupang_vendor_id"),
        coupang_access_key=creds_dict.get("coupang_access_key"),
        coupang_secret_key=creds_dict.get("coupang_secret_key"),
        cj_customer_id=creds_dict.get("cj_customer_id"),
        cj_biz_reg_num=creds_dict.get("cj_biz_reg_num"),
        sender_name=creds_dict.get("sender_name"),
        sender_phone=creds_dict.get("sender_phone"),
        sender_zipcode=creds_dict.get("sender_zipcode"),
        sender_address=creds_dict.get("sender_address"),
    )
    set_credentials(creds)
    return creds


@app.post("/api/dashboard/orders")
async def api_dashboard_orders(request: Request, session: Optional[str] = Cookie(None)):
    user_id, err = _dashboard_auth(request, session)
    if err:
        return err
    from auth import set_credentials
    try:
        _load_user_creds(user_id)
        return await get_orders(days=7)
    finally:
        set_credentials(None)


@app.post("/api/dashboard/process")
async def api_dashboard_process(request: Request, session: Optional[str] = Cookie(None)):
    user_id, err = _dashboard_auth(request, session)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "error": "잘못된 요청입니다."}
    dry_run = body.get("dry_run", True)
    from auth import set_credentials
    try:
        _load_user_creds(user_id)
        result = await process_orders(days=7, dry_run=dry_run)
        if not dry_run and result.get("total", 0) > 0:
            db.create_processing_log(
                user_id=user_id,
                trigger_type="manual",
                total=result.get("total", 0),
                processed=result.get("processed", 0),
                failed=result.get("failed", 0),
                result_json=json.dumps(result.get("results", []), ensure_ascii=False),
            )
        return result
    finally:
        set_credentials(None)


@app.post("/api/dashboard/automation")
async def api_dashboard_automation(request: Request, session: Optional[str] = Cookie(None)):
    user_id, err = _dashboard_auth(request, session)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "error": "잘못된 요청입니다."}
    enabled = bool(body.get("enabled", False))
    try:
        interval = int(body.get("interval_minutes", 60))
    except (ValueError, TypeError):
        return {"success": False, "error": "interval_minutes는 숫자여야 합니다."}
    interval = max(10, min(interval, 1440))
    db.update_automation_settings(user_id, enabled, interval)
    return {"success": True, "enabled": enabled, "interval_minutes": interval}


@app.get("/api/dashboard/automation")
async def api_get_automation(request: Request, session: Optional[str] = Cookie(None)):
    user_id, err = _dashboard_auth(request, session)
    if err:
        return err
    settings = db.get_automation_settings(user_id)
    return {"success": True, **(settings or {"enabled": False, "interval_minutes": 60})}


@app.post("/api/dashboard/logs")
async def api_dashboard_logs(request: Request, session: Optional[str] = Cookie(None)):
    user_id, err = _dashboard_auth(request, session)
    if err:
        return err
    logs = db.get_processing_logs(user_id, limit=20)
    return {"success": True, "logs": logs}


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

    csrf = get_csrf_token(session)
    content = f"""
    {msg}
    <form method="post">
        <input type="hidden" name="csrf_token" value="{csrf}">
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
    if not verify_csrf(session, form.get("csrf_token", "")):
        return RedirectResponse("/settings", status_code=303)
    credentials = {k: v for k, v in form.items() if k != "csrf_token"}
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
                    <input type="hidden" name="csrf_token" value="{get_csrf_token(session)}">
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
            <input type="hidden" name="csrf_token" value="{get_csrf_token(session)}">
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
async def create_token_submit(request: Request, session: Optional[str] = Cookie(None), name: str = Form("default"), csrf_token: str = Form("")):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    if not verify_csrf(session, csrf_token):
        return RedirectResponse("/tokens", status_code=303)
    token = db.create_token(user_id, name or "default")
    if session:
        session_flash[session] = {"new_token": token}
    return RedirectResponse("/tokens", status_code=303)


@app.post("/tokens/delete")
async def delete_token_submit(request: Request, session: Optional[str] = Cookie(None), token_id: int = Form(...), csrf_token: str = Form("")):
    user_id = get_session_user(session)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    if not verify_csrf(session, csrf_token):
        return RedirectResponse("/tokens", status_code=303)
    db.delete_token(token_id, user_id)
    return RedirectResponse("/tokens", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
