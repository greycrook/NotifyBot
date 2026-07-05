from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.database import get_chat_id
from bot.members import is_chat_admin


def resolve_group_chat_id(message: Message) -> int | None:
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        return message.chat.id
    return get_chat_id()


async def require_group_admin(message: Message, bot: Bot) -> bool:
    chat_id = resolve_group_chat_id(message)
    if not chat_id:
        await message.answer(
            "Чат ещё не привязан. Администратор группы выполняет /setchat в беседе."
        )
        return False
    if not message.from_user:
        return False
    if not await is_chat_admin(bot, chat_id, message.from_user.id):
        await message.answer("Команда доступна только администраторам группы.")
        return False
    return True
