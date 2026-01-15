"""
설정 관리 API
API 키, 알림 설정, 스케줄 설정 등
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import json
from pathlib import Path

router = APIRouter(prefix="/settings", tags=["Settings"])

# 설정 파일 경로
SETTINGS_FILE = Path("data/settings.json")


def load_settings() -> dict:
    """설정 파일 로드"""
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(settings: dict):
    """설정 파일 저장"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


class NaverSettings(BaseModel):
    client_id: str
    client_secret: str
    seller_id: str


class CoupangSettings(BaseModel):
    vendor_id: str
    access_key: str
    secret_key: str


class TelegramSettings(BaseModel):
    bot_token: str
    chat_id: str


class ScheduleSettings(BaseModel):
    first_batch: str = "12:00"
    second_batch: str = "15:30"
    tracking_interval: int = 30


class StockSettings(BaseModel):
    alert_threshold: int = 5


class SenderSettings(BaseModel):
    """발송인 정보"""
    name: str
    phone: str
    zipcode: str
    address: str


class CJCarrierSettings(BaseModel):
    """CJ대한통운 설정"""
    customer_id: str
    api_key: str
    contract_code: Optional[str] = None


class HanjinCarrierSettings(BaseModel):
    """한진택배 설정"""
    customer_id: str
    api_key: str


class LotteCarrierSettings(BaseModel):
    """롯데택배 설정"""
    customer_id: str
    api_key: str


class LogenCarrierSettings(BaseModel):
    """로젠택배 설정"""
    customer_id: str
    api_key: str


class EpostCarrierSettings(BaseModel):
    """우체국택배 설정"""
    customer_id: str
    api_key: str


class DefaultCarrierSettings(BaseModel):
    """기본 택배사 설정"""
    carrier: str = "cj"  # cj, hanjin, lotte, logen, epost


