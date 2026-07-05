from datetime import date

NON_WORKING_DATES: set[date] = {
    date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4),
    date(2025, 1, 5), date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8),
    date(2025, 2, 23), date(2025, 3, 8), date(2025, 5, 1), date(2025, 5, 9),
    date(2025, 6, 12), date(2025, 11, 4),
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4),
    date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8),
    date(2026, 2, 23), date(2026, 3, 8), date(2026, 5, 1), date(2026, 5, 9),
    date(2026, 6, 12), date(2026, 11, 4),
    date(2027, 1, 1), date(2027, 1, 2), date(2027, 1, 3), date(2027, 1, 4),
    date(2027, 1, 5), date(2027, 1, 6), date(2027, 1, 7), date(2027, 1, 8),
    date(2027, 2, 23), date(2027, 3, 8), date(2027, 5, 1), date(2027, 5, 9),
    date(2027, 6, 12), date(2027, 11, 4),
}


def is_working_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in NON_WORKING_DATES
