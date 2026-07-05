import datetime
import aiosqlite
from config import DB_NAME
import sqlite3


async def init_db():
    """Инициализация базы данных и создание таблиц"""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица пользователей (очереди)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                queue_order INTEGER NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
        """)

        # 2. Таблица расписания дежурств
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duty_schedule (
                date TEXT PRIMARY KEY,
                telegram_id INTEGER,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        """)

        # 3. Таблица логов уведомлений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                date TEXT,
                time_slot TEXT,
                status TEXT,
                PRIMARY KEY (date, time_slot)
            )
        """)
        await db.commit()


async def add_user_to_queue(telegram_id: int, username: str, is_admin: int = 0):
    """Добавление нового человека в конец круговой очереди"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Находим максимальный текущий порядковый номер
        async with db.execute("SELECT MAX(queue_order) FROM users") as cursor:
            row = await cursor.fetchone()
            max_order = row[0] if row[0] is not None else 0

        new_order = max_order + 1

        # Добавляем пользователя
        await db.execute(
            "INSERT OR REPLACE INTO users (telegram_id, username, queue_order, is_admin) VALUES (?, ?, ?, ?)",
            (telegram_id, username, new_order, is_admin)
        )
        await db.commit()

    # После добавления нужно будет пересчитать расписание (напишем в следующем шаге)
    await rebuild_schedule()


async def get_current_duty(date_str: str):
    """Получить дежурного на определенную дату (формат YYYY-MM-DD)"""
    async with aiosqlite.connect(DB_NAME) as db:
        query = """
            SELECT u.telegram_id, u.username 
            FROM duty_schedule ds
            JOIN users u ON ds.telegram_id = u.telegram_id
            WHERE ds.date = ?
        """
        async with db.execute(query, (date_str,)) as cursor:
            return await cursor.fetchone()  # Вернет (telegram_id, username) или None


async def rebuild_schedule():
    """Полный пересчет графика на 90 рабочих дней вперед на основе queue_order"""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Получаем список всех сотрудников по порядку очереди
        async with db.execute("SELECT telegram_id FROM users ORDER BY queue_order ASC") as cursor:
            users = await cursor.fetchall()

        if not users:
            return  # Некого назначать

        users_list = [u[0] for u in users]  # Чистый список ID

        # 2. Генерируем рабочие дни на 90 дней вперед (начиная с сегодня)
        current_date = datetime.date.today()
        working_days = []

        while len(working_days) < 90:
            # Пренебрегаем СБ и ВС (0 = Понедельник, 5 = Суббота, 6 = Воскресенье)
            if current_date.weekday() < 5:
                working_days.append(current_date.strftime("%Y-%m-%d"))
            current_date += datetime.timedelta(days=1)

        # 3. Находим, кто дежурит СЕГОДНЯ (чтобы не сбить текущего дежурного при пересчете, если возможно)
        # Для простоты: если расписание уже было, мы можем продолжить круг.
        # Но для первой и честной итерации — просто распределяем по кругу заново.

        user_index = 0
        schedule_data = []

        for date_str in working_days:
            user_id = users_list[user_index % len(users_list)]
            schedule_data.append((date_str, user_id))
            user_index += 1

        # 4. Очищаем старое будущее расписание и записываем новое
        # Удаляем всё, что начиная с сегодняшнего дня
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        await db.execute("DELETE FROM duty_schedule WHERE date >= ?", (today_str,))

        # Массовая вставка
        await db.executemany(
            "INSERT OR REPLACE INTO duty_schedule (date, telegram_id) VALUES (?, ?)",
            schedule_data
        )
        await db.commit()

async def get_all_users():
    """Получить список всех пользователей в порядке очереди"""
    async with aiosqlite.connect(DB_NAME) as db:
        query = "SELECT username, queue_order FROM users ORDER BY queue_order ASC"
        async with db.execute(query) as cursor:
            return await cursor.fetchall()

async def get_next_weeks_schedule(days: int = 14):
    """Получить расписание на ближайшие N дней"""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db:
        query = """
            SELECT ds.date, u.username 
            FROM duty_schedule ds
            JOIN users u ON ds.telegram_id = u.telegram_id
            WHERE ds.date >= ?
            ORDER BY ds.date ASC
            LIMIT ?
        """
        async with db.execute(query, (today_str, days)) as cursor:
            return await cursor.fetchall()



def dump_db_to_console():
    """Синхронный дамп базы данных в консоль для удобной отладки"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n" + "=" * 70)
    print("🧠 ДАМП БАЗЫ ДАННЫХ ДЛЯ ОТЛАДКИ")
    print("=" * 70)

    # 1. Выводим список пользователей и их порядок
    print("\n👥 ОЧЕРЕДЬ СОТРУДНИКОВ (Таблица 'users'):")
    print(f"{'ID':<15} | {'Username':<20} | {'Порядок':<8} | {'Админ':<6}")
    print("-" * 55)
    cursor.execute("SELECT telegram_id, username, queue_order, is_admin FROM users ORDER BY queue_order ASC")
    for row in cursor.fetchall():
        print(f"{row[0]:<15} | {row[1]:<20} | {row[2]:<8} | {row[3]:<6}")

    # 2. Выводим график на ближайшие 7 дней и статусы уведомлений
    print("\n📅 ГРАФИК И СТАТУСЫ УВЕДОМЛЕНИЙ НА 7 ДНЕЙ:")
    print(f"{'Дата':<12} | {'Дежурный':<20} | {'Слот 10:00':<12} | {'Слот 17:00':<12}")
    print("-" * 65)

    # Берем график на неделю вперед
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT ds.date, u.username 
        FROM duty_schedule ds
        JOIN users u ON ds.telegram_id = u.telegram_id
        WHERE ds.date >= ?
        ORDER BY ds.date ASC
        LIMIT 7
    """, (today_str,))

    schedule_rows = cursor.fetchall()

    for date_str, username in schedule_rows:
        # Проверяем статус для 10:00
        cursor.execute("SELECT status FROM notification_logs WHERE date = ? AND time_slot = '10:00'", (date_str,))
        log_10 = cursor.fetchone()
        status_10 = log_10[0] if log_10 else "НЕ ОТПРАВЛЕНО"

        # Проверяем статус для 17:00
        cursor.execute("SELECT status FROM notification_logs WHERE date = ? AND time_slot = '17:00'", (date_str,))
        log_17 = cursor.fetchone()
        status_17 = log_17[0] if log_17 else "НЕ ОТПРАВЛЕНО"

        # Красивые отметки
        icon_10 = "✅ SUCCESS" if status_10 == "SUCCESS" else ("❌ FAILED" if status_10 == "FAILED" else "⏳ Ожидает")
        icon_17 = "✅ SUCCESS" if status_17 == "SUCCESS" else ("❌ FAILED" if status_17 == "FAILED" else "⏳ Ожидает")

        print(f"{date_str:<12} | {username:<20} | {icon_10:<12} | {icon_17:<12}")

    print("=" * 70 + "\n")
    conn.close()