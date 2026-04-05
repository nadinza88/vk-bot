import os
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import time
import threading
import datetime
import re

# Пытаемся импортировать dotenv для локальной разработки
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==================== ЗАГРУЗКА НАСТРОЕК ====================
GROUP_TOKEN = os.environ.get('VK_TOKEN')
MANAGER_CHAT_ID = int(os.environ.get('MANAGER_CHAT_ID', 0))
TARGET_CHAT_ID = int(os.environ.get('TARGET_CHAT_ID', 0))

# Проверка настроек
if not GROUP_TOKEN:
    raise ValueError("❌ Ошибка: переменная окружения VK_TOKEN не установлена!")
if MANAGER_CHAT_ID == 0 or TARGET_CHAT_ID == 0:
    raise ValueError("❌ Ошибка: MANAGER_CHAT_ID и TARGET_CHAT_ID должны быть установлены!")

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
scheduled_tasks = []  # Список запланированных задач
tasks_lock = threading.Lock()

# Временные переменные для текущего настраиваемого сообщения
temp_time = None  # Время отправки
temp_text = None  # Текст сообщения

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
vk_session = vk_api.VkApi(token=GROUP_TOKEN)
vk = vk_session.get_api()

# Получаем ID группы
try:
    if GROUP_TOKEN.startswith('vk1.a.'):
        group_info = vk.groups.getById()
        if group_info:
            group_id = group_info[0]['id']
        else:
            group_id = None
    else:
        group_id = GROUP_TOKEN.split('_')[0] if '_' in GROUP_TOKEN else None
except:
    group_id = None

longpoll = VkBotLongPoll(vk_session, group_id=group_id)

# ==================== ФУНКЦИИ ====================
def send_message(peer_id, text):
    """Отправляет сообщение в указанную беседу"""
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=text,
            random_id=int(time.time() * 1000)
        )
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Отправлено в {peer_id}: {text[:50]}...")
        return True
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def schedule_checker():
    """Фоновый поток для проверки расписания"""
    print("✅ Поток проверки расписания запущен")
    while True:
        now = datetime.datetime.now()
        tasks_to_send = []
        
        with tasks_lock:
            remaining_tasks = []
            for task in scheduled_tasks:
                if task['time'] <= now:
                    tasks_to_send.append(task)
                else:
                    remaining_tasks.append(task)
            scheduled_tasks[:] = remaining_tasks
        
        for task in tasks_to_send:
            send_message(task['peer_id'], task['message'])
        
        time.sleep(1)

def parse_time(time_str):
    """
    Парсит время из строки вида "14:30"
    Возвращает datetime или None
    """
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str.strip())
    if not match:
        return None
    
    hours = int(match.group(1))
    minutes = int(match.group(2))
    
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    
    now = datetime.datetime.now()
    target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    
    if target_time <= now:
        target_time += datetime.timedelta(days=1)
    
    return target_time

def show_commands(peer_id):
    """Показывает список доступных команд"""
    commands_text = """
🤖 *Команды бота отложенных сообщений*

📝 *Основные команды:*
• `!время ЧЧ:ММ` - установить время отправки (Московское)
• `!текст Текст сообщения` - установить текст для отправки
• `!статус` - показать текущее сообщение и время отправки
• `!старт` - показать это сообщение с командами
• `!проверка` - проверить связь с целевой беседой

📌 *Порядок работы:*
1. Сначала задайте время командой `!время 15:30`
2. Затем задайте текст командой `!текст Привет всем!`
3. После этого бот автоматически запланирует отправку

✨ *Пример:*
!время 14:00
!текст Всем привет! Напоминаю о встрече в 15:00

✅ После выполнения обеих команд сообщение будет отправлено в указанное время
    """
    send_message(peer_id, commands_text)

def show_status(peer_id):
    """Показывает текущий статус (время и текст)"""
    global temp_time, temp_text
    
    status_text = "📊 *Текущий статус:*\n\n"
    
    if temp_time:
        time_str = temp_time.strftime("%d.%m.%Y в %H:%M")
        status_text += f"⏰ *Время отправки:* {time_str} (МСК)\n"
    else:
        status_text += f"⏰ *Время отправки:* ❌ не задано\n"
    
    if temp_text:
        status_text += f"📝 *Текст сообщения:* {temp_text}\n"
    else:
        status_text += f"📝 *Текст сообщения:* ❌ не задан\n"
    
    status_text += "\n"
    
    if temp_time and temp_text:
        status_text += "✅ *Сообщение готово к отправке!*\n"
        status_text += f"Оно будет отправлено в {temp_time.strftime('%H:%M')} (МСК)"
    else:
        status_text += "⚠️ *Не хватает данных:*\n"
        if not temp_time:
            status_text += "• Задайте время командой !время ЧЧ:ММ\n"
        if not temp_text:
            status_text += "• Задайте текст командой !текст Ваше сообщение"
    
    send_message(peer_id, status_text)

