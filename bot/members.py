from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMember, User

NOT_IN_CHAT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


async def get_member_by_user_id(
    bot: Bot, chat_id: int, user_id: int
) -> ChatMember | None:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest:
        return None
    if member.status in NOT_IN_CHAT:
        return None
    return member


async def find_user_id_in_chat(
    bot: Bot, chat_id: int, username: str
) -> User | None:
    """Ищет участника по @username среди админов группы."""
    username = username.lower().lstrip("@")
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except TelegramBadRequest:
        return None
    for m in admins:
        u = m.user
        if u.username and u.username.lower() == username:
            return u
    return None


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest:
        return False
    return member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
    }
