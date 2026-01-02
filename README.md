<div align="center">

# 🛒 쇼핑몰 자동화 MCP 서버

**다채널 쇼핑몰을 하나로 통합 관리하는 오픈소스 자동화 솔루션**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)

[데모 보기](#-스크린샷) • [빠른 시작](#-빠른-시작) • [문서](#-문서) • [기여하기](#-기여하기)

</div>

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 📦 **다채널 주문 통합** | 스마트스토어, 쿠팡 주문을 한 곳에서 관리 |
| 🏷️ **자동 송장 처리** | 1차(12시), 2차(15:30) 배치로 자동 발송 처리 |
| 📊 **실시간 재고 관리** | 모든 채널의 재고를 자동 동기화 |
| 🔔 **텔레그램 알림** | 주문, 재고 부족, 클레임 실시간 알림 |
| 🤖 **Claude MCP 연동** | AI 어시스턴트로 쇼핑몰 관리 |
| 🖥️ **웹 관리 UI** | 직관적인 대시보드로 손쉽게 관리 |

## 🎯 이런 분께 추천합니다

- ✅ 스마트스토어 + 쿠팡 **동시 운영** 중인 셀러
- ✅ **재고 관리**가 번거로운 분
- ✅ **자동화**로 운영 효율을 높이고 싶은 분
- ✅ **AI(Claude)**로 쇼핑몰을 관리하고 싶은 분

## 📸 스크린샷

<details>
<summary>대시보드</summary>

```
┌─────────────────────────────────────────────────────────────────┐
│  🛒 쇼핑몰 자동화                     📊 대시보드               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ 오늘 주문   │ │ 오늘 매출   │ │ 발송 대기   │ │ 재고 부족 │ │
│  │     32건    │ │  1,250,000  │ │     8건     │ │    3개    │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │  채널별 현황        │  │  배치 처리                      │  │
│  │  🟢 스마트스토어    │  │  [▶ 1차 처리] 12:00            │  │
│  │     15건 / 520,000  │  │  [▶ 2차 처리] 15:30            │  │
│  │  🔴 쿠팡            │  │                                 │  │
│  │     17건 / 730,000  │  │                                 │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

</details>

## 🚀 빠른 시작

### 원클릭 설치 (권장)

```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/shop-mcp-server/main/install.sh | bash
```

### Docker로 설치

```bash
# 1. 프로젝트 클론
git clone https://github.com/YOUR_USERNAME/shop-mcp-server.git
cd shop-mcp-server

# 2. 환경 설정
cp .env.example .env

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
# .env 파일 편집

# 5. 실행
python -m src.main
```

## ⚙️ 설정

### 1. 네이버 스마트스토어 API

1. [네이버 커머스API센터](https://apicenter.commerce.naver.com) 접속
2. 개발업체 계정 생성
3. 애플리케이션 등록
4. Client ID, Client Secret 발급

### 2. 쿠팡 WING API

1. [쿠팡 WING](https://wing.coupang.com) 로그인
2. 판매자정보 → 추가판매정보 → OPEN API 키 발급
3. Access Key, Secret Key 발급

### 3. 텔레그램 알림 (선택)

1. [@BotFather](https://t.me/botfather)에서 봇 생성
2. 봇 토큰 발급
3. 채팅방 ID 확인

## 🔧 환경 변수

```env
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
```

## 🤖 Claude MCP 연동

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

사용자: 1차 송장 처리 실행해줘
Claude: 1차 송장 처리를 시작합니다...
        ✅ 완료! 8건 주문 수집, 8건 발주확인, 8건 송장출력
```

## 📅 스케줄

| 작업 | 시간 | 설명 |
|------|------|------|
| 1차 송장 처리 | 12:00 | 오전 주문 일괄 발송 |
| 2차 송장 처리 | 15:30 | 오후 주문 일괄 발송 |
| 배송 추적 | 30분 간격 | 배송 상태 자동 업데이트 |

## 📁 프로젝트 구조

```
shop-mcp-server/
├── src/
│   ├── main.py              # 메인 서버
│   ├── config.py            # 설정 관리
│   ├── database.py          # DB 모델
│   ├── api/                  # REST API
│   │   ├── dashboard.py
│   │   ├── orders.py
│   │   ├── products.py
│   │   ├── settings.py
│   │   └── claims.py
│   ├── channels/            # 채널 API
│   │   ├── naver.py
│   │   └── coupang.py
│   ├── notifications/       # 알림
│   └── static/              # 웹 UI
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── install.sh
```

## 🛠️ API 문서

서버 실행 후 `/docs`에서 Swagger UI를 확인할 수 있습니다.

### 주요 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/dashboard/summary` | 대시보드 요약 |
| GET | `/api/v1/orders` | 주문 목록 |
| POST | `/api/v1/orders/collect` | 주문 수집 |
| POST | `/api/v1/orders/process-batch/{n}` | 배치 처리 |
| GET | `/api/v1/products` | 상품 목록 |
| POST | `/api/v1/products/{id}/stock` | 재고 업데이트 |
| GET | `/api/v1/claims/sync` | 클레임 동기화 |
| POST | `/api/v1/settings/naver` | 네이버 설정 |

## 🐳 시놀로지 NAS 배포

시놀로지 NAS에서 Docker로 실행할 수 있습니다.

```bash
# SSH 접속
ssh admin@YOUR_NAS_IP

# 디렉토리 생성
cd /volume1/docker
git clone https://github.com/YOUR_USERNAME/shop-mcp-server.git
cd shop-mcp-server

# 실행
docker-compose up -d
```

## 📄 라이선스

MIT License - 자유롭게 사용, 수정, 배포할 수 있습니다.

## 🤝 기여하기

기여를 환영합니다!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 지원

- 🐛 버그 리포트: [Issues](https://github.com/YOUR_USERNAME/shop-mcp-server/issues)
- 💡 기능 제안: [Discussions](https://github.com/YOUR_USERNAME/shop-mcp-server/discussions)

## ⭐ Star History

이 프로젝트가 도움이 되셨다면 ⭐ 를 눌러주세요!

---

<div align="center">

Made with ❤️ for Korean e-commerce sellers

</div>
