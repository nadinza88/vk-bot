import os
import time
import threading
import datetime
import re
import sys
import uuid

print("=" * 60)
print("ЗАПУСК БОТА - НАЧАЛО")
print("=" * 60)

print("\n[1] Попытка импорта vk_api...")
try:
    import vk_api
    from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
    from vk_api.utils import get_random_id
    print("[1] ✅ vk_api успешно импортирован")
except ImportError as e:
    print(f"[1] ❌ ОШИБКА: Не удалось импортировать vk_api: {e}")
    sys.exit(1)

print("\n[2] Попытка импорта python-dotenv...")
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[2] ✅ python-dotenv загружен")
except ImportError:
    print("[2] ⚠️ python-dotenv не установлен")

print("\n[3] Загрузка настроек...")
GROUP_TOKEN = os.environ.get('VK_TOKEN')
MANAGER_CHAT_ID = int(os.environ.get('MANAGER_CHAT_ID', 0))
TARGET_CHAT_ID = int(os.environ.get('TARGET_CHAT_ID', 0))

print(f"    VK_TOKEN: {'✅ Установлен' if GROUP_TOKEN else '❌ НЕ УСТАНОВЛЕН'}")
print(f"    MANAGER_CHAT_ID: {MANAGER_CHAT_ID}")
print(f"    TARGET_CHAT_ID: {TARGET_CHAT_ID}")

if not GROUP_TOKEN:
    print("[3] ❌ ОШИБКА: VK_TOKEN не найден!")
    sys.exit(1)

print("[3] ✅ Настройки загружены")

print("\n[4] Инициализация VK сессии...")
try:
    vk_session = vk_api.VkApi(token=GROUP_TOKEN)
    vk = vk_session.get_api()
    print("[4] ✅ VK сессия создана")
except Exception as e:
    print(f"[4] ❌ Ошибка: {e}")
    sys.exit(1)

print("\n[5] Проверка токена...")
try:
    group_info = vk.groups.getById()
    if group_info:
        print(f"[5] ✅ Токен валиден! Группа: {group_info[0]['name']} (ID: {group_info[0]['id']})")
        group_id = group_info[0]['id']
    else:
        group_id = None
except Exception as e:
    print(f"[5] ❌ Ошибка: {e}")
    sys.exit(1)

print("\n[6] Создание VkBotLongPoll...")
try:
    longpoll = VkBotLongPoll(vk_session, group_id=group_id)
    print(f"[6] ✅ VkBotLongPoll создан")
except Exception as e:
    print(f"[6] ❌ Ошибка: {e}")
    sys.exit(1)

scheduled_tasks = []
tasks_lock = threading.Lock()
temp_text = None
temp_datetime = None

def send_message(peer_id, text):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=get_random_id())
        print(f"    📤 Отправлено в {peer_id}: {text[:50]}...")
        return True
    except Exception as e:
        print(f"    ❌ Ошибка отправки: {e}")
        return False

def schedule_checker():
    print("[Поток] ✅ Запущен")
    while True:
        now = datetime.datetime.now()
        tasks_to_send = []
        with tasks_lock:
            remaining_tasks = []
            for task in scheduled_tasks:
                if task['datetime'] <= now:
                    tasks_to_send.append(task)
                else:
                    remaining_tasks.append(task)
            scheduled_tasks[:] = remaining_tasks
        for task in tasks_to_send:
            send_message(task['peer_id'], task['message'])
            print(f"    ✅ Отправлено запланированное сообщение #{task['id']}")
        time.sleep(1)

def parse_datetime(datetime_str):
    datetime_str = datetime_str.strip()
    now = datetime.datetime.now()
    
    match = re.match(r'^(\d{1,2}):(\d{2})$', datetime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            target = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)
            return target
    
    match = re.match(r'^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s+(\d{1,2}):(\d{2})$', datetime_str)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = match.group(3)
        hours = int(match.group(4))
        minutes = int(match.group(5))
        
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            if year:
                target_year = int(year)
            else:
                target_year = now.year
                if month < now.month:
                    target_year += 1
            try:
                target = datetime.datetime(target_year, month, day, hours, minutes, 0, 0)
                if target < now and target.date() != now.date():
                    target = target.replace(year=target.year + 1)
                return target
            except ValueError:
                return None
    return None

