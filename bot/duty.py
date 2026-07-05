from datetime import date, timedelta

from bot.database import (
    DutyUser,
    get_duty_index,
    get_evening_advanced_on,
    list_duty_users,
    set_duty_index,
    set_evening_advanced_on,
)
from bot.holidays import is_working_day


def _user_at_index(users: list[DutyUser], index: int) -> DutyUser | None:
    if not users:
        return None
    return users[index % len(users)]


def advance_after_working_day() -> None:
    users = list_duty_users()
    if not users:
        return
    idx = get_duty_index()
    set_duty_index((idx + 1) % len(users))
    set_evening_advanced_on(date.today())


def _duty_index_for_date(on_date: date) -> int:
    """Индекс дежурного на календарный день (с учётом сдвига очереди в 17:00)."""
    users = list_duty_users()
    if not users:
        return 0
    idx = get_duty_index()
    advanced_on = get_evening_advanced_on()
    if advanced_on == on_date and is_working_day(on_date):
        return (idx - 1) % len(users)
    return idx


def get_today_duty(
    on_date: date | None = None, *, force_working: bool = False
) -> tuple[DutyUser | None, bool]:
    d = on_date or date.today()
    working = force_working or is_working_day(d)
    if not working:
        return None, False
    users = list_duty_users()
    return _user_at_index(users, _duty_index_for_date(d)), True


def simulate_schedule(
    start: date | None = None, days: int = 14
) -> list[tuple[date, DutyUser | None, bool]]:
    d = start or date.today()
    users = list_duty_users()
    idx = _duty_index_for_date(d)
    result: list[tuple[date, DutyUser | None, bool]] = []

    for i in range(days):
        current = d + timedelta(days=i)
        working = is_working_day(current)
        if working and users:
            user = _user_at_index(users, idx)
            result.append((current, user, True))
            idx = (idx + 1) % len(users)
        else:
            result.append((current, None, working))

    return result


def format_user_label(user: DutyUser) -> str:
    name = user.display_name or user.username
    return f"{name} (@{user.username})"
