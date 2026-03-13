"""백그라운드 스케줄러 - 사용자별 자동 주문 처리"""
import json
import structlog
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
from auth import UserCredentials, set_credentials

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


def _build_creds(creds_dict: dict) -> UserCredentials:
    return UserCredentials(
        coupang_vendor_id=creds_dict.get("coupang_vendor_id"),
        coupang_access_key=creds_dict.get("coupang_access_key"),
        coupang_secret_key=creds_dict.get("coupang_secret_key"),
        cj_customer_id=creds_dict.get("cj_customer_id"),
        cj_biz_reg_num=creds_dict.get("cj_biz_reg_num"),
        sender_name=creds_dict.get("sender_name"),
        sender_phone=creds_dict.get("sender_phone"),
        sender_zipcode=creds_dict.get("sender_zipcode"),
        sender_address=creds_dict.get("sender_address"),
    )


async def run_cron_for_user(user_id: int):
    """단일 사용자의 자동 주문 처리 실행"""
    from tools.shipping import process_orders

    creds_dict = db.get_user_credentials(user_id)
    if not creds_dict:
        return

    try:
        set_credentials(_build_creds(creds_dict))
        result = await process_orders(days=7, dry_run=False)

        total = result.get("total", 0)
        processed = result.get("processed", 0)
        failed = result.get("failed", 0)
        summary = f"성공 {processed}건, 실패 {failed}건" if total > 0 else "신규 주문 없음"

        db.create_processing_log(
            user_id=user_id,
            trigger_type="auto",
            total=total,
            processed=processed,
            failed=failed,
            result_json=json.dumps(result, ensure_ascii=False, default=str),
        )
        db.update_automation_last_run(user_id, summary)
        logger.info("cron.user_processed", user_id=user_id, total=total, processed=processed, failed=failed)

    except Exception as e:
        logger.exception("cron.user_error", user_id=user_id, error=str(e))
        db.update_automation_last_run(user_id, f"오류: {str(e)[:100]}")
    finally:
        set_credentials(None)


async def cron_tick():
    """매 분 실행: 자동화 활성 사용자 확인 후 처리"""
    automations = db.get_all_enabled_automations()
    now = datetime.now(timezone.utc)

    for auto in automations:
        user_id = auto["user_id"]
        interval = auto.get("interval_minutes", 60)
        last_run = auto.get("last_run_at")

        if last_run:
            try:
                if isinstance(last_run, str):
                    last_run_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                else:
                    last_run_dt = last_run
                if last_run_dt.tzinfo is None:
                    last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
                elapsed = (now - last_run_dt).total_seconds() / 60
                if elapsed < interval:
                    continue
            except Exception as e:
                logger.warning("cron.bad_last_run", user_id=user_id, error=str(e))
                continue

        await run_cron_for_user(user_id)


def start_scheduler():
    """스케줄러 시작"""
    scheduler.add_job(cron_tick, "interval", minutes=1, id="cron_tick", replace_existing=True)
    scheduler.start()
    logger.info("scheduler.started")


def stop_scheduler():
    """스케줄러 종료"""
    scheduler.shutdown(wait=False)
    logger.info("scheduler.stopped")