def format_task_list():
    if not scheduled_tasks:
        return "📭 Нет запланированных сообщений\n\nЧтобы создать сообщение:\n1. !текст ...\n2. !время 14:30"
    
    sorted_tasks = sorted(scheduled_tasks, key=lambda x: x['datetime'])
    
    header = f"📋 ЗАПЛАНИРОВАННЫЕ СООБЩЕНИЯ\n\n"
    header += f"Всего: {len(sorted_tasks)} сообщений\n\n"
    header += "--------------------------------\n\n"
    
    max_length = 3500
    parts = []
    current_part = header
    current_count = 0
    
    for i, task in enumerate(sorted_tasks, 1):
        datetime_str = task['datetime'].strftime("%d.%m.%Y в %H:%M")
        task_text = f"{i}. ID: {task['id']}\n"
        task_text += f"   Время: {datetime_str}\n"
        task_text += f"   Текст: {task['message']}\n"
        task_text += f"\n   Для отмены: !отмена {task['id']}\n"
        task_text += "\n--------------------------------\n\n"
        
        if len(current_part) + len(task_text) > max_length and current_count > 0:
            current_part += f"\n📄 Продолжение в следующем сообщении"
            parts.append(current_part)
            current_part = f"📋 ЗАПЛАНИРОВАННЫЕ СООБЩЕНИЯ (продолжение)\n\n"
            current_part += "--------------------------------\n\n"
            current_count = 0
        
        current_part += task_text
        current_count += 1
    
    if current_part:
        if len(parts) > 0:
            current_part += "\n📄 Конец списка\n\n"
        current_part += "Команды управления:\n"
        current_part += "!отмена ID - отменить сообщение\n"
        current_part += "!отменить_все - отменить все сообщения\n"
        current_part += "!план - показать этот список"
        parts.append(current_part)
    
    if len(parts) == 1:
        return parts[0]
    return parts

def show_commands(peer_id):
    commands_text = """🤖 БОТ ОТЛОЖЕННЫХ СООБЩЕНИЙ

================================

СОЗДАНИЕ СООБЩЕНИЯ

!текст Текст - задать текст сообщения
!время Дата Время - задать дату и время отправки

================================

ФОРМАТЫ ВРЕМЕНИ

14:30 - сегодня (или завтра если время прошло)
15.04 14:30 - 15 апреля в 14:30
15.04.2026 14:30 - 15 апреля 2026 в 14:30

================================

УПРАВЛЕНИЕ СООБЩЕНИЯМИ

!план - показать все запланированные сообщения
!отмена ID - отменить сообщение (ID из списка)
!отменить_все - отменить все сообщения
!статус - показать текущее редактируемое сообщение

================================

ДРУГИЕ КОМАНДЫ

!проверка - проверить связь с целевой беседой
!чат ID - сменить целевую беседу
!id - показать ID текущего чата
!стоп - остановить бота
!старт - показать это меню

================================

ПРИМЕРЫ

1) Создание сообщения
   !текст Всем привет!
   !время 14:30

2) Создание с конкретной датой
   !текст Напоминание о встрече
   !время 15.04 16:00

3) Управление
   !план
   !отмена abc12345
   !отменить_все

================================

Сообщение автоматически сохраняется после указания и времени, и текста"""
    
    send_message(peer_id, commands_text)

def show_status(peer_id):
    global temp_text, temp_datetime
    status_text = "📊 ТЕКУЩЕЕ РЕДАКТИРУЕМОЕ СООБЩЕНИЕ\n\n"
    
    if temp_text:
        status_text += f"Текст: {temp_text}\n"
    else:
        status_text += "Текст: не задан\n"
    
    if temp_datetime:
        status_text += f"Время: {temp_datetime.strftime('%d.%m.%Y в %H:%M')} (МСК)\n"
    else:
        status_text += "Время: не задано\n"
    
    status_text += "\n--------------------------------\n\n"
    
    if temp_text and temp_datetime:
        status_text += "ГОТОВО К СОХРАНЕНИЮ! Сообщение автоматически сохранится."
    elif temp_text:
        status_text += "Теперь задайте время командой !время\nФорматы: 14:30, 15.04 14:30, 15.04.2026 14:30"
    elif temp_datetime:
        status_text += "Теперь задайте текст командой !текст ..."
    else:
        status_text += "Нет редактируемого сообщения. Напишите !текст ... чтобы начать создание."
    
    send_message(peer_id, status_text)

