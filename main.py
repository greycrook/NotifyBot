import asyncio
import logging
from aiogram import Bot, Dispatcher

from config import TOKEN
from database import init_db
from handlers import router
from scheduler import setup_scheduler

from database import init_db, dump_db_to_console  # Обнови импорт
from scheduler import setup_scheduler, get_time_until_next_notification  # Обнови импорт

# Настраиваем логирование в консоль
logging.basicConfig(level=logging.INFO)


async def main():
    # Инициализируем бота и диспетчер
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Подключаем роутер с командами
    dp.include_router(router)

    # Шаг 1. Инициализируем таблицы в SQLite
    await init_db()

    # Шаг 2. Запускаем планировщик уведомлений
    # ВАЖНО: замени -1001234567890 на РЕАЛЬНЫЙ ID твоей беседы (чата), куда бот должен слать уведомления
    CHAT_ID = -5196307154
    setup_scheduler(bot)

    # Шаг 3. Запускаем long polling (слушаем команды)
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)


async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await init_db()
    setup_scheduler(bot)

    # --- БЛОК ОТЛАДКИ ПРИ СТАРТЕ ---
    print("Бот успешно запущен и готов к работе!")

    # Выводим состояние базы в консоль
    dump_db_to_console()

    # Выводим таймер до следующего алерта
    print(get_time_until_next_notification())
    print("-" * 70)
    # -------------------------------

    await dp.start_polling(bot)



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")