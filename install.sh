#!/bin/bash

# ============================================
# 쇼핑몰 자동화 MCP 서버 원클릭 설치 스크립트
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🛒 쇼핑몰 자동화 MCP 서버 설치 스크립트               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 시스템 체크
check_requirements() {
    echo -e "${YELLOW}[1/5] 시스템 요구사항 확인 중...${NC}"
    
    # Docker 체크
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker가 설치되어 있지 않습니다.${NC}"
        echo "Docker 설치: https://docs.docker.com/get-docker/"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker 설치됨${NC}"
    
    # Docker Compose 체크
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ Docker Compose가 설치되어 있지 않습니다.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker Compose 설치됨${NC}"
    
    # Git 체크 (선택사항)
    if command -v git &> /dev/null; then
        echo -e "${GREEN}✅ Git 설치됨${NC}"
    fi
}

# 프로젝트 다운로드
download_project() {
    echo ""
    echo -e "${YELLOW}[2/5] 프로젝트 다운로드 중...${NC}"
    
    INSTALL_DIR="${HOME}/shop-mcp-server"
    
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}⚠️  이미 설치된 디렉토리가 있습니다: $INSTALL_DIR${NC}"
        read -p "덮어쓰시겠습니까? (y/N): " confirm
        if [[ $confirm != [yY] ]]; then
            echo "설치를 취소합니다."
            exit 0
        fi
        rm -rf "$INSTALL_DIR"
    fi
    
    # GitHub에서 다운로드 또는 현재 디렉토리 복사
    if command -v git &> /dev/null; then
        echo "GitHub에서 클론 중..."
        git clone https://github.com/YOUR_USERNAME/shop-mcp-server.git "$INSTALL_DIR" 2>/dev/null || {
            echo "GitHub 클론 실패, 현재 디렉토리에서 복사합니다..."
            mkdir -p "$INSTALL_DIR"
            cp -r . "$INSTALL_DIR/"
        }
    else
        mkdir -p "$INSTALL_DIR"
        cp -r . "$INSTALL_DIR/"
    fi
    
    cd "$INSTALL_DIR"
    echo -e "${GREEN}✅ 프로젝트 다운로드 완료: $INSTALL_DIR${NC}"
}

# 환경 설정
setup_environment() {
    echo ""
    echo -e "${YELLOW}[3/5] 환경 설정 중...${NC}"
    
    if [ ! -f .env ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env 파일 생성됨${NC}"
    else
        echo -e "${YELLOW}⚠️  .env 파일이 이미 존재합니다${NC}"
    fi
    
    # 데이터 디렉토리 생성
    mkdir -p data logs config
    echo -e "${GREEN}✅ 데이터 디렉토리 생성됨${NC}"
}

# Docker 빌드 및 실행
build_and_run() {
    echo ""
    echo -e "${YELLOW}[4/5] Docker 이미지 빌드 및 실행 중...${NC}"
    
    # Docker Compose 버전 확인
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    $COMPOSE_CMD build
    $COMPOSE_CMD up -d
    
    echo -e "${GREEN}✅ 서버 시작됨${NC}"
}

# 완료 메시지
show_completion() {
    echo ""
    echo -e "${YELLOW}[5/5] 설치 완료!${NC}"
    echo ""
    
    # IP 주소 확인
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    🎉 설치 완료!                           ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║  📌 웹 관리 UI:                                            ║${NC}"
    echo -e "${GREEN}║     http://${LOCAL_IP}:8080                               ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║  📌 API 문서 (Swagger):                                    ║${NC}"
    echo -e "${GREEN}║     http://${LOCAL_IP}:8080/docs                          ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║  📌 MCP 연동 (Claude Desktop):                             ║${NC}"
    echo -e "${GREEN}║     http://${LOCAL_IP}:8080/sse                           ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║  🔧 다음 단계:                                             ║${NC}"
    echo -e "${GREEN}║  1. 웹 UI 접속 후 [설정] 메뉴에서 API 키 입력             ║${NC}"
    echo -e "${GREEN}║  2. 스마트스토어/쿠팡 연동 테스트                          ║${NC}"
    echo -e "${GREEN}║  3. 텔레그램 알림 설정 (선택)                              ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}║  📋 유용한 명령어:                                         ║${NC}"
    echo -e "${GREEN}║  • 로그 확인: docker-compose logs -f                       ║${NC}"
    echo -e "${GREEN}║  • 서버 중지: docker-compose down                          ║${NC}"
    echo -e "${GREEN}║  • 서버 재시작: docker-compose restart                     ║${NC}"
    echo -e "${GREEN}║                                                            ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# 메인 실행
main() {
    check_requirements
    download_project
    setup_environment
    build_and_run
    show_completion
}

main