def schedule_message(peer_id):
    """Планирует отправку сообщения, если заданы и время, и текст"""
    global temp_time, temp_text
    
    if temp_time and temp_text:
        with tasks_lock:
            scheduled_tasks.append({
                'time': temp_time,
                'message': temp_text,
                'peer_id': TARGET_CHAT_ID
            })
        
        time_str = temp_time.strftime("%d.%m.%Y в %H:%M")
        send_message(peer_id, f"✅ *Сообщение запланировано!*\n\n⏰ Время: {time_str} (МСК)\n📝 Текст: {temp_text}\n\nСообщение будет отправлено в целевую беседу.")
        
        # Очищаем временные переменные после планирования
        temp_time = None
        temp_text = None
        return True
    else:
        error_msg = "❌ *Не могу запланировать сообщение!*\n\nНе хватает данных:\n"
        if not temp_time:
            error_msg += "• Задайте время командой !время ЧЧ:ММ\n"
        if not temp_text:
            error_msg += "• Задайте текст командой !текст Ваше сообщение"
        send_message(peer_id, error_msg)
        return False

def check_connection(peer_id):
    """Проверяет связь с целевой беседой"""
    success = send_message(TARGET_CHAT_ID, "🔌 связь установлена")
    if success:
        send_message(peer_id, "✅ *Проверка связи:* Сообщение 'связь установлена' отправлено в целевую беседу!")
    else:
        send_message(peer_id, "❌ *Ошибка связи:* Не удалось отправить сообщение в целевую беседу. Проверьте права бота и ID беседы.")

# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================
def main():
    global temp_time, temp_text
    
    print("=" * 50)
    print("Бот отложенных сообщений ВК запущен")
    print(f"Управляющий чат ID: {MANAGER_CHAT_ID}")
    print(f"Целевой чат ID: {TARGET_CHAT_ID}")
    print("=" * 50)
    print("Доступные команды: !старт - список команд")
    print("=" * 50)
    
    # Запускаем поток проверки расписания
    checker_thread = threading.Thread(target=schedule_checker, daemon=True)
    checker_thread.start()
    
    # Основной цикл
    try:
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                peer_id = event.obj.message['peer_id']
                text = event.obj.message['text'].strip()
                
                # Игнорируем сообщения не из управляющего чата
                if peer_id != MANAGER_CHAT_ID:
                    continue
                
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Получено: {text}")
                
                # Обработка команд
                if text.startswith('!время'):
                    # Команда !время ЧЧ:ММ
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_message(peer_id, "❌ *Ошибка!*\nФормат: `!время 14:30`\nПример: `!время 15:45`")
                        continue
                    
                    time_str = parts[1]
                    target_time = parse_time(time_str)
                    
                    if target_time:
                        temp_time = target_time
                        time_str_formatted = target_time.strftime("%d.%m.%Y в %H:%M")
                        send_message(peer_id, f"✅ *Время установлено:* {time_str_formatted} (МСК)\n\nТеперь задайте текст командой `!текст Ваше сообщение`")
                        
                        # Если и текст уже есть, сразу планируем
                        if temp_text:
                            schedule_message(peer_id)
                    else:
                        send_message(peer_id, "❌ *Ошибка!* Неверный формат времени.\nИспользуйте: `!время ЧЧ:ММ`\nПример: `!время 14:30`")
                
                elif text.startswith('!текст'):
                    # Команда !текст Текст сообщения
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_message(peer_id, "❌ *Ошибка!*\nФормат: `!текст Ваше сообщение`\nПример: `!текст Привет всем!`")
                        continue
                    
                    message_text = parts[1].strip()
                    if message_text:
                        temp_text = message_text
                        send_message(peer_id, f"✅ *Текст установлен:* {message_text}\n\nТеперь задайте время командой `!время ЧЧ:ММ`")
                        
                        # Если и время уже есть, сразу планируем
                        if temp_time:
                            schedule_message(peer_id)
                    else:
                        send_message(peer_id, "❌ *Ошибка!* Текст сообщения не может быть пустым.")
                
                elif text == '!статус':
                    show_status(peer_id)
                
                elif text == '!старт':
                    show_commands(peer_id)
                
                elif text == '!проверка':
                    check_connection(peer_id)
                
                elif text.startswith('!'):
                    # Неизвестная команда
                    send_message(peer_id, "❌ *Неизвестная команда!*\n\nВведите `!старт` для просмотра всех доступных команд.")
    
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        time.sleep(5)
        main()

if __name__ == '__main__':
    main()
