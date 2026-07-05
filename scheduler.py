import datetime
import logging
import aiosqlite
from aiogram import Bot


import sqlite3
from config import DB_NAME, CHAT_ID  # Импортируем CHAT_ID из конфига
from database import get_current_duty

logger = logging.getLogger(__name__)


async def check_and_send_notification(bot: Bot):
    """
    Проверяет реальное время и отправляет уведомления в жестко заданный CHAT_ID.
    Запускается каждые 10 минут.
    """
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    # Строгие интервалы для боевого режима
    if 10 <= current_hour < 17:
        time_slot = "10:00"
    elif 17 <= current_hour <= 23:
        time_slot = "17:00"
    else:
        return  # Ночью и рано утром бот отдыхает

    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, не отправляли ли уже сегодня этот слот
        query = "SELECT status FROM notification_logs WHERE date = ? AND time_slot = ?"
        async with db.execute(query, (today_str, time_slot)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == "SUCCESS":
                return

                # Ищем, кто дежурит сегодня по календарю
        duty_user = await get_current_duty(today_str)
        if not duty_user:
            return  # Выходной или расписание не заполнено

        telegram_id, username = duty_user

        try:
            if time_slot == "10:00":
                message_text = f"🔔 <b>Напоминание! Сегодня дежурит {username}. Удачного рабочего дня! </b>"
            else:
                message_text = (
                    f"🔔 <b>Напоминание! {username} Вам необходимо: </b>\n"
                    f"<blockquote>"
                    f"1) Организовать порядок в 130 и на складе Пахра-1\n"
                    f"2) Организовать порядок в залах (убедиться, что закрыты стойки, мониторы и тележка на своих местах, в телеге есть инструмент и стяжки)"
                    f"</blockquote>"
                )

            await bot.send_message(chat_id=CHAT_ID, text=message_text, parse_mode="HTML")

            await db.execute(
                "INSERT OR REPLACE INTO notification_logs (date, time_slot, status) VALUES (?, ?, ?)",
                (today_str, time_slot, "SUCCESS")
            )
            await db.commit()
            logger.info(f"Уведомление для {username} успешно отправлено.")

        except Exception as e:
            # Логируем, пишем FAILED и выходим БЕЗ падения основного процесса бота
            logger.error(f"💥 Критическая ошибка отправки в чат, но бот продолжает работу: {e}")
            await db.execute(
                "INSERT OR REPLACE INTO notification_logs (date, time_slot, status) VALUES (?, ?, ?)",
                (today_str, time_slot, "FAILED")
            )
            await db.commit()


def setup_scheduler(bot: Bot):
    """Инициализация планировщика на интервал в 10 минут"""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_notification,
        "interval",
        minutes=1,
        args=[bot]
    )
    scheduler.start()


def get_time_until_next_notification():
    """Возвращает строку с описанием, сколько осталось до следующего уведомления, учитывая долги"""
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    today_10 = now.replace(hour=10, minute=0, second=0, microsecond=0)
    today_17 = now.replace(hour=17, minute=0, second=0, microsecond=0)

    # СВЕЖАК: Проверяем, есть ли вообще дежурный на сегодня. Если нет — сегодня выходной!
    has_duty_today = False
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM duty_schedule WHERE date = ?", (today_str,))
            if cursor.fetchone():
                has_duty_today = True
    except Exception:
        pass

    # Если сегодня выходной, бот просто ждет наступления следующего рабочего дня
    if not has_duty_today:
        return "⏳ Сегодня выходной день. Бот активируется в ближайший рабочий день в 10:00."

    # Быстрая проверка статусов за сегодня (выполняется только в рабочие дни)
    status_10, status_17 = None, None
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT time_slot, status FROM notification_logs WHERE date = ?", (today_str,))
            for slot, stat in cursor.fetchall():
                if slot == "10:00": status_10 = stat
                if slot == "17:00": status_17 = stat
    except Exception:
        pass

    # Считаем остаток для рабочих дней
    if now < today_10:
        if status_10 != "SUCCESS":
            delta = today_10 - now
            return f"⏳ До утреннего уведомления [10:00] осталось: {int(delta.total_seconds() // 3600)} ч. {int((delta.total_seconds() % 3600) // 60)} мин."

    if now < today_17:
        if status_10 != "SUCCESS":
            return "🚨 Долг! Утреннее уведомление [10:00] не отправлено. Бот будет пытаться отправить его каждые 10 минут!"
        delta = today_17 - now
        return f"⏳ До вечернего уведомления [17:00] осталось: {int(delta.total_seconds() // 3600)} ч. {int((delta.total_seconds() % 3600) // 60)} мин."

    if status_17 != "SUCCESS":
        return "🚨 Долг! Вечернее уведомление [17:00] поймало ошибку. Бот пытается отправить его прямо сейчас в текущих циклах!"

    tomorrow_10 = today_10 + datetime.timedelta(days=1)
    delta = tomorrow_10 - now
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"⏳ Все уведомления на сегодня отправлены. До следующего [10:00 завтра] осталось: {hours} ч. {minutes} мин."
