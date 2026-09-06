import os
import asyncio
import re
import sys
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError('Не заданы API_ID, API_HASH или BOT_TOKEN')

print('Бот запускается...', file=sys.stderr)
sys.stderr.flush()

client = TelegramClient('bot_session', API_ID, API_HASH)

TOPIC_IDS = {}

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        '👋 Привет! Я бот для проверки отчётов.\n'
        'Настрой меня:\n'
        '/set_reports_topic <ссылка_на_ветку> – задать ветку для отчётов\n'
        'Например: /set_reports_topic https://t.me/c/3934689847/4\n\n'
        'Проверка:\n'
        '/check_reports #Иванов #Петров – проверить отчёты за вчера\n\n'
        'Для справки: /help'
    )

@client.on(events.NewMessage(pattern='/set_reports_topic (.+)'))
async def set_reports_topic(event):
    link = event.pattern_match.group(1).strip()
    match = re.search(r'/(\d+)$', link)
    if not match:
        await event.reply('❌ Неверный формат ссылки. Ожидается: https://t.me/c/123456789/5')
        return
    thread_id = int(match.group(1))
    chat_id = event.chat_id
    TOPIC_IDS[chat_id] = thread_id
    await event.reply(f'✅ Ветка для отчётов установлена. ID темы: {thread_id}')

@client.on(events.NewMessage(pattern='/check_reports(.+)?'))
async def check_reports(event):
    chat_id = event.chat_id
    thread_id = TOPIC_IDS.get(chat_id)
    if not thread_id:
        await event.reply('⚠️ Сначала задай ветку для отчётов командой /set_reports_topic <ссылка>')
        return

    hashtags = []
    if event.pattern_match.group(1):
        hashtags = [h.strip() for h in event.pattern_match.group(1).split() if h.startswith('#')]
    if not hashtags:
        await event.reply('❌ Передай хэштеги: /check_reports #Иванов #Петров')
        return

    yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    today = yesterday + timedelta(days=1)

    result_lines = []
    for tag in hashtags:
        messages = await find_messages(chat_id, thread_id, tag, yesterday, today)
        if messages:
            links = [build_message_link(chat_id, msg.id, thread_id) for msg in messages]
            result_lines.append(f'{tag} ✅ {" ".join(links)}')
        else:
            result_lines.append(f'{tag} ❌')

    reply = f'📊 Отчёты за {yesterday.strftime("%d.%m.%Y")}:\n' + '\n'.join(result_lines)
    await event.reply(reply)

# ---------- НОВАЯ КОМАНДА /help ----------
@client.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    await event.reply(
        '📖 **Справка по командам бота:**\n\n'
        '/start – показать приветствие\n'
        '/set_reports_topic <ссылка> – задать ветку для отчётов\n'
        '   Пример: /set_reports_topic https://t.me/c/123456789/5\n'
        '/check_reports #хэштеги – проверить отчёты за вчера\n'
        '   Пример: /check_reports #Иванов #Петров\n'
        '/help – показать эту справку'
    )
# ----------------------------------------

async def find_messages(chat_id, thread_id, hashtag, date_from, date_to):
    try:
        messages = await client.get_messages(
            chat_id,
            limit=200,
            offset_date=int(date_to.timestamp()),
            reverse=False
        )
        found = []
        for msg in messages:
            if not msg.date or not (date_from <= msg.date < date_to):
                continue
            is_in_topic = False
            if msg.id == thread_id:
                is_in_topic = True
            elif msg.reply_to and hasattr(msg.reply_to, 'reply_to_top_id'):
                if msg.reply_to.reply_to_top_id == thread_id:
                    is_in_topic = True
            if not is_in_topic:
                continue
            if msg.message and re.search(rf'(?<!\w){re.escape(hashtag)}(?!\w)', msg.message, re.IGNORECASE):
                found.append(msg)
        return found
    except Exception as e:
        print(f'Ошибка при поиске сообщений: {e}', file=sys.stderr)
        return []

def build_message_link(chat_id, message_id, thread_id):
    chat_id_abs = abs(chat_id)
    if str(chat_id).startswith('-100'):
        chat_id_link = str(chat_id)[4:]
    else:
        chat_id_link = str(chat_id_abs)
    return f'https://t.me/c/{chat_id_link}/{message_id}?thread={thread_id}'

async def main():
    try:
        print('🔄 Подключение к Telegram...', file=sys.stderr)
        await client.start(bot_token=BOT_TOKEN)
        print('✅ Бот успешно запущен', file=sys.stderr)
        await client.run_until_disconnected()
    except Exception as e:
        print(f'❌ Критическая ошибка: {e}', file=sys.stderr)
    finally:
        await client.disconnect()
        print('🛑 Соединение закрыто', file=sys.stderr)

if __name__ == '__main__':
    asyncio.run(main())
