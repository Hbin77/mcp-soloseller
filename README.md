# SoloSeller - 쇼핑몰 자동화 MCP 서버

쿠팡 주문 조회 → CJ대한통운 송장 발급 → 쿠팡 송장 등록을 자동화합니다.

## 기능
- 쿠팡 WING API 연동 (주문 조회, 송장 등록)
- CJ대한통운 DX API 연동 (운송장 발급, 접수)
- MCP 프로토콜 지원 (Claude Desktop 등 AI 어시스턴트 연동)
- 웹 UI (회원가입, API 키 관리, 토큰 발급)

## MCP 도구
| 도구 | 설명 |
|------|------|
| check_config | 설정 상태 확인 |
| get_orders | 쿠팡 신규 주문 조회 |
| issue_invoice | CJ대한통운 송장 발급 |
| register_invoice | 쿠팡 송장 등록 |
| process_orders | 전체 자동 처리 (조회→발급→등록) |

## 빠른 시작

### 1. 설치
```bash
pip install -r requirements.txt
cp .env.example .env
# .env 파일에 API 키 입력
```

### 2. Claude Desktop에서 사용
`claude_desktop_config.json`에 추가:
```json
{
  "mcpServers": {
    "soloseller": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/shop-mcp-server"
    }
  }
}
```

### 3. 웹 서버로 사용
```bash
python app.py
# http://localhost:8000 접속
```

## 설정

### 쿠팡 WING API
1. [쿠팡 WING](https://wing.coupang.com) 접속
2. 판매자정보 → OPEN API 키 발급
3. IP 주소 허용 목록에 서버 IP 추가

### CJ대한통운 DX API
1. [CJ대한통운 API 포털](https://dxapi.cjlogistics.com) 접속
2. 계약이관 (고객코드 필요)
3. 고객코드 + 사업자등록번호 입력

### 발송인 정보
택배 발송에 필요한 발송인 이름, 전화번호, 주소, 우편번호를 설정합니다.

## 프로젝트 구조
```
├── app.py              # FastAPI 웹 서버
├── server.py           # MCP stdio 서버 (Claude Desktop용)
├── auth.py             # 인증/인가
├── database.py         # SQLite 사용자 DB
├── models.py           # 데이터 모델
├── tools/
│   ├── orders.py       # 주문 조회
│   ├── shipping.py     # 송장 발급/등록
│   └── config.py       # 설정 확인
├── channels/
│   └── coupang.py      # 쿠팡 WING API
├── carriers/
│   └── cj.py           # CJ대한통운 DX API
├── test_flow.py        # 통합 테스트
└── .env.example        # 환경변수 예시
```
