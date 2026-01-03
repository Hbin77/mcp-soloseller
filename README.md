<div align="center">

# 쇼핑몰 자동화 MCP 서버

**다채널 쇼핑몰을 하나로 통합 관리하는 오픈소스 자동화 솔루션**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)

[빠른 시작](#빠른-시작) | [설정 가이드](#설정) | [API 문서](#api-문서) | [MCP 연동](#claude-mcp-연동)

</div>

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **다채널 주문 통합** | 스마트스토어, 쿠팡 주문을 한 곳에서 관리 |
| **자동 송장 처리** | 1차(12시), 2차(15:30) 배치로 자동 발송 처리 |
| **실시간 재고 관리** | 모든 채널의 재고를 자동 동기화 |
| **텔레그램 알림** | 주문, 재고 부족, 클레임 실시간 알림 |
| **Claude MCP 연동** | AI 어시스턴트로 쇼핑몰 관리 |
| **웹 관리 UI** | 직관적인 대시보드로 손쉽게 관리 |

---

## 빠른 시작

### Docker 설치 (권장)

```bash
# 1. 프로젝트 클론
git clone https://github.com/YOUR_USERNAME/shop-mcp-server.git
cd shop-mcp-server

# 2. 환경 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 입력

# 3. 실행
docker-compose up -d

# 4. 접속
# 웹 UI: http://localhost:8080
# API 문서: http://localhost:8080/docs
```

### 수동 설치

```bash
# 1. 프로젝트 클론
git clone https://github.com/YOUR_USERNAME/shop-mcp-server.git
cd shop-mcp-server

# 2. 가상환경 설정
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경 설정
cp .env.example .env

# 5. 실행
python -m src.main
```

---

## 설정

### 네이버 스마트스토어 API

1. [네이버 커머스API센터](https://apicenter.commerce.naver.com) 접속
2. 개발업체 계정 생성
3. 애플리케이션 등록
4. Client ID, Client Secret 발급

### 쿠팡 WING API

1. [쿠팡 WING](https://wing.coupang.com) 로그인
2. 판매자정보 → 추가판매정보 → OPEN API 키 발급
3. Access Key, Secret Key 발급

### 텔레그램 알림 (선택)

1. [@BotFather](https://t.me/botfather)에서 봇 생성
2. 봇 토큰 발급
3. 채팅방 ID 확인

### 환경 변수

```env
# 서버 설정
MCP_HOST=0.0.0.0
MCP_PORT=8080

# 네이버 스마트스토어
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret
NAVER_SELLER_ID=your_seller_id

# 쿠팡
COUPANG_VENDOR_ID=your_vendor_id
COUPANG_ACCESS_KEY=your_access_key
COUPANG_SECRET_KEY=your_secret_key

# 텔레그램 (선택)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 스케줄
SCHEDULE_FIRST_BATCH=12:00
SCHEDULE_SECOND_BATCH=15:30

# 보안 (프로덕션에서 필수)
CORS_ORIGINS=https://your-domain.com
```

---

## 아키텍처

### 프로젝트 구조

```
shop-mcp-server/
├── src/
│   ├── main.py              # 메인 서버 (FastAPI + MCP + Streamable HTTP)
│   ├── config.py            # 설정 관리
│   ├── database.py          # SQLAlchemy ORM 모델
│   ├── auth.py              # PlayMCP 인증 (HTTP 헤더 기반)
│   ├── security.py          # 보안/인증
│   ├── webhooks.py          # 웹훅 관리
│   ├── api/                  # REST API 라우터
│   │   ├── dashboard.py     # 대시보드
│   │   ├── orders.py        # 주문 관리
│   │   ├── products.py      # 상품/재고 관리
│   │   ├── settings.py      # 설정
│   │   ├── claims.py        # 반품/교환/취소
│   │   ├── export.py        # 내보내기
│   │   ├── auth.py          # 인증
│   │   └── webhooks.py      # 웹훅 API
│   ├── channels/            # 채널 API 클라이언트
│   │   ├── naver.py         # 네이버 커머스 API
│   │   └── coupang.py       # 쿠팡 WING API
│   ├── notifications/       # 알림 시스템
│   ├── shipping/            # 배송 추적
│   ├── utils/               # 유틸리티
│   └── static/              # 웹 UI
├── tests/                   # 테스트
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### 핵심 컴포넌트

| 컴포넌트 | 설명 |
|----------|------|
| `src/main.py` | FastAPI REST API + MCP 서버 (SSE + Streamable HTTP 전송 지원) |
| `src/auth.py` | PlayMCP 인증 모듈 (HTTP 헤더에서 사용자별 API 키 추출) |
| `src/database.py` | SQLAlchemy 비동기 ORM 모델 (Product, Order, Claim 등) |
| `src/config.py` | Pydantic Settings 기반 환경 설정 |
| `src/channels/` | 네이버, 쿠팡 API 클라이언트 (사용자별 인증 지원) |
| `src/notifications/` | 텔레그램, Slack, 이메일 알림 |

### 스케줄 작업

| 작업 | 시간 | 설명 |
|------|------|------|
| 1차 송장 처리 | 12:00 | 오전 주문 일괄 발송 |
| 2차 송장 처리 | 15:30 | 오후 주문 일괄 발송 |
| 배송 추적 | 30분 간격 | 배송 상태 자동 업데이트 |

---

## API 문서

서버 실행 후 `/docs`에서 Swagger UI를 확인할 수 있습니다.

### 주요 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/dashboard/summary` | 대시보드 요약 |
| GET | `/api/v1/orders` | 주문 목록 |
| GET | `/api/v1/orders/pending` | 발송 대기 주문 |
| POST | `/api/v1/orders/collect` | 주문 수집 |
| POST | `/api/v1/orders/process-batch/{n}` | 배치 처리 |
| GET | `/api/v1/products` | 상품 목록 |
| GET | `/api/v1/products/low-stock` | 재고 부족 상품 |
| POST | `/api/v1/products/{id}/stock` | 재고 업데이트 |
| GET | `/api/v1/claims` | 클레임 목록 |
| GET | `/api/v1/claims/sync` | 클레임 동기화 |
| GET | `/api/v1/settings` | 설정 조회 |
| GET | `/api/v1/export/orders/excel` | 주문 엑셀 내보내기 |
| GET | `/health` | 헬스체크 |

---

## Claude MCP 연동

Claude Desktop에서 AI로 쇼핑몰을 관리할 수 있습니다.

### claude_desktop_config.json

```json
{
  "mcpServers": {
    "shop-automation": {
      "url": "http://localhost:8080/sse",
      "transport": "sse"
    }
  }
}
```

### MCP 도구 목록

| 카테고리 | 도구 | 설명 |
|----------|------|------|
| 주문 | `get_new_orders` | 신규 주문 수집 |
| 주문 | `get_pending_orders` | 발송 대기 주문 조회 |
| 주문 | `process_batch` | 배치 처리 실행 |
| 재고 | `get_stock` | 재고 조회 |
| 재고 | `update_stock` | 재고 업데이트 |
| 재고 | `get_low_stock_alerts` | 재고 부족 알림 |
| 재고 | `sync_stock_all_channels` | 전체 채널 재고 동기화 |
| 리포트 | `get_daily_report` | 일일 리포트 |
| 리포트 | `get_processing_logs` | 처리 이력 조회 |
| 클레임 | `get_claims` | 클레임 조회 |
| 상품 | `add_product` | 상품 등록 |
| 상품 | `list_products` | 상품 목록 |

### 사용 예시

```
사용자: 오늘 주문 현황 알려줘
Claude: 오늘 총 32건의 주문이 들어왔습니다.
        - 스마트스토어: 15건 (520,000원)
        - 쿠팡: 17건 (730,000원)
        발송 대기 중인 주문은 8건입니다.

사용자: 재고 부족한 상품 확인해줘
Claude: 재고 부족 상품 3개가 있습니다:
        - 상품A: 2개 (임계값: 5)
        - 상품B: 3개 (임계값: 5)
        - 상품C: 1개 (임계값: 5)
```

---

## PlayMCP 연동

[카카오 PlayMCP](https://playmcp.kakao.com)에 이 MCP 서버를 등록하여 다양한 AI 서비스에서 사용할 수 있습니다.

### PlayMCP 등록 방법

1. **서버 배포**: 공개적으로 접근 가능한 HTTPS 엔드포인트 필요
2. **PlayMCP 개발자 콘솔 접속**: https://playmcp.kakao.com
3. **MCP 서버 등록**:
   - 엔드포인트: `https://your-domain.com/mcp`
   - 전송 방식: Streamable HTTP
   - 인증 방식: Key/Token (HTTP 헤더)

### 인증 헤더 설정

PlayMCP에서 사용자별로 API 키를 입력받아 전달합니다:

| 헤더 | 설명 | 필수 |
|------|------|------|
| `X-Naver-Client-Id` | 네이버 커머스 API Client ID | 선택 |
| `X-Naver-Client-Secret` | 네이버 커머스 API Client Secret | 선택 |
| `X-Naver-Seller-Id` | 네이버 스마트스토어 판매자 ID | 선택 |
| `X-Coupang-Vendor-Id` | 쿠팡 WING Vendor ID | 선택 |
| `X-Coupang-Access-Key` | 쿠팡 WING Access Key | 선택 |
| `X-Coupang-Secret-Key` | 쿠팡 WING Secret Key | 선택 |

### MCP 엔드포인트

| 엔드포인트 | 설명 |
|------------|------|
| `POST /mcp` | Streamable HTTP MCP 엔드포인트 (PlayMCP용) |
| `GET /sse` | SSE 엔드포인트 (Claude Desktop용) |
| `GET /mcp/info` | 서버 메타데이터 (등록 시 참조용) |

### 사용자 경험

```
1. PlayMCP에서 "쇼핑몰 자동화" MCP 서버 선택
2. 자신의 네이버/쿠팡 API 키 입력 (최초 1회)
3. AI 채팅으로 쇼핑몰 관리 시작!

예시:
사용자: 오늘 주문 현황 알려줘
AI: 네이버 스마트스토어 15건, 쿠팡 17건의 주문이 있습니다.
```

---

## 개발

### 개발 환경 설정

```bash
# 의존성 설치
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 테스트 실행
pytest tests/ -v

# 커버리지 포함 테스트
pytest tests/ -v --cov=src

# 코드 포맷팅
black src/
isort src/

# 린트 검사
flake8 src/
```

### 커밋 메시지 컨벤션

```
feat: 새로운 기능 추가
fix: 버그 수정
docs: 문서 변경
style: 코드 포맷팅
refactor: 코드 리팩토링
test: 테스트 추가/수정
chore: 빌드/설정 변경
```

### 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/amazing-feature`)
3. Commit your Changes (`git commit -m 'feat: Add amazing feature'`)
4. Push to the Branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 변경 로그

### v1.0.0

**핵심 기능**
- 다채널 주문 통합 (네이버 스마트스토어, 쿠팡)
- 자동 송장 처리 (1차 12:00, 2차 15:30)
- 실시간 재고 관리 및 채널 동기화
- 알림 시스템 (텔레그램, Slack, 이메일)
- Claude MCP 연동

**웹 관리 UI**
- 대시보드 (오늘 주문/매출/배송 현황)
- 주문/상품/재고/클레임 관리
- 설정 마법사

**내보내기**
- Excel/CSV 내보내기
- 송장 라벨 PDF 생성
- 데이터 백업/복원

### 계획된 기능
- CJ대한통운 실제 송장 발급 API 연동
- 11번가 채널 추가
- 지마켓/옥션 채널 추가

---

## 라이선스

MIT License - 자유롭게 사용, 수정, 배포할 수 있습니다.

---

## 지원

- 버그 리포트: [Issues](https://github.com/YOUR_USERNAME/shop-mcp-server/issues)
- 기능 제안: [Discussions](https://github.com/YOUR_USERNAME/shop-mcp-server/discussions)
- 이메일 문의: [phb007298@gmail.com](mailto:phb007298@gmail.com)

---

<div align="center">

**이 프로젝트가 도움이 되셨다면 Star를 눌러주세요!**

Made with love for Korean e-commerce sellers

</div>
