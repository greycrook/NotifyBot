from datetime import date

from bot.database import DutyUser
from bot.duty import format_user_label

WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def weekday_short(d: date) -> str:
    return WEEKDAY_SHORT[d.weekday()]


def format_schedule_line(d: date, user: DutyUser | None, working: bool) -> str:
    day = weekday_short(d)
    date_str = d.strftime("%d.%m")
    if working and user:
        return f"{day} {date_str} — {format_user_label(user)}"
    return f"{day} {date_str} — Выходной"


def format_schedule_message(schedule: list[tuple[date, DutyUser | None, bool]]) -> str:
    lines = [format_schedule_line(d, user, working) for d, user, working in schedule]
    return "Расписание на 14 дней\n\n" + "\n".join(lines)