def try_save_message(peer_id):
    global temp_text, temp_datetime
    if temp_text and temp_datetime:
        task_id = str(uuid.uuid4())[:8]
        with tasks_lock:
            scheduled_tasks.append({
                'id': task_id,
                'datetime': temp_datetime,
                'message': temp_text,
                'peer_id': TARGET_CHAT_ID
            })
        datetime_str = temp_datetime.strftime("%d.%m.%Y в %H:%M")
        
        save_msg = f"✅ СООБЩЕНИЕ СОХРАНЕНО!\n\n"
        save_msg += f"ID: {task_id}\n"
        save_msg += f"Текст: {temp_text}\n"
        save_msg += f"Время: {datetime_str} (МСК)\n\n"
        save_msg += "--------------------------------\n"
        save_msg += f"Посмотреть все: !план\n"
        save_msg += f"Отменить: !отмена {task_id}"
        
        send_message(peer_id, save_msg)
        temp_datetime = None
        temp_text = None
        return True
    return False

def cancel_task(peer_id, task_id):
    with tasks_lock:
        for i, task in enumerate(scheduled_tasks):
            if task['id'] == task_id:
                removed = scheduled_tasks.pop(i)
                datetime_str = removed['datetime'].strftime("%d.%m.%Y в %H:%M")
                cancel_msg = f"❌ СООБЩЕНИЕ ОТМЕНЕНО\n\n"
                cancel_msg += f"ID: {task_id}\n"
                cancel_msg += f"Текст: {removed['message'][:100]}\n"
                cancel_msg += f"Время: {datetime_str} (МСК)"
                send_message(peer_id, cancel_msg)
                return True
    
    send_message(peer_id, f"❌ Сообщение с ID {task_id} не найдено\n\nПроверьте ID командой !план")
    return False

def cancel_all_tasks(peer_id):
    with tasks_lock:
        count = len(scheduled_tasks)
        if count == 0:
            send_message(peer_id, "📭 Нет запланированных сообщений для отмены")
            return
        tasks_copy = scheduled_tasks.copy()
        scheduled_tasks.clear()
    
    cancel_msg = f"❌ ОТМЕНЕНО {count} СООБЩЕНИЙ\n\n"
    for task in tasks_copy[:5]:
        datetime_str = task['datetime'].strftime("%d.%m %H:%M")
        cancel_msg += f"{datetime_str} | {task['message'][:30]}...\n"
    if count > 5:
        cancel_msg += f"\n...и ещё {count - 5} сообщений"
    send_message(peer_id, cancel_msg)

def check_connection(peer_id):
    success = send_message(TARGET_CHAT_ID, "🔌 связь установлена")
    if success:
        send_message(peer_id, "✅ ПРОВЕРКА СВЯЗИ УСПЕШНА!\n\nСообщение 'связь установлена' отправлено в целевую беседу.")
    else:
        send_message(peer_id, "❌ ОШИБКА СВЯЗИ\n\nНе удалось отправить сообщение в целевую беседу.\nПроверьте права бота и ID беседы.")

