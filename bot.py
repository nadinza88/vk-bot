import os
import time
import threading
import datetime
import re
import sys

print("=" * 60)
print("ЗАПУСК БОТА - НАЧАЛО")
print("=" * 60)

# Шаг 1: Попытка импорта vk_api
print("\n[1] Попытка импорта vk_api...")
try:
    import vk_api
    from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
    from vk_api.utils import get_random_id
    print("[1] ✅ vk_api успешно импортирован")
except ImportError as e:
    print(f"[1] ❌ ОШИБКА: Не удалось импортировать vk_api")
    print(f"    Текст ошибки: {e}")
    print(f"    Решение: Установите библиотеку командой: pip install vk-api")
    sys.exit(1)
except Exception as e:
    print(f"[1] ❌ Неожиданная ошибка при импорте: {e}")
    sys.exit(1)

# Шаг 2: Попытка импорта dotenv
print("\n[2] Попытка импорта python-dotenv...")
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[2] ✅ python-dotenv загружен (для локальной разработки)")
except ImportError:
    print("[2] ⚠️ python-dotenv не установлен (пропускаем, используем переменные окружения)")
except Exception as e:
    print(f"[2] ⚠️ Ошибка при загрузке .env: {e}")

# ==================== ЗАГРУЗКА НАСТРОЕК ====================
print("\n[3] Загрузка настроек из переменных окружения...")

GROUP_TOKEN = os.environ.get('VK_TOKEN')
MANAGER_CHAT_ID_STR = os.environ.get('MANAGER_CHAT_ID', '0')
TARGET_CHAT_ID_STR = os.environ.get('TARGET_CHAT_ID', '0')

print(f"    VK_TOKEN: {'Установлен' if GROUP_TOKEN else '❌ НЕ УСТАНОВЛЕН'}")
print(f"    MANAGER_CHAT_ID: {MANAGER_CHAT_ID_STR}")
print(f"    TARGET_CHAT_ID: {TARGET_CHAT_ID_STR}")

# Проверка наличия токена
if not GROUP_TOKEN:
    print("\n[3] ❌ КРИТИЧЕСКАЯ ОШИБКА: VK_TOKEN не найден!")
    print("    Решение: Установите переменную окружения VK_TOKEN")
    print("    Или создайте файл .env с содержимым: VK_TOKEN=ваш_токен")
    sys.exit(1)

# Конвертируем ID в числа
try:
    MANAGER_CHAT_ID = int(MANAGER_CHAT_ID_STR)
    TARGET_CHAT_ID = int(TARGET_CHAT_ID_STR)
    print(f"[3] ✅ ID чатов сконвертированы успешно")
except ValueError as e:
    print(f"[3] ❌ ОШИБКА: Не удалось сконвертировать ID чатов в числа")
    print(f"    Ошибка: {e}")
    sys.exit(1)

if MANAGER_CHAT_ID == 0 or TARGET_CHAT_ID == 0:
    print("[3] ⚠️ ВНИМАНИЕ: MANAGER_CHAT_ID или TARGET_CHAT_ID равны 0")
    print("    Убедитесь, что вы установили правильные ID бесед!")

print("[3] ✅ Настройки загружены")

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
scheduled_tasks = []
tasks_lock = threading.Lock()

# Временные переменные для текущего настраиваемого сообщения
temp_time = None
temp_text = None

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
print("\n[4] Инициализация VK сессии...")

try:
    vk_session = vk_api.VkApi(token=GROUP_TOKEN)
    vk = vk_session.get_api()
    print("[4] ✅ VK сессия создана")
except Exception as e:
    print(f"[4] ❌ ОШИБКА при создании VK сессии: {e}")
    print("    Возможные причины:")
    print("    1. Неверный формат токена")
    print("    2. Токен просрочен")
    print("    3. Токен не имеет нужных прав")
    sys.exit(1)

# Проверка токена
print("\n[5] Проверка токена (получение информации о группе)...")
try:
    group_info = vk.groups.getById()
    if group_info:
        group_id = group_info[0]['id']
        group_name = group_info[0]['name']
        print(f"[5] ✅ Токен валиден!")
        print(f"    Группа: {group_name} (ID: {group_id})")
    else:
        print("[5] ⚠️ Не удалось получить информацию о группе")
        group_id = None
except Exception as e:
    print(f"[5] ❌ ОШИБКА при проверке токена: {e}")
    print("    Возможные причины:")
    print("    1. Токен недействителен")
    print("    2. У токена нет прав на чтение информации о группе")
    print("    3. Токен отозван")
    sys.exit(1)

# Создание LongPoll
print("\n[6] Создание VkBotLongPoll...")
try:
    longpoll = VkBotLongPoll(vk_session, group_id=group_id)
    print(f"[6] ✅ VkBotLongPoll создан (group_id={group_id})")
except Exception as e:
    print(f"[6] ❌ ОШИБКА при создании VkBotLongPoll: {e}")
    sys.exit(1)

# ==================== ФУНКЦИИ ====================
def send_message(peer_id, text):
    """Отправляет сообщение в указанную беседу"""
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=text,
            random_id=get_random_id()
        )
        print(f"    📤 Отправлено в {peer_id}: {text[:50]}...")
        return True
    except Exception as e:
        print(f"    ❌ Ошибка отправки: {e}")
        return False

