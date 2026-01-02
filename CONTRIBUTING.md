# 기여 가이드 (Contributing Guide)

먼저, 이 프로젝트에 관심을 가져주셔서 감사합니다! 🎉

## 🤝 기여 방법

### 버그 리포트

버그를 발견하셨나요? [Issues](https://github.com/YOUR_USERNAME/shop-mcp-server/issues)에 다음 정보와 함께 신고해 주세요:

1. **버그 설명**: 문제가 무엇인가요?
2. **재현 방법**: 어떻게 하면 이 버그를 볼 수 있나요?
3. **예상 동작**: 원래 어떻게 동작해야 하나요?
4. **환경**: OS, Python 버전, Docker 버전 등

### 기능 제안

새로운 기능을 제안하고 싶으신가요? [Discussions](https://github.com/YOUR_USERNAME/shop-mcp-server/discussions)에서 논의해 주세요!

### Pull Request

1. 이 저장소를 Fork 합니다
2. 새 브랜치를 만듭니다 (`git checkout -b feature/amazing-feature`)
3. 변경사항을 커밋합니다 (`git commit -m 'Add amazing feature'`)
4. 브랜치에 Push 합니다 (`git push origin feature/amazing-feature`)
5. Pull Request를 생성합니다

## 📋 개발 환경 설정

```bash
# 1. 저장소 클론
git clone https://github.com/YOUR_USERNAME/shop-mcp-server.git
cd shop-mcp-server

# 2. 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 개발 의존성 설치
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. 환경 설정
cp .env.example .env

# 5. 테스트 실행
pytest tests/ -v
```

## 🎨 코드 스타일

- **Python**: PEP 8 스타일 가이드를 따릅니다
- **포매터**: Black (기본 설정)
- **Import 정렬**: isort
- **린터**: flake8

```bash
# 코드 포맷팅
black src/
isort src/

# 린트 검사
flake8 src/
```

## 📝 커밋 메시지

의미 있는 커밋 메시지를 작성해 주세요:

```
feat: 새로운 기능 추가
fix: 버그 수정
docs: 문서 변경
style: 코드 포맷팅
refactor: 코드 리팩토링
test: 테스트 추가/수정
chore: 빌드/설정 변경
```

예시:
```
feat: 11번가 채널 연동 추가
fix: 네이버 API 토큰 갱신 오류 수정
docs: README에 설치 가이드 추가
```

## 🧪 테스트

- 새로운 기능을 추가할 때는 테스트도 함께 작성해 주세요
- 기존 테스트가 모두 통과해야 PR이 머지됩니다

```bash
# 전체 테스트
pytest tests/ -v

# 특정 테스트
pytest tests/test_api.py -v

# 커버리지 포함
pytest tests/ -v --cov=src
```

## 📁 프로젝트 구조

```
shop-mcp-server/
├── src/
│   ├── main.py           # 메인 서버
│   ├── config.py         # 설정
│   ├── database.py       # DB 모델
│   ├── security.py       # 보안/인증
│   ├── api/              # REST API 라우터
│   ├── channels/         # 채널 API 클라이언트
│   ├── notifications/    # 알림 시스템
│   ├── utils/            # 유틸리티
│   └── static/           # 웹 UI
├── tests/                # 테스트
├── scripts/              # 스크립트
└── docs/                 # 문서
```

## 🔒 보안

보안 취약점을 발견하셨나요? **공개 Issue로 올리지 마시고** 비공개로 알려주세요:

- 이메일: security@example.com
- 또는 GitHub Security Advisory 사용

## 📄 라이선스

이 프로젝트에 기여하시면, 귀하의 기여물은 MIT 라이선스 하에 배포됩니다.

## 💬 질문이 있으신가요?

- [Discussions](https://github.com/YOUR_USERNAME/shop-mcp-server/discussions)에서 질문해 주세요
- 친절하게 답변해 드리겠습니다! 😊

---

다시 한번 관심 가져주셔서 감사합니다! 🙏