def main():
    global temp_text, temp_datetime, TARGET_CHAT_ID
    print("\n" + "=" * 60)
    print("БОТ ЗАПУЩЕН! Готов к работе.")
    print(f"Управляющий чат ID: {MANAGER_CHAT_ID}")
    print(f"Целевой чат ID: {TARGET_CHAT_ID}")
    print("=" * 60)
    
    checker_thread = threading.Thread(target=schedule_checker, daemon=True)
    checker_thread.start()
    
    print("[Главный] Ожидание сообщений...\n")
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
            peer_id = event.obj.message['peer_id']
            text = event.obj.message.get('text', '').strip()
            
            if peer_id != MANAGER_CHAT_ID:
                continue
            
            print(f"[Событие] Чат: {peer_id} | Текст: {text}")
            
            if text == '!старт':
                show_commands(peer_id)
            elif text == '!план':
                result = format_task_list()
                if isinstance(result, list):
                    for part in result:
                        send_message(peer_id, part)
                        time.sleep(0.5)
                else:
                    send_message(peer_id, result)
            elif text == '!статус':
                show_status(peer_id)
            elif text == '!проверка':
                check_connection(peer_id)
            elif text == '!отменить_все':
                cancel_all_tasks(peer_id)
            elif text == '!стоп':
                send_message(peer_id, "🛑 Бот останавливается...")
                print("\nБот остановлен командой !стоп")
                os._exit(0)
            elif text == '!id':
                send_message(peer_id, f"ID этого чата: {peer_id}")
            elif text.startswith('!чат'):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send_message(peer_id, f"Ошибка! Формат: !чат ID_беседы\n\nТекущий чат: {TARGET_CHAT_ID}")
                    continue
                try:
                    new_chat_id = int(parts[1].strip())
                    
                    # Переносим отложенные сообщения в новый чат
                    with tasks_lock:
                        moved_count = len(scheduled_tasks)
                        for task in scheduled_tasks:
                            task['peer_id'] = new_chat_id
                        if moved_count > 0:
                            send_message(peer_id, f"📦 Перенесено {moved_count} отложенных сообщений в новую беседу")
                    
                    TARGET_CHAT_ID = new_chat_id
                    
                    # Сохраняем в файл .env
                    try:
                        with open('.env', 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        with open('.env', 'w', encoding='utf-8') as f:
                            for line in lines:
                                if line.startswith('TARGET_CHAT_ID='):
                                    f.write(f'TARGET_CHAT_ID={new_chat_id}\n')
                                else:
                                    f.write(line)
                    except:
                        pass
                    
                    send_message(peer_id, f"✅ Целевая беседа изменена!\nНовый ID: {new_chat_id}\n\nВсе отложенные сообщения будут отправлены в новую беседу.")
                except ValueError:
                    send_message(peer_id, "Ошибка! ID должен быть числом")
            elif text.startswith('!текст'):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send_message(peer_id, "Ошибка! Формат: !текст Ваше сообщение")
                    continue
                message_text = parts[1].strip()
                if message_text:
                    temp_text = message_text
                    if temp_datetime:
                        send_message(peer_id, f"Текст сохранён: {message_text}")
                        try_save_message(peer_id)
                    else:
                        send_message(peer_id, f"Текст сохранён: {message_text}\n\n--------------------------------\nТеперь задайте время командой !время\nФорматы: 14:30, 15.04 14:30, 15.04.2026 14:30")
                else:
                    send_message(peer_id, "Ошибка! Текст не может быть пустым.")
            elif text.startswith('!время'):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send_message(peer_id, "Ошибка! Формат: !время 14:30\n\nПримеры: !время 16:00, !время 20.04 10:30, !время 15.04.2026 09:00")
                    continue
                target_datetime = parse_datetime(parts[1])
                if target_datetime:
                    temp_datetime = target_datetime
                    if temp_text:
                        send_message(peer_id, f"Дата и время установлены: {target_datetime.strftime('%d.%m.%Y в %H:%M')} (МСК)")
                        try_save_message(peer_id)
                    else:
                        send_message(peer_id, f"Дата и время установлены: {target_datetime.strftime('%d.%m.%Y в %H:%M')} (МСК)\n\n--------------------------------\nТеперь задайте текст командой !текст ...")
                else:
                    send_message(peer_id, "Неверный формат!\n\nПоддерживаемые форматы:\n14:30 - сегодня/завтра\n15.04 14:30 - 15 апреля\n15.04.2026 14:30 - 15 апреля 2026")
            elif text.startswith('!отмена '):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send_message(peer_id, "Ошибка! Формат: !отмена ID_сообщения\n\nПолучить ID можно командой !план")
                    continue
                cancel_task(peer_id, parts[1].strip())
            elif text.startswith('!'):
                send_message(peer_id, "Неизвестная команда. Введите !старт для списка всех команд.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nБот остановлен")
    except Exception as e:
        print(f"Ошибка: {e}")
