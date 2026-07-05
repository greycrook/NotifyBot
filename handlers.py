import datetime
from aiogram import Router, types
from aiogram.filters import Command
import aiosqlite

from config import ADMIN_IDS, DB_NAME
from database import rebuild_schedule, add_user_to_queue, get_all_users, get_next_weeks_schedule  # Обнови импорт


router = Router()


# Функция-фильтр для проверки прав администратора
def is_admin_user(message: types.Message) -> bool:
    return message.from_user.id in ADMIN_IDS


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для управления дежурствами.\n"
        "Я автоматически напоминаю о дежурных в 10:00 и 17:00.\n"
        "Доступные команды для админов:\n"
        "/add @username — Добавить человека в очередь\n"
        "/remove @username — Удалить человека из очереди\n"
        "/skipday — Объявить сегодняшний день выходным (сдвиг очереди)\n"
        "/skipduty — Снять текущего дежурного (заболел/отпуск)"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Выводит список всех доступных команд бота"""

    text = (
        "📖 <b>Руководство по командам бота дежурств</b>\n\n"

        "ℹ️ <b>Для всех сотрудников:</b>\n"
        "• /list — Посмотреть текущий порядок круговой очереди.\n"
        "• /schedule — Посмотреть график дежурств на ближайшие 2 недели.\n"
        "• /today — Посмотреть дежурного на сегодня.\n\n"
        
        "🛠 <b>Для администраторов (управление графиком):</b>\n"
        "• /add @user1 @user2 — Добавить одного или нескольких сотрудников в конец очереди.\n"
        "• /remover @user1 @user2 — Удалить сотрудников из базы и перестроить график.\n"
        "• /editduty @username ГГГГ-ММ-ДД — Вручную назначить сотрудника на конкретную дату.\n"
        "• /skipduty — Снять текущего дежурного с сегодняшней смены (сдвиг графика на 1 день вперед).\n"
        "• /skipday — Объявить сегодняшний день выходным (все смены сдвигаются на завтра).\n"
    )

    await message.answer(text, parse_mode="HTML")

@router.message(Command("add"))
async def cmd_add_worker(message: types.Message):
    if not is_admin_user(message):
        return await message.answer("❌ У вас нет прав для этой команды.")

    # Разбиваем сообщение по пробелам
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("✍️ Использование: `/add @user1 @user2 @user3`", parse_mode="HTML")

    # Выделяем только те аргументы, которые начинаются с @ (никнеймы)
    workers_to_add = [username for username in args[1:] if username.startswith("@")]

    if not workers_to_add:
        return await message.answer("❌ Не найдено ни одного корректного никнейма (никнейм должен начинаться с @).")

    added_users = []
    async with aiosqlite.connect(DB_NAME) as db:
        for username in workers_to_add:
            # Находим максимальный текущий порядковый номер на каждом шаге цикла
            async with db.execute("SELECT MAX(queue_order) FROM users") as cursor:
                row = await cursor.fetchone()
                max_order = row[0] if row[0] is not None else 0

            new_order = max_order + 1
            fake_id = hash(username)  # Генерируем уникальный хэш-ID на основе никнейма

            # Записываем в базу
            await db.execute(
                "INSERT OR REPLACE INTO users (telegram_id, username, queue_order, is_admin) VALUES (?, ?, ?, 0)",
                (fake_id, username, new_order)
            )
            added_users.append(username)

        await db.commit()

    # Перестраиваем календарь один раз после добавления всех сотрудников
    await rebuild_schedule()

    # Формируем красивый ответ
    list_str = ", ".join(added_users)
    await message.answer(f"✅ Успешно добавлены в очередь: {list_str}")


@router.message(Command("remove"))
async def cmd_remove_worker(message: types.Message):
    if not is_admin_user(message):
        return await message.answer("❌ У вас нет прав.")

    args = message.text.split()
    if len(args) < 2:
        return await message.answer("✍️ Использование: `/remove @user1 @user2`", parse_mode="HTML")

    # Собираем все никнеймы с @
    workers_to_remove = [username for username in args[1:] if username.startswith("@")]

    if not workers_to_remove:
        return await message.answer("❌ Не найдено ни одного корректного никнейма с @.")

    removed_users = []
    async with aiosqlite.connect(DB_NAME) as db:
        for username in workers_to_remove:
            # Проверяем, есть ли он вообще в базе
            async with db.execute("SELECT 1 FROM users WHERE username = ?", (username,)) as cursor:
                if await cursor.fetchone():
                    await db.execute("DELETE FROM users WHERE username = ?", (username,))
                    removed_users.append(username)
        await db.commit()

    if not removed_users:
        return await message.answer("🤷‍♂️ Ни один из указанных сотрудников не был найден в базе данных.")

    # Перестраиваем расписание без удаленных людей
    await rebuild_schedule()

    list_str = ", ".join(removed_users)
    await message.answer(f"❌ Успешно удалены из базы: {list_str}. График автоматически скорректирован!")


@router.message(Command("skipday"))
async def cmd_skipday(message: types.Message):
    """Праздник: сдвигаем всю очередь дежурных начиная с сегодня на один рабочий день вперед"""
    if not is_admin_user(message):
        return await message.answer("❌ У вас нет прав.")

    today_str = datetime.date.today().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        # Получаем все дежурства, начиная с сегодняшнего дня, отсортированные по дате
        query = "SELECT date, telegram_id FROM duty_schedule WHERE date >= ? ORDER BY date ASC"
        async with db.execute(query, (today_str,)) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await message.answer("📅 Расписание пустое, нечего сдвигать.")

        # Сдвигаем telegram_id: сегодняшняя дата освобождается (или удаляется),
        # а ID дежурных перемещаются на следующую по списку дату.
        for i in range(len(rows) - 1, 0, -1):
            current_date = rows[i][0]
            prev_user_id = rows[i - 1][1]
            await db.execute("UPDATE duty_schedule SET telegram_id = ? WHERE date = ?", (prev_user_id, current_date))

        # Сегодняшний день удаляем из графика дежурств (считаем его праздником)
        await db.execute("DELETE FROM duty_schedule WHERE date = ?", (today_str,))
        await db.commit()

    await message.answer(
        "Сегодня объявлен выходной! Очередь дежурств сдвинута.")


@router.message(Command("skipduty"))
async def cmd_skipduty(message: types.Message):
    """Болезнь: сдвигаем график дежурств начиная с сегодня на 1 день вперед,
    а текущего заболевшего переносим на самый конец сгенерированного расписания"""
    if not is_admin_user(message):
        return await message.answer("❌ У вас нет прав.")

    today_str = datetime.date.today().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Получаем весь график начиная с сегодня
        query = "SELECT date, telegram_id FROM duty_schedule WHERE date >= ? ORDER BY date ASC"
        async with db.execute(query, (today_str,)) as cursor:
            rows = await cursor.fetchall()

        if len(rows) < 2:
            return await message.answer("📅 Расписание слишком короткое, невозможно выполнить сдвиг.")

        # Запоминаем, кто должен был дежурить сегодня (заболевший)
        sick_user_id = rows[0][1]

        # 2. Сдвигаем всех дежурных на один день назад (следующий заступает сегодня)
        # Пример: сегодняшний день получает ID того, кто должен был дежурить завтра, и т.д.
        for i in range(len(rows) - 1):
            current_date = rows[i][0]
            next_user_id = rows[i + 1][1]
            await db.execute("UPDATE duty_schedule SET telegram_id = ? WHERE date = ?", (next_user_id, current_date))

        # 3. Заболевшего отправляем на самую последнюю дату нашего 90-дневного графика
        last_date = rows[-1][0]
        await db.execute("UPDATE duty_schedule SET telegram_id = ? WHERE date = ?", (sick_user_id, last_date))
        await db.commit()

    await message.answer("Дежурный снят со смены.")

@router.message(Command("today"))
async def cmd_who_today(message: types.Message):
    from database import get_current_duty
    import datetime
    today = datetime.date.today().strftime("%Y-%m-%d")
    duty = await get_current_duty(today)
    if duty:
        await message.answer(f"Сегодня дежурит: {duty[1]}")
    else:
        await message.answer("На сегодня дежурный не назначен.")


@router.message(Command("list"))
async def cmd_list(message: types.Message):
    """Выводит список всех людей в круговой очереди"""
    users = await get_all_users()
    if not users:
        return await message.answer("В очереди пока никого нет.")

    # Используем тег <b> вместо **
    text = "🔄 <b>Порядок очереди:</b>\n"
    for i, (username, order) in enumerate(users, 1):
        text += f"{i}. {username}\n"

    # Меняем parse_mode на HTML
    await message.answer(text, parse_mode="HTML")


@router.message(Command("schedule"))
async def cmd_schedule(message: types.Message):
    """Выводит график дежурств на ближайшие 14 дней"""
    schedule = await get_next_weeks_schedule(14)
    if not schedule:
        return await message.answer("График пока пуст.")

    # Используем тег <b> вместо **
    text = "📅 <b>График на ближайшие 2 недели:</b>\n"
    for date_str, username in schedule:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        date_formatted = dt.strftime("%d.%m (%a)")
        text += f"▫️ {date_formatted}: {username}\n"

    # Меняем parse_mode на HTML
    await message.answer(text, parse_mode="HTML")


from database import dump_db_to_console
from scheduler import get_time_until_next_notification


@router.message(Command("debug"))
async def cmd_debug(message: types.Message):
    if not is_admin_user(message):
        return

    # Вызываем дамп в консоль сервера
    dump_db_to_console()

    # А в чат бот ответит, сколько осталось до триггера
    time_info = get_time_until_next_notification()
    await message.answer(f"📊 Дамп базы выведен в консоль сервера.\n{time_info}")


@router.message(Command("editduty"))
async def cmd_edit_duty(message: types.Message):
    """Ручное назначение сотрудника на конкретную дату"""
    if not is_admin_user(message):
        return await message.answer("❌ У вас нет прав.")

    # Ожидаем формат: /editduty @worker 2026-06-15
    args = message.text.split()
    if len(args) < 3 or not args[1].startswith("@"):
        return await message.answer("✍️ Использование: `/editduty @username YYYY-MM-DD`", parse_mode="Markdown")

    username = args[1]
    target_date = args[2]

    # Проверяем валидность формата даты
    try:
        datetime.datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return await message.answer("❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД (например, 2026-06-15).")

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Находим telegram_id пользователя по его никнейму
        async with db.execute("SELECT telegram_id FROM users WHERE username = ?", (username,)) as cursor:
            user_row = await cursor.fetchone()

        if not user_row:
            return await message.answer(
                f"❌ Пользователь {username} не найден в базе. Сначала добавьте его через /add_worker.")

        user_id = user_row[0]

        # 2. Записываем его дежурным на эту дату (если дата есть в календаре рабочих дней)
        async with db.execute("SELECT 1 FROM duty_schedule WHERE date = ?", (target_date,)) as check_cursor:
            if not await check_cursor.fetchone():
                # Если даты нет в duty_schedule, создаем запись
                await db.execute("INSERT INTO duty_schedule (date, telegram_id) VALUES (?, ?)", (target_date, user_id))
            else:
                # Если есть — обновляем дежурного
                await db.execute("UPDATE duty_schedule SET telegram_id = ? WHERE date = ?", (user_id, target_date))

        await db.commit()

    await message.answer(f"🎯 Смена скорректирована! На дату <b>{target_date}</b> назначен {username}.",
                         parse_mode="HTML")

