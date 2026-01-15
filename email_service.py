"""이메일 발송 모듈 - Naver SMTP"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 환경 변수에서 설정 로드
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.naver.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "SoloSeller")


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """이메일 발송"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("[EMAIL] SMTP 설정이 없습니다. SMTP_USER, SMTP_PASSWORD 환경변수를 확인하세요.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        msg["To"] = to_email

        html_part = MIMEText(html_content, "html", "utf-8")
        msg.attach(html_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        print(f"[EMAIL] 발송 성공: {to_email}")
        return True

    except Exception as e:
        print(f"[EMAIL] 발송 실패: {to_email} - {e}")
        return False


def send_verification_email(to_email: str, code: str) -> bool:
    """인증 코드 이메일 발송"""
    subject = "[SoloSeller] 이메일 인증 코드"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 40px 20px; }}
            .container {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            h1 {{ color: #333; font-size: 24px; margin-bottom: 20px; }}
            .code {{ background: #f0f7ff; color: #1a73e8; font-size: 32px; font-weight: bold; letter-spacing: 8px; padding: 20px; border-radius: 8px; text-align: center; margin: 30px 0; }}
            p {{ color: #666; line-height: 1.6; }}
            .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>이메일 인증</h1>
            <p>아래 인증 코드를 입력해주세요.</p>
            <div class="code">{code}</div>
            <p>이 코드는 <strong>10분</strong> 동안 유효합니다.</p>
            <p>본인이 요청하지 않았다면 이 이메일을 무시해주세요.</p>
            <div class="footer">
                SoloSeller - 쇼핑몰 자동화 MCP 서버
            </div>
        </div>
    </body>
    </html>
    """
    return send_email(to_email, subject, html_content)
