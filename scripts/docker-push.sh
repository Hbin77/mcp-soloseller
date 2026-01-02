#!/bin/bash

# ============================================
# Docker Hub 배포 스크립트
# ============================================

set -e

# 설정
DOCKER_USERNAME="${DOCKER_USERNAME:-your-username}"
IMAGE_NAME="shop-mcp-server"
VERSION="${VERSION:-latest}"

echo "🐳 Docker Hub 배포를 시작합니다..."
echo "   Image: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

# Docker 로그인 확인
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker가 실행되지 않았습니다."
    exit 1
fi

# 빌드
echo ""
echo "📦 이미지 빌드 중..."
docker build -t ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} .

# latest 태그도 추가
if [ "${VERSION}" != "latest" ]; then
    docker tag ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} ${DOCKER_USERNAME}/${IMAGE_NAME}:latest
fi

# 푸시
echo ""
echo "🚀 Docker Hub에 푸시 중..."
docker push ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}

if [ "${VERSION}" != "latest" ]; then
    docker push ${DOCKER_USERNAME}/${IMAGE_NAME}:latest
fi

echo ""
echo "✅ 배포 완료!"
echo ""
echo "사용 방법:"
echo "  docker pull ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"
echo "  docker run -d -p 8080:8080 ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"
