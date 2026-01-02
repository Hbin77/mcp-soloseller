# 변경 로그 (Changelog)

이 프로젝트의 모든 주목할 만한 변경사항을 이 파일에 기록합니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/)를 기반으로 하며,
이 프로젝트는 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [Unreleased]

### 계획됨
- CJ대한통운 실제 송장 발급 API 연동
- 11번가 채널 추가
- 지마켓/옥션 채널 추가
- 다국어 지원 (영어, 일본어)

---

## [1.0.0] - 2024-XX-XX

### 🎉 최초 릴리스

#### 추가됨

**핵심 기능**
- 📦 다채널 주문 통합 (네이버 스마트스토어, 쿠팡)
- 🏷️ 자동 송장 처리 (1차 12:00, 2차 15:30)
- 📊 실시간 재고 관리 및 채널 동기화
- 🔔 알림 시스템 (텔레그램, Slack, 이메일)
- 🤖 Claude MCP 연동

**웹 관리 UI**
- 📊 대시보드 (오늘 주문/매출/배송 현황)
- 📦 주문 관리 (목록, 필터, 수동 처리)
- 📋 상품/재고 관리
- 🔄 반품/교환 관리
- ⚙️ 설정 (API 키, 스케줄, 알림)
- 🧙 설정 마법사

**API**
- REST API (Swagger 문서 자동 생성)
- MCP Tools (22개 도구)
- 웹훅 지원 (발송/수신)

**내보내기**
- Excel 내보내기 (주문, 상품, 리포트)
- CSV 내보내기
- 송장 라벨 PDF 생성
- 데이터 백업/복원

**보안**
- API 키 인증
- 레이트 리미팅
- HMAC 서명 검증

**배포**
- Docker 지원
- Docker Compose
- 시놀로지 NAS 배포 가이드
- 원클릭 설치 스크립트

---

## 버전 관리 정책

- **Major (X.0.0)**: 하위 호환성이 없는 변경
- **Minor (0.X.0)**: 하위 호환되는 기능 추가
- **Patch (0.0.X)**: 하위 호환되는 버그 수정

[Unreleased]: https://github.com/YOUR_USERNAME/shop-mcp-server/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/YOUR_USERNAME/shop-mcp-server/releases/tag/v1.0.0
