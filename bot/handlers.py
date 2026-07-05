import logging
import re
from datetime import date

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message

from bot.config import format_schedule_times
from bot.database import (
    add_duty_users,
    get_chat_id,
    list_duty_users,
    remove_duty_user,
    remove_duty_users,
    set_chat_id,
)
from bot.duty import format_user_label, get_today_duty, simulate_schedule
from bot.formatting import format_schedule_message
from bot.members import get_member_by_user_id
from bot.permissions import require_group_admin, resolve_group_chat_id

logger = logging.getLogger(__name__)
router = Router()

USERNAME_RE = re.compile(r"@?([a-zA-Z0-9_]{5,32})")
USER_ID_RE = re.compile(r"^\d{5,15}$")


def _build_help_text() -> str:
    schedule_note = format_schedule_times()
    return (
        "<b>Бот для напоминаний</b>\n\n"
        "<b>Автоматически</b> (будни РФ, МСК):\n"
        f"• {schedule_note} — утреннее и вечернее напоминания\n\n"
        "<b>Для всех участников группы:</b>\n"
        "/list — очередь дежурных\n"
        "/today — кто дежурит сегодня\n"
        "/schedule — расписание на 14 дней\n"
        "/help — эта справка\n\n"
        "<b>Для администраторов группы:</b>\n"
        "/setchat — привязать беседу\n"
        "/add @user1 @user2 — добавить нескольких по порядку\n"
        "/add 123456789 — добавить по Telegram ID\n"
        "/remove @user1 @user2 — удалить нескольких\n\n"
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я напоминаю о дежурстве в групповом чате.\n"
        "Список команд: /help"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_build_help_text())


@router.message(Command("setchat"))
async def cmd_setchat(message: Message, bot: Bot) -> None:
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.answer("Эту команду нужно выполнить в групповом чате")
        return
    if not await require_group_admin(message, bot):
        return
    set_chat_id(message.chat.id)
    await message.answer(f"Чат привязан (id: {message.chat.id})")


@router.message(Command("add"))
async def cmd_add(message: Message, bot: Bot) -> None:
    if not await require_group_admin(message, bot):
        return

    chat_id = resolve_group_chat_id(message)
    if not chat_id:
        await message.answer("Сначала выполните /setchat в группе")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Использование:\n"
            "/add @user1 @user2 @user3\n"
            "/add 123456789 — Telegram ID"
        )
        return

    tokens = args[1].split()
    to_add: list[tuple[str, str | None, int | None]] = []
    invalid: list[str] = []

    for token in tokens:
        if USER_ID_RE.match(token):
            member = await get_member_by_user_id(bot, chat_id, int(token))
            if not member:
                invalid.append(f"{token} — не найден в беседе")
                continue
            tg_user = member.user
            if not tg_user.username:
                invalid.append(f"{token} — нет @username")
                continue
            to_add.append((tg_user.username.lower(), tg_user.full_name, tg_user.id))
            continue

        m = USERNAME_RE.search(token)
        if m:
            to_add.append((m.group(1).lower(), None, None))
        else:
            invalid.append(token)

    if not to_add:
        if invalid:
            await message.answer(
                "Не удалось добавить никого:\n" + "\n".join(invalid)
            )
        else:
            await message.answer("Укажите @username или числовой Telegram ID")
        return

    result = add_duty_users(to_add)
    if invalid:
        result += "\n\nНе распознано:\n" + "\n".join(invalid)
    await message.answer(result)


@router.message(Command("remove"))
async def cmd_remove(message: Message, bot: Bot) -> None:
    if not await require_group_admin(message, bot):
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /remove @user1 @user2 @user3")
        return

    to_remove: list[str] = []
    invalid: list[str] = []
    for token in args[1].split():
        m = USERNAME_RE.search(token)
        if m:
            to_remove.append(m.group(1).lower())
        else:
            invalid.append(token)

    if not to_remove:
        await message.answer("Укажите @username")
        return

    result = remove_duty_users(to_remove)
    if invalid:
        result += "\n\nНе распознано:\n" + "\n".join(invalid)
    await message.answer(result)


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    users = list_duty_users()
    if not users:
        await message.answer("Список дежурных пуст")
        return
    lines = [f"{i + 1}. {format_user_label(u)}" for i, u in enumerate(users)]
    await message.answer("Список дежурных:\n" + "\n".join(lines))


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    duty, working = get_today_duty()
    if not working:
        await message.answer(
            f"Сегодня ({date.today():%d.%m.%Y}) — выходной, дежурства нет"
        )
        return
    if not duty:
        await message.answer("Список дежурных пуст")
        return
    await message.answer(f"Сегодня дежурит — {format_user_label(duty)}")


@router.message(Command("schedule"))
async def cmd_schedule(message: Message) -> None:
    users = list_duty_users()
    if not users:
        await message.answer("Список дежурных пуст")
        return
    schedule = simulate_schedule(days=14)
    await message.answer(format_schedule_message(schedule))


@router.chat_member(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_chat_member(update: ChatMemberUpdated) -> None:
    chat_id = get_chat_id()
    if chat_id and update.chat.id != chat_id:
        return

    old = update.old_chat_member
    new = update.new_chat_member
    user = new.user
    if not user or user.is_bot:
        return

    if new.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        if old.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
            if user.username:
                result = remove_duty_user(user.username)
                logger.info("Участник вышел: %s — %s", user.username, result)
