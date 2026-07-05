import logging
from collections.abc import Callable
from datetime import date

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import (
    TEST_EVENING_HOUR,
    TEST_EVENING_MINUTE,
    TEST_MODE,
    TEST_MORNING_HOUR,
    TEST_MORNING_MINUTE,
    TIMEZONE,
)
from bot.database import DutyUser, get_chat_id
from bot.duty import advance_after_working_day, get_today_duty
from bot.holidays import is_working_day

logger = logging.getLogger(__name__)


def _format_username_tag(user: DutyUser) -> str:
    return f"@{user.username}"


async def _send_reminder(
    bot: Bot,
    label: str,
    build_text: Callable[[DutyUser], str],
    *,
    advance_queue: bool = False,
) -> None:
    chat_id = get_chat_id()
    if not chat_id:
        logger.warning("%s: пропущено — CHAT_ID не задан (выполните /setchat)", label)
        return

    today = date.today()
    if not TEST_MODE and not is_working_day(today):
        logger.info("%s: пропущено — выходной или праздник (%s)", label, today)
        return

    duty, working = get_today_duty(force_working=TEST_MODE)
    if not working:
        logger.info("%s: пропущено — нерабочий день (%s)", label, today)
        return
    if not duty:
        logger.warning("%s: пропущено — список дежурных пуст", label)
        return

    text = build_text(duty)
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.exception(
            "%s: ошибка отправки в чат %s для @%s", label, chat_id, duty.username
        )
        raise

    logger.info(
        "%s: отправлено в чат %s для @%s", label, chat_id, duty.username
    )
    if advance_queue:
        advance_after_working_day()
        logger.info("%s: очередь дежурных сдвинута", label)


async def _send_morning(bot: Bot) -> None:
    await _send_reminder(
        bot,
        "Утреннее напоминание",
        lambda duty: f"Напоминание. Сегодня дежурит — {_format_username_tag(duty)}",
    )


async def _send_evening(bot: Bot) -> None:
    await _send_reminder(
        bot,
        "Вечернее напоминание",
        lambda duty: (
            f"Напоминание. {_format_username_tag(duty)}, "
            "пожалуйста, отправьте фото уборки."
        ),
        advance_queue=not TEST_MODE,
    )


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    if TEST_MODE:
        morning_h, morning_m = TEST_MORNING_HOUR, TEST_MORNING_MINUTE
        evening_h, evening_m = TEST_EVENING_HOUR, TEST_EVENING_MINUTE
        logger.warning(
            "TEST_MODE: напоминания в %02d:%02d и %02d:%02d (включая выходные)",
            morning_h,
            morning_m,
            evening_h,
            evening_m,
        )
    else:
        morning_h, morning_m = 10, 0
        evening_h, evening_m = 17, 0
        logger.info(
            "Боевой режим: напоминания в %02d:%02d и %02d:%02d (будни РФ)",
            morning_h,
            morning_m,
            evening_h,
            evening_m,
        )
    scheduler.add_job(
        _send_morning,
        CronTrigger(hour=morning_h, minute=morning_m, timezone=TIMEZONE),
        args=[bot],
        id="morning_reminder",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _send_evening,
        CronTrigger(hour=evening_h, minute=evening_m, timezone=TIMEZONE),
        args=[bot],
        id="evening_reminder",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