@router.get("")
async def get_settings():
    """현재 설정 조회 (민감 정보 마스킹)"""
    from ..config import get_settings
    settings = get_settings()
    
    def mask(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if len(value) <= 4:
            return "****"
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    
    return {
        "naver": {
            "configured": settings.naver_configured,
            "client_id": mask(settings.naver_client_id),
            "seller_id": mask(settings.naver_seller_id)
        },
        "coupang": {
            "configured": settings.coupang_configured,
            "vendor_id": mask(settings.coupang_vendor_id)
        },
        "telegram": {
            "configured": settings.telegram_configured,
            "chat_id": mask(settings.telegram_chat_id)
        },
        "schedule": {
            "first_batch": settings.schedule_first_batch,
            "second_batch": settings.schedule_second_batch,
            "tracking_interval": settings.tracking_interval_minutes
        },
        "stock": {
            "alert_threshold": settings.stock_alert_threshold
        },
        "sender": {
            "configured": settings.sender_configured,
            "name": settings.sender_name,
            "phone": mask(settings.sender_phone),
            "zipcode": settings.sender_zipcode,
            "address": settings.sender_address
        },
        "carriers": {
            "default": settings.default_carrier,
            "cj": {
                "configured": settings.cj_configured,
                "customer_id": mask(settings.cj_customer_id)
            },
            "hanjin": {
                "configured": settings.hanjin_configured,
                "customer_id": mask(settings.hanjin_customer_id)
            },
            "lotte": {
                "configured": settings.lotte_configured,
                "customer_id": mask(settings.lotte_customer_id)
            },
            "logen": {
                "configured": settings.logen_configured,
                "customer_id": mask(settings.logen_customer_id)
            },
            "epost": {
                "configured": settings.epost_configured,
                "customer_id": mask(settings.epost_customer_id)
            }
        }
    }


@router.get("/status")
async def get_connection_status():
    """채널 연결 상태 확인"""
    from ..main import server
    
    status = {
        "naver": {"connected": False, "message": "미설정"},
        "coupang": {"connected": False, "message": "미설정"},
        "telegram": {"connected": False, "message": "미설정"}
    }
    
    # 네이버 연결 테스트
    if server.naver_client:
        try:
            connected = await server.naver_client.authenticate()
            status["naver"] = {
                "connected": connected,
                "message": "연결됨" if connected else "인증 실패"
            }
        except Exception as e:
            status["naver"] = {"connected": False, "message": str(e)}
    
    # 쿠팡 연결 테스트
    if server.coupang_client:
        try:
            connected = await server.coupang_client.authenticate()
            status["coupang"] = {
                "connected": connected,
                "message": "연결됨" if connected else "인증 실패"
            }
        except Exception as e:
            status["coupang"] = {"connected": False, "message": str(e)}
    
    # 텔레그램 테스트
    if server.notifier and server.notifier.telegram:
        try:
            result = await server.notifier.telegram.send("🔔 연결 테스트")
            status["telegram"] = {
                "connected": result.success,
                "message": "연결됨" if result.success else result.error
            }
        except Exception as e:
            status["telegram"] = {"connected": False, "message": str(e)}
    
    return status


@router.post("/naver")
async def update_naver_settings(settings: NaverSettings):
    """네이버 API 설정 업데이트"""
    current = load_settings()
    current["naver"] = settings.model_dump()
    save_settings(current)
    
    # 환경 변수도 업데이트 (런타임)
    os.environ["NAVER_CLIENT_ID"] = settings.client_id
    os.environ["NAVER_CLIENT_SECRET"] = settings.client_secret
    os.environ["NAVER_SELLER_ID"] = settings.seller_id
    
    # 클라이언트 재초기화
    from ..main import server
    from ..channels.naver import NaverCommerceClient
    
    if server.naver_client:
        await server.naver_client.close()
    
    server.naver_client = NaverCommerceClient(
        settings.client_id,
        settings.client_secret,
        settings.seller_id
    )
    
    # 연결 테스트
    connected = await server.naver_client.authenticate()
    
    return {
        "success": True,
        "connected": connected,
        "message": "네이버 API 설정이 저장되었습니다" + (" (연결 성공)" if connected else " (연결 실패)")
    }


@router.post("/coupang")
async def update_coupang_settings(settings: CoupangSettings):
    """쿠팡 API 설정 업데이트"""
    current = load_settings()
    current["coupang"] = settings.model_dump()
    save_settings(current)
    
    # 환경 변수 업데이트
    os.environ["COUPANG_VENDOR_ID"] = settings.vendor_id
    os.environ["COUPANG_ACCESS_KEY"] = settings.access_key
    os.environ["COUPANG_SECRET_KEY"] = settings.secret_key
    
    # 클라이언트 재초기화
    from ..main import server
    from ..channels.coupang import CoupangWingClient
    
    if server.coupang_client:
        await server.coupang_client.close()
    
    server.coupang_client = CoupangWingClient(
        settings.vendor_id,
        settings.access_key,
        settings.secret_key
    )
    
    return {
        "success": True,
        "message": "쿠팡 API 설정이 저장되었습니다"
    }


@router.post("/telegram")
async def update_telegram_settings(settings: TelegramSettings):
    """텔레그램 알림 설정 업데이트"""
    current = load_settings()
    current["telegram"] = settings.model_dump()
    save_settings(current)
    
    # 환경 변수 업데이트
    os.environ["TELEGRAM_BOT_TOKEN"] = settings.bot_token
    os.environ["TELEGRAM_CHAT_ID"] = settings.chat_id
    
    # 알림 재초기화
    from ..main import server
    from ..notifications import TelegramNotifier
    
    if server.notifier and server.notifier.telegram:
        await server.notifier.telegram.close()
    
    server.notifier.telegram = TelegramNotifier(settings.bot_token, settings.chat_id)
    
    # 테스트 메시지 발송
    result = await server.notifier.telegram.send("🎉 텔레그램 알림이 연결되었습니다!")
    
    return {
        "success": True,
        "connected": result.success,
        "message": "텔레그램 설정이 저장되었습니다" + (" (테스트 성공)" if result.success else f" (테스트 실패: {result.error})")
    }


@router.post("/schedule")
async def update_schedule_settings(settings: ScheduleSettings):
    """스케줄 설정 업데이트"""
    current = load_settings()
    current["schedule"] = settings.model_dump()
    save_settings(current)
    
    # 환경 변수 업데이트
    os.environ["SCHEDULE_FIRST_BATCH"] = settings.first_batch
    os.environ["SCHEDULE_SECOND_BATCH"] = settings.second_batch
    os.environ["TRACKING_INTERVAL_MINUTES"] = str(settings.tracking_interval)
    
    # 스케줄러 재설정
    from ..main import server
    from apscheduler.triggers.cron import CronTrigger
    
    # 기존 작업 제거
    for job_id in ["batch_1", "batch_2"]:
        try:
            server.scheduler.remove_job(job_id)
        except:
            pass
    
    # 새 작업 추가
    first_hour, first_minute = settings.first_batch.split(":")
    server.scheduler.add_job(
        server._run_batch_processing,
        CronTrigger(hour=int(first_hour), minute=int(first_minute)),
        args=[1],
        id="batch_1",
        name="1차 송장 처리",
        replace_existing=True
    )
    
    second_hour, second_minute = settings.second_batch.split(":")
    server.scheduler.add_job(
        server._run_batch_processing,
        CronTrigger(hour=int(second_hour), minute=int(second_minute)),
        args=[2],
        id="batch_2",
        name="2차 송장 처리",
        replace_existing=True
    )
    
    return {
        "success": True,
        "message": f"스케줄이 설정되었습니다 (1차: {settings.first_batch}, 2차: {settings.second_batch})"
    }


@router.post("/stock")
async def update_stock_settings(settings: StockSettings):
    """재고 설정 업데이트"""
    current = load_settings()
    current["stock"] = settings.model_dump()
    save_settings(current)
    
    os.environ["STOCK_ALERT_THRESHOLD"] = str(settings.alert_threshold)
    
    return {
        "success": True,
        "message": f"재고 알림 임계값이 {settings.alert_threshold}개로 설정되었습니다"
    }


@router.post("/test-notification")
async def test_notification(message: str = "🔔 테스트 알림입니다!"):
    """테스트 알림 발송"""
    from ..main import server
    
    if not server.notifier:
        raise HTTPException(status_code=400, detail="알림이 설정되지 않았습니다")
    
    results = await server.notifier._send_all(message)
    
    return {
        "success": any(r.success for r in results),
        "results": [
            {"channel": r.channel, "success": r.success, "error": r.error}
            for r in results
        ]
    }


@router.get("/scheduler/jobs")
async def get_scheduler_jobs():
    """스케줄러 작업 목록"""
    from ..main import server
    
    jobs = []
    for job in server.scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {"jobs": jobs}


@router.post("/export")
async def export_settings():
    """설정 내보내기 (민감 정보 제외)"""
    from ..config import get_settings
    settings = get_settings()

    return {
        "schedule": {
            "first_batch": settings.schedule_first_batch,
            "second_batch": settings.schedule_second_batch,
            "tracking_interval": settings.tracking_interval_minutes
        },
        "stock": {
            "alert_threshold": settings.stock_alert_threshold
        }
    }


# ============================================
# 발송인 설정
# ============================================

@router.post("/sender")
async def update_sender_settings(settings: SenderSettings):
    """발송인 정보 업데이트"""
    current = load_settings()
    current["sender"] = settings.model_dump()
    save_settings(current)

    # 환경 변수 업데이트
    os.environ["SENDER_NAME"] = settings.name
    os.environ["SENDER_PHONE"] = settings.phone
    os.environ["SENDER_ZIPCODE"] = settings.zipcode
    os.environ["SENDER_ADDRESS"] = settings.address

    # ShippingManager 재설정
    from ..main import server
    if server.shipping_manager:
        from ..shipping.carriers import SenderInfo
        server.shipping_manager.sender_info = SenderInfo(
            name=settings.name,
            phone=settings.phone,
            zipcode=settings.zipcode,
            address=settings.address
        )

    return {
        "success": True,
        "message": f"발송인 정보가 저장되었습니다 ({settings.name})"
    }


# ============================================
# 택배사 설정
# ============================================

@router.get("/carriers")
async def get_carriers():
    """택배사 목록 및 설정 상태 조회"""
    from ..main import server

    if server.shipping_manager:
        carriers = server.shipping_manager.get_available_carriers()
    else:
        from ..config import get_settings
        settings = get_settings()
        carriers = [
            {"code": "cj", "name": "CJ대한통운", "configured": settings.cj_configured, "is_default": settings.default_carrier == "cj"},
            {"code": "hanjin", "name": "한진택배", "configured": settings.hanjin_configured, "is_default": settings.default_carrier == "hanjin"},
            {"code": "lotte", "name": "롯데택배", "configured": settings.lotte_configured, "is_default": settings.default_carrier == "lotte"},
            {"code": "logen", "name": "로젠택배", "configured": settings.logen_configured, "is_default": settings.default_carrier == "logen"},
            {"code": "epost", "name": "우체국택배", "configured": settings.epost_configured, "is_default": settings.default_carrier == "epost"},
        ]

    return {"carriers": carriers}


@router.post("/carriers/default")
async def set_default_carrier(settings: DefaultCarrierSettings):
    """기본 택배사 설정"""
    valid_carriers = ["cj", "hanjin", "lotte", "logen", "epost"]
    if settings.carrier not in valid_carriers:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 택배사: {settings.carrier}")

    current = load_settings()
    current["default_carrier"] = settings.carrier
    save_settings(current)

    os.environ["DEFAULT_CARRIER"] = settings.carrier

    carrier_names = {
        "cj": "CJ대한통운",
        "hanjin": "한진택배",
        "lotte": "롯데택배",
        "logen": "로젠택배",
        "epost": "우체국택배"
    }

    return {
        "success": True,
        "message": f"기본 택배사가 {carrier_names[settings.carrier]}(으)로 설정되었습니다"
    }


@router.post("/carriers/cj")
async def update_cj_settings(settings: CJCarrierSettings):
    """CJ대한통운 설정 업데이트"""
    current = load_settings()
    current["cj"] = settings.model_dump()
    save_settings(current)

    # 환경 변수 업데이트
    os.environ["CJ_CUSTOMER_ID"] = settings.customer_id
    os.environ["CJ_API_KEY"] = settings.api_key
    if settings.contract_code:
        os.environ["CJ_CONTRACT_CODE"] = settings.contract_code

    # ShippingManager의 CJ 클라이언트 재초기화
    from ..main import server
    if server.shipping_manager:
        from ..shipping.carriers import CarrierType
        from ..shipping.carriers.cj import CJLogisticsClient

        # 기존 클라이언트 정리
        old_carrier = server.shipping_manager.get_carrier(CarrierType.CJ)
        if old_carrier:
            await old_carrier.close()

        # 새 클라이언트 설정
        new_client = CJLogisticsClient(
            customer_id=settings.customer_id,
            api_key=settings.api_key,
            contract_code=settings.contract_code,
            test_mode=False
        )
        server.shipping_manager.set_carrier(CarrierType.CJ, new_client)

        # 연결 테스트
        connected = await new_client.authenticate()

        return {
            "success": True,
            "connected": connected,
            "message": "CJ대한통운 설정이 저장되었습니다" + (" (연결 성공)" if connected else " (연결 실패 - 테스트 모드로 동작)")
        }

    return {
        "success": True,
        "message": "CJ대한통운 설정이 저장되었습니다"
    }


@router.post("/carriers/hanjin")
async def update_hanjin_settings(settings: HanjinCarrierSettings):
    """한진택배 설정 업데이트"""
    current = load_settings()
    current["hanjin"] = settings.model_dump()
    save_settings(current)

    os.environ["HANJIN_CUSTOMER_ID"] = settings.customer_id
    os.environ["HANJIN_API_KEY"] = settings.api_key

    return {
        "success": True,
        "message": "한진택배 설정이 저장되었습니다 (추후 지원 예정)"
    }


@router.post("/carriers/lotte")
async def update_lotte_settings(settings: LotteCarrierSettings):
    """롯데택배 설정 업데이트"""
    current = load_settings()
    current["lotte"] = settings.model_dump()
    save_settings(current)

    os.environ["LOTTE_CUSTOMER_ID"] = settings.customer_id
    os.environ["LOTTE_API_KEY"] = settings.api_key

    return {
        "success": True,
        "message": "롯데택배 설정이 저장되었습니다 (추후 지원 예정)"
    }


@router.post("/carriers/logen")
async def update_logen_settings(settings: LogenCarrierSettings):
    """로젠택배 설정 업데이트"""
    current = load_settings()
    current["logen"] = settings.model_dump()
    save_settings(current)

    os.environ["LOGEN_CUSTOMER_ID"] = settings.customer_id
    os.environ["LOGEN_API_KEY"] = settings.api_key

    return {
        "success": True,
        "message": "로젠택배 설정이 저장되었습니다 (추후 지원 예정)"
    }


@router.post("/carriers/epost")
async def update_epost_settings(settings: EpostCarrierSettings):
    """우체국택배 설정 업데이트"""
    current = load_settings()
    current["epost"] = settings.model_dump()
    save_settings(current)

    os.environ["EPOST_CUSTOMER_ID"] = settings.customer_id
    os.environ["EPOST_API_KEY"] = settings.api_key

    return {
        "success": True,
        "message": "우체국택배 설정이 저장되었습니다 (추후 지원 예정)"
    }
