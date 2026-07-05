import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0") or "0")
TIMEZONE = "Europe/Moscow"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "duty_bot.db"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() in ("1", "true", "yes")

TEST_MORNING_HOUR = int(os.getenv("TEST_MORNING_HOUR", "15"))
TEST_MORNING_MINUTE = int(os.getenv("TEST_MORNING_MINUTE", "20"))
TEST_EVENING_HOUR = int(os.getenv("TEST_EVENING_HOUR", "15"))
TEST_EVENING_MINUTE = int(os.getenv("TEST_EVENING_MINUTE", "22"))


def format_schedule_times() -> str:
    if TEST_MODE:
        return (
            f"{TEST_MORNING_HOUR:02d}:{TEST_MORNING_MINUTE:02d} и "
            f"{TEST_EVENING_HOUR:02d}:{TEST_EVENING_MINUTE:02d} (тестовый режим)"
        )
    return "10:00 и 17:00"
