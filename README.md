# 쇼핑몰 자동화 MCP 서버

Claude와 직접 연동하여 쇼핑몰 주문 관리 및 송장 처리를 자동화하는 MCP 서버

## 주요 기능

- **주문 조회**: 네이버 스마트스토어, 쿠팡에서 신규 주문 조회
- **송장 발급**: 택배사 API로 송장 자동 발급
- **송장 등록**: 쇼핑몰에 송장번호 자동 입력
- **처리 기록**: 매일 엑셀 파일로 로컬 저장

## 지원 플랫폼

### 쇼핑몰
- 네이버 스마트스토어
- 쿠팡 WING

### 택배사
- CJ대한통운
- 한진택배
- 롯데택배
- 로젠택배
- 우체국택배

## 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경 설정
cp .env.example .env
# .env 파일 편집하여 API 키 입력
```

## 환경 설정

`.env` 파일에서 설정:

```bash
# 발송인 정보 (필수)
SENDER_NAME=홍길동
SENDER_PHONE=010-1234-5678
SENDER_ZIPCODE=12345
SENDER_ADDRESS=서울시 강남구 테헤란로 123

# 기본 택배사
DEFAULT_CARRIER=cj

# 네이버 스마트스토어 API
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret
NAVER_SELLER_ID=your_seller_id

# 쿠팡 WING API
COUPANG_VENDOR_ID=your_vendor_id
COUPANG_ACCESS_KEY=your_access_key
COUPANG_SECRET_KEY=your_secret_key

# 택배사 API (사용할 택배사만 설정)
CJ_CUSTOMER_ID=
CJ_API_KEY=
```

## Claude Desktop 연동

`~/.config/claude/claude_desktop_config.json` (Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "shop-automation": {
      "command": "python",
      "args": ["/path/to/shop-mcp-server/server.py"]
    }
  }
}
```

## MCP Tools

| Tool | 설명 |
|------|------|
| `get_orders` | 네이버+쿠팡에서 신규 주문 조회 |
| `issue_invoice` | 송장 발급 |
| `batch_issue_invoices` | 일괄 송장 발급 |
| `register_invoice` | 쇼핑몰에 송장 등록 |
| `batch_register_invoices` | 일괄 송장 등록 |
| `save_processing_log` | 처리 내역 엑셀 저장 |
| `get_processing_history` | 과거 처리 기록 조회 |
| `get_available_carriers` | 택배사 목록/상태 |
| `get_channel_status` | 쇼핑몰 연결 상태 |

## 사용 예시

Claude에게 다음과 같이 요청:

```
"오늘 들어온 주문 확인해줘"
"전체 주문 송장 발급해줘"
"발급된 송장 쇼핑몰에 등록해줘"
"처리 내역 엑셀로 저장해줘"
```

## 프로젝트 구조

```
shop-mcp-server/
├── server.py           # MCP 서버 진입점
├── config.py           # 환경변수 설정
├── models.py           # 데이터 모델
├── tools/              # MCP Tools
│   ├── orders.py       # 주문 조회
│   ├── shipping.py     # 송장 발급/등록
│   └── export.py       # 엑셀 저장
├── channels/           # 쇼핑몰 API
│   ├── naver.py
│   └── coupang.py
├── carriers/           # 택배사 API
│   ├── cj.py
│   ├── hanjin.py
│   ├── lotte.py
│   ├── logen.py
│   └── epost.py
└── storage/            # 저장 모듈
    └── excel_store.py
```

## 라이선스

MIT License