def schedule_checker():
    """Фоновый поток для проверки расписания"""
    print("[Поток] ✅ Запущен")
    last_check = None
    while True:
        try:
            now = datetime.datetime.now()
            
            # Логируем только раз в минуту, чтобы не заспамливать
            if last_check is None or (now - last_check).seconds >= 60:
                print(f"[Поток] Проверка расписания... Запланировано задач: {len(scheduled_tasks)}")
                last_check = now
            
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
                print(f"[Поток] ⏰ Отправка запланированного сообщения...")
                send_message(task['peer_id'], task['message'])
            
            time.sleep(1)
        except Exception as e:
            print(f"[Поток] ❌ Ошибка: {e}")
            time.sleep(5)

def parse_time(time_str):
    """Парсит время из строки вида '14:30'"""
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
    """
    send_message(peer_id, commands_text)

def show_status(peer_id):
    """Показывает текущий статус"""
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
    """Планирует отправку сообщения"""
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
        
        # Очищаем временные переменные
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
    
    print("\n" + "=" * 60)
    print("ЗАПУСК ОСНОВНОГО ЦИКЛА БОТА")
    print("=" * 60)
    print(f"Управляющий чат ID: {MANAGER_CHAT_ID}")
    print(f"Целевой чат ID: {TARGET_CHAT_ID}")
    print("=" * 60)
    print("Доступные команды: !старт - список команд")
    print("Бот готов к работе!")
    print("=" * 60 + "\n")
    
    # Запускаем поток проверки расписания
    print("[Главный] Запуск фонового потока для проверки расписания...")
    checker_thread = threading.Thread(target=schedule_checker, daemon=True)
    checker_thread.start()
    print("[Главный] ✅ Фоновый поток запущен")
    
    # Основной цикл
    event_count = 0
    try:
        print("[Главный] Вход в цикл прослушивания событий...\n")
        for event in longpoll.listen():
            event_count += 1
            print(f"\n[Событие #{event_count}] Тип: {event.type}")
            
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                peer_id = event.obj.message['peer_id']
                text = event.obj.message.get('text', '').strip()
                from_id = event.obj.message.get('from_id', 'unknown')
                
                print(f"    От: {from_id}")
                print(f"    Чат ID: {peer_id}")
                print(f"    Текст: {text}")
                
                # Игнорируем сообщения не из управляющего чата
                if peer_id != MANAGER_CHAT_ID:
                    print(f"    ⏭️ Пропускаем (не управляющий чат, ожидается {MANAGER_CHAT_ID})")
                    continue
                
                print(f"    ✅ Обрабатываю команду...")
                
                # Обработка команд
                if text.startswith('!время'):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_message(peer_id, "❌ *Ошибка!*\nФормат: `!время 14:30`")
                        continue
                    
                    target_time = parse_time(parts[1])
                    if target_time:
                        temp_time = target_time
                        send_message(peer_id, f"✅ *Время установлено:* {target_time.strftime('%d.%m.%Y в %H:%M')} (МСК)\n\nТеперь задайте текст командой `!текст ...`")
                        
                        if temp_text:
                            schedule_message(peer_id)
                    else:
                        send_message(peer_id, "❌ *Ошибка!* Неверный формат времени.\nИспользуйте: `!время ЧЧ:ММ`")
                
                elif text.startswith('!текст'):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_message(peer_id, "❌ *Ошибка!*\nФормат: `!текст Ваше сообщение`")
                        continue
                    
                    message_text = parts[1].strip()
                    if message_text:
                        temp_text = message_text
                        send_message(peer_id, f"✅ *Текст установлен:* {message_text}\n\nТеперь задайте время командой `!время ЧЧ:ММ`")
                        
                        if temp_time:
                            schedule_message(peer_id)
                    else:
                        send_message(peer_id, "❌ *Ошибка!* Текст не может быть пустым.")
                
                elif text == '!статус':
                    show_status(peer_id)
                
                elif text == '!старт':
                    show_commands(peer_id)
                
                elif text == '!проверка':
                    check_connection(peer_id)
                
                elif text.startswith('!'):
                    send_message(peer_id, "❌ *Неизвестная команда!*\n\nВведите `!старт` для списка команд.")
                else:
                    print(f"    ⏭️ Не команда, игнорирую")
            
            elif event.type == VkBotEventType.MESSAGE_NEW:
                print(f"    ⏭️ Не из чата (from_chat=False), игнорирую")
            else:
                print(f"    ⏭️ Другой тип события, игнорирую")
    
    except KeyboardInterrupt:
        print("\n\n[Главный] ⚠️ Получен сигнал остановки (Ctrl+C)")
        print("[Главный] Бот остановлен пользователем")
    
    except Exception as e:
        print(f"\n[Главный] ❌ КРИТИЧЕСКАЯ ОШИБКА в цикле обработки: {e}")
        import traceback
        print("\n" + "=" * 60)
        print("ПОЛНЫЙ СТЕК ОШИБКИ:")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        print("\nБот будет перезапущен через 5 секунд...")
        time.sleep(5)
        print("Перезапуск...\n")
        main()

# ==================== ТОЧКА ВХОДА ====================
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ Необработанная ошибка: {e}")
        import traceback
        traceback.print_exc()
        input("\nНажмите Enter для выхода...")
