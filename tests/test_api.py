"""
API 테스트
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime


@pytest.fixture
def client():
    """테스트 클라이언트"""
    from src.main import app
    return TestClient(app)


class TestHealthCheck:
    """헬스체크 테스트"""
    
    def test_health_endpoint(self, client):
        """헬스체크 엔드포인트 테스트"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestDashboardAPI:
    """대시보드 API 테스트"""
    
    def test_dashboard_summary(self, client):
        """대시보드 요약 API 테스트"""
        response = client.get("/api/v1/dashboard/summary")
        
        assert response.status_code == 200
        data = response.json()
        assert "today" in data
        assert "pending" in data
        assert "alerts" in data
    
    def test_orders_chart(self, client):
        """주문 차트 API 테스트"""
        response = client.get("/api/v1/dashboard/chart/orders?days=7")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 7
    
    def test_recent_orders(self, client):
        """최근 주문 API 테스트"""
        response = client.get("/api/v1/dashboard/recent-orders?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestOrdersAPI:
    """주문 API 테스트"""
    
    def test_list_orders(self, client):
        """주문 목록 API 테스트"""
        response = client.get("/api/v1/orders")
        
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert "total" in data
        assert "page" in data
    
    def test_list_orders_with_filter(self, client):
        """필터링된 주문 목록 API 테스트"""
        response = client.get("/api/v1/orders?status=new&channel=naver")
        
        assert response.status_code == 200
    
    def test_pending_orders(self, client):
        """발송 대기 주문 API 테스트"""
        response = client.get("/api/v1/orders/pending")
        
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert "count" in data


class TestProductsAPI:
    """상품 API 테스트"""
    
    def test_list_products(self, client):
        """상품 목록 API 테스트"""
        response = client.get("/api/v1/products")
        
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "total" in data
    
    def test_low_stock_products(self, client):
        """재고 부족 상품 API 테스트"""
        response = client.get("/api/v1/products/low-stock")
        
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "count" in data
    
    def test_create_product(self, client):
        """상품 등록 API 테스트"""
        product_data = {
            "sku": "TEST-001",
            "name": "테스트 상품",
            "stock_quantity": 100,
            "price": 10000
        }
        
        response = client.post("/api/v1/products", json=product_data)
        
        # 이미 존재할 수 있으므로 200 또는 400
        assert response.status_code in [200, 400]


class TestSettingsAPI:
    """설정 API 테스트"""
    
    def test_get_settings(self, client):
        """설정 조회 API 테스트"""
        response = client.get("/api/v1/settings")
        
        assert response.status_code == 200
        data = response.json()
        assert "naver" in data
        assert "coupang" in data
        assert "telegram" in data
        assert "schedule" in data
    
    def test_get_scheduler_jobs(self, client):
        """스케줄러 작업 조회 API 테스트"""
        response = client.get("/api/v1/settings/scheduler/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data


class TestClaimsAPI:
    """클레임 API 테스트"""
    
    def test_list_claims(self, client):
        """클레임 목록 API 테스트"""
        response = client.get("/api/v1/claims")
        
        assert response.status_code == 200
        data = response.json()
        assert "claims" in data
        assert "total" in data
    
    def test_claim_stats(self, client):
        """클레임 통계 API 테스트"""
        response = client.get("/api/v1/claims/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "by_type" in data
        assert "by_status" in data
