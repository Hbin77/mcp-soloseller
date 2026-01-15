"""데이터베이스 모듈 - SQLite 기반 사용자/토큰 관리"""
import sqlite3
import hashlib
import secrets
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from contextlib import contextmanager

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/users.db")


def get_db_path() -> str:
    """데이터베이스 경로 반환 및 디렉토리 생성"""
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    return DATABASE_PATH


@contextmanager
def get_connection():
    """데이터베이스 연결 컨텍스트 매니저"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_database():
    """데이터베이스 초기화 - 테이블 생성"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 사용자 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # API 키 설정 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                -- 네이버
                naver_client_id TEXT,
                naver_client_secret TEXT,
                naver_seller_id TEXT,
                -- 쿠팡
                coupang_vendor_id TEXT,
                coupang_access_key TEXT,
                coupang_secret_key TEXT,
                -- 택배사 - CJ
                cj_customer_id TEXT,
                cj_api_key TEXT,
                -- 택배사 - 한진
                hanjin_customer_id TEXT,
                hanjin_api_key TEXT,
                -- 택배사 - 롯데
                lotte_customer_id TEXT,
                lotte_api_key TEXT,
                -- 택배사 - 로젠
                logen_customer_id TEXT,
                logen_api_key TEXT,
                -- 택배사 - 우체국
                epost_customer_id TEXT,
                epost_api_key TEXT,
                -- 발송인 정보
                sender_name TEXT,
                sender_phone TEXT,
                sender_zipcode TEXT,
                sender_address TEXT,
                -- 기본 택배사
                default_carrier TEXT DEFAULT 'cj',
                -- 메타
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # 토큰 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                name TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                expires_at TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def hash_password(password: str) -> str:
    """비밀번호 해싱"""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token() -> str:
    """안전한 토큰 생성"""
    return secrets.token_urlsafe(32)


# ============ 사용자 관리 ============

def create_user(email: str, password: str) -> Optional[int]:
    """사용자 생성"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, hash_password(password))
            )
            user_id = cursor.lastrowid

            # 빈 credentials 레코드 생성
            cursor.execute(
                "INSERT INTO user_credentials (user_id) VALUES (?)",
                (user_id,)
            )
            return user_id
    except sqlite3.IntegrityError:
        return None


def authenticate_user(email: str, password: str) -> Optional[int]:
    """사용자 인증 - 성공시 user_id 반환"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM users WHERE email = ? AND password_hash = ?",
            (email, hash_password(password))
        )
        row = cursor.fetchone()
        return row["id"] if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """사용자 정보 조회"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ============ API 키 관리 ============

def get_user_credentials(user_id: int) -> Optional[dict]:
    """사용자 API 키 조회"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_credentials WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_user_credentials(user_id: int, credentials: dict) -> bool:
    """사용자 API 키 업데이트"""
    allowed_fields = [
        'naver_client_id', 'naver_client_secret', 'naver_seller_id',
        'coupang_vendor_id', 'coupang_access_key', 'coupang_secret_key',
        'cj_customer_id', 'cj_api_key',
        'hanjin_customer_id', 'hanjin_api_key',
        'lotte_customer_id', 'lotte_api_key',
        'logen_customer_id', 'logen_api_key',
        'epost_customer_id', 'epost_api_key',
        'sender_name', 'sender_phone', 'sender_zipcode', 'sender_address',
        'default_carrier'
    ]

    # 허용된 필드만 필터링
    filtered = {k: v for k, v in credentials.items() if k in allowed_fields}
    if not filtered:
        return False

    # SQL 생성
    set_clause = ", ".join([f"{k} = ?" for k in filtered.keys()])
    values = list(filtered.values()) + [user_id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE user_credentials SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            values
        )
        return cursor.rowcount > 0


# ============ 토큰 관리 ============

def create_token(user_id: int, name: str = "default", expires_days: int = 365) -> str:
    """새 토큰 생성"""
    token = generate_token()
    expires_at = datetime.now() + timedelta(days=expires_days)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tokens (user_id, token, name, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token, name, expires_at)
        )
    return token


def validate_token(token: str) -> Optional[int]:
    """토큰 검증 - 유효하면 user_id 반환"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT user_id FROM tokens
               WHERE token = ? AND is_active = 1
               AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)""",
            (token,)
        )
        row = cursor.fetchone()

        if row:
            # 마지막 사용 시간 업데이트
            cursor.execute(
                "UPDATE tokens SET last_used_at = CURRENT_TIMESTAMP WHERE token = ?",
                (token,)
            )
            return row["user_id"]
        return None


def get_user_tokens(user_id: int) -> list:
    """사용자의 토큰 목록 조회"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, token, name, created_at, last_used_at, expires_at, is_active
               FROM tokens WHERE user_id = ? ORDER BY created_at DESC""",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def revoke_token(token_id: int, user_id: int) -> bool:
    """토큰 비활성화"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tokens SET is_active = 0 WHERE id = ? AND user_id = ?",
            (token_id, user_id)
        )
        return cursor.rowcount > 0


def delete_token(token_id: int, user_id: int) -> bool:
    """토큰 삭제"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM tokens WHERE id = ? AND user_id = ?",
            (token_id, user_id)
        )
        return cursor.rowcount > 0


# ============ 토큰으로 Credentials 조회 ============

def get_credentials_by_token(token: str) -> Optional[dict]:
    """토큰으로 사용자 credentials 조회"""
    user_id = validate_token(token)
    if not user_id:
        return None
    return get_user_credentials(user_id)


# 앱 시작 시 데이터베이스 초기화
init_database()
