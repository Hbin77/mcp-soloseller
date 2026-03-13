"""데이터베이스 모듈 - SQLite 기반 사용자/토큰 관리"""
import sqlite3
import hashlib
import secrets
import os
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
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
                email_verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 이메일 인증 코드 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                type TEXT DEFAULT 'register',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0,
                attempts INTEGER DEFAULT 0
            )
        """)

        # API 키 설정 테이블 (MVP: 쿠팡 + CJ대한통운)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                -- 쿠팡
                coupang_vendor_id TEXT,
                coupang_access_key TEXT,
                coupang_secret_key TEXT,
                -- CJ대한통운
                cj_customer_id TEXT,
                cj_biz_reg_num TEXT,
                -- 발송인 정보
                sender_name TEXT,
                sender_phone TEXT,
                sender_zipcode TEXT,
                sender_address TEXT,
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
    """비밀번호 해싱 (bcrypt)"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """비밀번호 검증"""
    # bcrypt 해시인지 확인 (bcrypt 해시는 $2로 시작)
    if hashed.startswith('$2'):
        return bcrypt.checkpw(password.encode(), hashed.encode())
    # 레거시 SHA256 해시 지원 (마이그레이션용)
    return hashlib.sha256(password.encode()).hexdigest() == hashed


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


def create_user_with_hash(email: str, password_hash: str) -> Optional[int]:
    """사용자 생성 (이미 해싱된 비밀번호 사용)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, password_hash)
            )
            user_id = cursor.lastrowid
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
            "SELECT id, password_hash FROM users WHERE email = ?",
            (email,)
        )
        row = cursor.fetchone()
        if row and verify_password(password, row["password_hash"]):
            # 레거시 SHA256 해시를 bcrypt로 업그레이드
            if not row["password_hash"].startswith('$2'):
                cursor.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (hash_password(password), row["id"])
                )
            return row["id"]
        return None


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
        'coupang_vendor_id', 'coupang_access_key', 'coupang_secret_key',
        'cj_customer_id', 'cj_biz_reg_num',
        'sender_name', 'sender_phone', 'sender_zipcode', 'sender_address'
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
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

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


# ============ 이메일 인증 ============

def generate_verification_code() -> str:
    """6자리 인증 코드 생성 (암호학적으로 안전한 방식)"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def create_verification_code(email: str, code_type: str = "register", expires_minutes: int = 10) -> str:
    """인증 코드 생성 및 저장"""
    code = generate_verification_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

    with get_connection() as conn:
        cursor = conn.cursor()
        # 기존 미사용 코드 무효화
        cursor.execute(
            "UPDATE verification_codes SET used = 1 WHERE email = ? AND type = ? AND used = 0",
            (email, code_type)
        )
        # 새 코드 생성
        cursor.execute(
            "INSERT INTO verification_codes (email, code, type, expires_at) VALUES (?, ?, ?, ?)",
            (email, code, code_type, expires_at)
        )
    return code


def verify_code(email: str, code: str, code_type: str = "register", max_attempts: int = 5) -> bool:
    """인증 코드 확인 (최대 시도 횟수 제한)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, code, attempts FROM verification_codes
               WHERE email = ? AND type = ? AND used = 0
               AND expires_at > CURRENT_TIMESTAMP
               ORDER BY created_at DESC LIMIT 1""",
            (email, code_type)
        )
        row = cursor.fetchone()

        if not row:
            return False

        # 시도 횟수 초과 확인
        if row["attempts"] >= max_attempts:
            cursor.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (row["id"],))
            return False

        # 시도 횟수 증가
        cursor.execute(
            "UPDATE verification_codes SET attempts = attempts + 1 WHERE id = ?",
            (row["id"],)
        )

        if secrets.compare_digest(code, row["code"]):
            cursor.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (row["id"],))
            return True
        return False


def mark_email_verified(email: str) -> bool:
    """이메일 인증 완료 처리"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (email,))
        return cursor.rowcount > 0


def is_email_verified(email: str) -> bool:
    """이메일 인증 여부 확인"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT email_verified FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return bool(row and row["email_verified"])


def get_user_by_email(email: str) -> Optional[dict]:
    """이메일로 사용자 조회"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, email_verified, created_at FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None


def migrate_database():
    """기존 데이터베이스 마이그레이션"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # verification_codes 테이블에 attempts 컬럼 추가 (기존 DB 호환)
        try:
            cursor.execute("ALTER TABLE verification_codes ADD COLUMN attempts INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 이미 존재하는 경우 무시

        # cj_api_key → cj_biz_reg_num 마이그레이션
        try:
            cursor.execute("ALTER TABLE user_credentials RENAME COLUMN cj_api_key TO cj_biz_reg_num")
        except sqlite3.OperationalError:
            pass  # 이미 변경되었거나 컬럼이 없는 경우 무시


# 앱 시작 시 데이터베이스 초기화
init_database()
migrate_database()
