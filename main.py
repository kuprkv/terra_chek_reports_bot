import os
import asyncio
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.network.connection import ConnectionTcpFull
from dotenv import load_dotenv

load_dotenv()  # загружаем переменные из .env (на локальной машине)

API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError('Не заданы API_ID, API_HASH или BOT_TOKEN')

# Инициализация клиента с явными параметрами для надёжности
client = TelegramClient(
    'bot_session',
    API_ID,
    API_HASH,
    timeout=30,
    retries=10,
    connection=ConnectionTcpFull,
    connection_parameters={
        'ip': '149.154.167.91',   # DC1 – при необходимости замените на свой DC
        'port': 443,              # или 80, если 443 заблокирован
        'dc_id': 1,
    }
)

# Хранилище: для каждой группы храним названия веток
TOPIC_NAMES = {}  # chat_id -> {'reports': 'Отчёты', 'homework': 'Домашки'}

# --------------------- Команды настройки ---------------------
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        '👋 Привет! Я бот для проверки отчётов и домашних заданий.\n'
        'Настрой меня:\n'
        '/set_reports_topic <название> – ветка для отчётов\n'
        '/set_homework_topic <название> – ветка для домашек\n\n'
        'Проверка:\n'
        '/check_reports #Иванов #Петров\n'
        '/check_homework #Иванов #Петров'
    )

@client.on(events.NewMessage(pattern='/set_reports_topic (.+)'))
async def set_reports_topic(event):
    topic_name = event.pattern_match.group(1).strip()
    chat_id = event.chat_id
    if chat_id not in TOPIC_NAMES:
        TOPIC_NAMES[chat_id] = {}
    TOPIC_NAMES[chat_id]['reports'] = topic_name
    await event.reply(f'✅ Ветка для отчётов установлена: "{topic_name}"')

@client.on(events.NewMessage(pattern='/set_homework_topic (.+)'))
async def set_homework_topic(event):
    topic_name = event.pattern_match.group(1).strip()
    chat_id = event.chat_id
    if chat_id not in TOPIC_NAMES:
        TOPIC_NAMES[chat_id] = {}
    TOPIC_NAMES[chat_id]['homework'] = topic_name
    await event.reply(f'✅ Ветка для домашних заданий установлена: "{topic_name}"')

# --------------------- Команды проверки ---------------------
@client.on(events.NewMessage(pattern='/check_reports(.+)?'))
async def check_reports(event):
    await handle_check(event, 'reports')

@client.on(events.NewMessage(pattern='/check_homework(.+)?'))
async def check_homework(event):
    await handle_check(event, 'homework')

async def handle_check(event, check_type):
    chat_id = event.chat_id
    topic_name = TOPIC_NAMES.get(chat_id, {}).get(check_type)
    if not topic_name:
        await event.reply(f'⚠️ Сначала задай ветку для {"отчётов" if check_type == "reports" else "домашек"} командой /set_{check_type}_topic')
        return

    # Парсим хэштеги из команды
    hashtags = []
    if event.pattern_match.group(1):
        hashtags = [h.strip() for h in event.pattern_match.group(1).split() if h.startswith('#')]
    if not hashtags:
        await event.reply(f'❌ Передай хэштеги: /{event.pattern_match.string.split()[0]} #Иванов #Петров')
        return

    # Ищем ID ветки
    thread_id = await find_topic_id(chat_id, topic_name)
    if not thread_id:
        await event.reply(f'❌ Ветка "{topic_name}" не найдена')
        return

    # Вчерашний день
    yesterday = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    today = yesterday + timedelta(days=1)

    # Проверяем каждый хэштег
    result_lines = []
    for tag in hashtags:
        messages = await find_messages(chat_id, thread_id, tag, yesterday, today)
        if messages:
            links = [build_message_link(chat_id, msg.id, thread_id) for msg in messages]
            result_lines.append(f'{tag} ✅ {" ".join(links)}')
        else:
            result_lines.append(f'{tag} ❌')

    reply = f'📊 {"Отчёты" if check_type == "reports" else "Домашки"} за {yesterday.strftime("%d.%m.%Y")}:\n' + '\n'.join(result_lines)
    await event.reply(reply)

# --------------------- Вспомогательные функции ---------------------
async def find_topic_id(chat_id, topic_name):
    """Ищет ID ветки форума по её названию"""
    try:
        async for dialog in client.iter_dialogs():
            if dialog.id == chat_id and dialog.is_group:
                topics = await client.get_topics(dialog.entity)
                for t in topics:
                    if t.title.lower() == topic_name.lower():
                        return t.id
    except Exception as e:
        print(f'Ошибка при поиске ветки: {e}')
    return None

async def find_messages(chat_id, thread_id, hashtag, date_from, date_to):
    """
    Ищет сообщения в указанной ветке за период, содержащие хэштег.
    Возвращает список объектов Message.
    """
    try:
        messages = await client.get_messages(
            chat_id,
            limit=200,
            offset_date=int(date_to.timestamp()),
            reply_to=thread_id,
            reverse=False
        )
        found = []
        for msg in messages:
            if msg.date and msg.date >= date_from and msg.date < date_to:
                if msg.message and re.search(rf'(?<!\w){re.escape(hashtag)}(?!\w)', msg.message, re.IGNORECASE):
                    found.append(msg)
        return found
    except Exception as e:
        print(f'Ошибка при поиске сообщений: {e}')
        return []

def build_message_link(chat_id, message_id, thread_id):
    """Генерирует ссылку на сообщение в ветке"""
    chat_id_abs = abs(chat_id)
    if str(chat_id).startswith('-100'):
        chat_id_link = str(chat_id)[4:]
    else:
        chat_id_link = str(chat_id_abs)
    return f'https://t.me/c/{chat_id_link}/{message_id}?thread={thread_id}'

# --------------------- Запуск бота ---------------------
async def main():
    try:
        print('🔄 Подключение к Telegram...')
        await client.start(bot_token=BOT_TOKEN)
        print('✅ Бот успешно запущен')
        await client.run_until_disconnected()
    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')
    finally:
        await client.disconnect()
        print('🛑 Соединение закрыто')

if __name__ == '__main__':
    asyncio.run(main())
