"""
기본 테스트
"""
import pytest
from datetime import datetime, date


class TestConfig:
    """설정 테스트"""
    
    def test_settings_load(self):
        """설정 로드 테스트"""
        from src.config import get_settings
        settings = get_settings()
        
        assert settings.mcp_host == "0.0.0.0"
        assert settings.mcp_port == 8080
        assert settings.timezone == "Asia/Seoul"
    
    def test_schedule_settings(self):
        """스케줄 설정 테스트"""
        from src.config import get_settings
        settings = get_settings()
        
        assert settings.schedule_first_batch == "12:00"
        assert settings.schedule_second_batch == "15:30"
        assert settings.tracking_interval_minutes == 30


class TestDatabase:
    """데이터베이스 테스트"""
    
    def test_models_import(self):
        """모델 임포트 테스트"""
        from src.database import (
            Product, Order, OrderItem, StockHistory,
            Claim, DeliveryTracking, ProcessingLog
        )
        
        assert Product is not None
        assert Order is not None
    
    def test_enums(self):
        """Enum 테스트"""
        from src.database import (
            ChannelType, OrderStatus, ClaimType,
            ClaimStatus, DeliveryStatus, StockChangeReason
        )
        
        assert ChannelType.NAVER.value == "naver"
        assert ChannelType.COUPANG.value == "coupang"
        assert OrderStatus.NEW.value == "new"
        assert OrderStatus.SHIPPED.value == "shipped"


class TestChannels:
    """채널 API 테스트"""
    
    def test_naver_client_init(self):
        """네이버 클라이언트 초기화 테스트"""
        from src.channels.naver import NaverCommerceClient
        
        client = NaverCommerceClient(
            client_id="test_id",
            client_secret="test_secret",
            seller_id="test_seller"
        )
        
        assert client.channel_name == "naver"
        assert client.client_id == "test_id"
    
    def test_coupang_client_init(self):
        """쿠팡 클라이언트 초기화 테스트"""
        from src.channels.coupang import CoupangWingClient
        
        client = CoupangWingClient(
            vendor_id="test_vendor",
            access_key="test_access",
            secret_key="test_secret"
        )
        
        assert client.channel_name == "coupang"
        assert client.vendor_id == "test_vendor"


class TestNotifications:
    """알림 테스트"""
    
    def test_telegram_notifier_init(self):
        """텔레그램 알림 초기화 테스트"""
        from src.notifications import TelegramNotifier
        
        notifier = TelegramNotifier(
            bot_token="test_token",
            chat_id="test_chat"
        )
        
        assert notifier.bot_token == "test_token"
        assert notifier.chat_id == "test_chat"
    
    def test_notification_manager(self):
        """알림 매니저 테스트"""
        from src.notifications import NotificationManager
        
        manager = NotificationManager()
        
        assert manager.telegram is None
        assert manager.slack is None
        assert manager.email is None


class TestUtils:
    """유틸리티 테스트"""
    
    def test_date_formatting(self):
        """날짜 포맷팅 테스트"""
        test_date = datetime(2024, 1, 15, 12, 30, 0)
        formatted = test_date.strftime("%Y-%m-%d %H:%M:%S")
        
        assert formatted == "2024-01-15 12:30:00"
    
    def test_currency_formatting(self):
        """통화 포맷팅 테스트"""
        amount = 1250000
        formatted = f"{amount:,}원"
        
        assert formatted == "1,250,000원"
