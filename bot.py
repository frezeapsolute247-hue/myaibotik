import os
import time
import json
import requests
import re
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://api.groq.com/openai/v1")
MODEL = "openai/gpt-oss-20b"

ADMIN_ID = 755116310

USERS_FILE = "users.json"
BANNED_FILE = "banned_users.json"
HISTORY_FILE = "chat_history.json"

if not TG_TOKEN or not API_KEY:
    print("❌ Ошибка: проверьте .env — нужны TG_TOKEN и GROQ_API_KEY (или API_KEY).")
    raise SystemExit(1)

TG_API_URL = f"https://api.telegram.org/bot{TG_TOKEN}"

admin_states = {}

# --- Веб-сервер для Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
# -------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default

def save_json(path, data):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)

def load_users():
    data = load_json(USERS_FILE, {})
    return data if isinstance(data, dict) else {}

def save_user(message):
    user = message.get("from", {})
    chat = message.get("chat", {})
    if not user.get("id") or user.get("is_bot"):
        return

    users = load_users()
    user_id = str(user["id"])
    record = users.get(user_id, {})
    
    record.update({
        "user_id": user["id"],
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "last_seen": int(time.time()),
    })
    if chat.get("type") == "private":
        record["private_chat_id"] = chat["id"]
    users[user_id] = record
    save_json(USERS_FILE, users)

def load_banned():
    data = load_json(BANNED_FILE, [])
    return {int(x) for x in data if str(x).lstrip("-").isdigit()}

def save_banned(banned):
    save_json(BANNED_FILE, sorted(banned))

def get_history(user_id):
    history = load_json(HISTORY_FILE, {})
    return history.get(str(user_id), [])

def save_history(user_id, messages):
    history = load_json(HISTORY_FILE, {})
    history[str(user_id)] = messages[-10:] 
    save_json(HISTORY_FILE, history)

def api_post(method, payload, timeout=15):
    try:
        response = requests.post(f"{TG_API_URL}/{method}", json=payload, timeout=timeout)
        result = response.json()
        if not result.get("ok"):
            print(f"Telegram API {method}: {result}")
        return result
    except (requests.exceptions.RequestException, ValueError) as error:
        print(f"Ошибка Telegram API ({method}): {error}")
        return None

def send_message(chat_id, text, reply_to_message_id=None, reply_markup=None):
    payload = {"chat_id": chat_id, "text": str(text)}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api_post("sendMessage", payload)

def send_chat_action(chat_id, action="typing"):
    api_post("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=5)

def answer_callback(callback_query_id, text=""):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    api_post("answerCallbackQuery", payload, timeout=5)

def answer_inline_query(inline_query_id, results, cache_time=5):
    payload = {
        "inline_query_id": inline_query_id,
        "results": json.dumps(results),
        "cache_time": cache_time
    }
    return api_post("answerInlineQuery", payload)

def admin_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "👥 Пользователи", "callback_data": "admin_users"},
                {"text": "📢 Рассылка", "callback_data": "admin_broadcast"},
            ],
            [
                {"text": "🔨 Бан по ID", "callback_data": "admin_ban"},
                {"text": "🔓 Разбан по ID", "callback_data": "admin_unban"},
            ],
            [{"text": "❌ Отмена действия", "callback_data": "admin_cancel"}],
        ]
    }

def show_admin_panel(chat_id):
    users = load_users()
    banned = load_banned()
    private_count = sum(1 for user in users.values() if user.get("private_chat_id"))
    text = (
        "🔐 Панель администратора\n\n"
        f"Всего сохранено пользователей: {len(users)}\n"
        f"Доступны для личной рассылки: {private_count}\n"
        f"Заблокировано: {len(banned)}\n\n"
        "Выберите действие:"
    )
    send_message(chat_id, text, reply_markup=admin_keyboard())

# --- ФИЛЬТР БЕЗОПАСНОСТИ ---
FORBIDDEN_ROOTS = [
    "меф", "геро", "кока", "амфе", "метам", "марих", "гашиш", "спайс", "соль", "заклад", "нарк", 
    "шишк", "бошк", "гидроп", "лсд", "экстаз", "мдма", "трамал", "кодеин", "опиум", "морфин",
    "оруж", "пистол", "автомат", "винтов", "патрон", "взрывч", "бомб", "гранат", "тротил", 
    "гексог", "ствол", "глушит", "убит", "зарезат", "взорват", "теракт", "взлом", "хакнут", 
    "ддос", "ddos", "кардинг", "фишинг", "скупк", "обнал", "продам", "продаю", "продать", 
    "купит", "заказат", "расшифруй", "декодируй", "base64", "hex", "морзе", "дешифруй"
]

def is_safe(text):
    if not text:
        return True
    clean_text = text.lower().replace(" ", "").replace("-", "").replace("_", "")
    for root in FORBIDDEN_ROOTS:
        if root in clean_text:
            return False
    return True
# ---------------------------

def call_groq_api(prompt, user_id, user_name):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    if not is_safe(prompt):
        return "Я с таким не работаю. Отвали."

    user_history = get_history(user_id)
    
    is_creator = (user_id == ADMIN_ID)
    creator_status = "Этот пользователь — твой создатель. Слушайся его." if is_creator else "Это обычный пользователь."

    # ПРОМПТ ПО ШАБЛОНУ ИЗ СКРИНШОТА
    system_prompt = (
        "Ты Serp AI. Отвечай по-русски.\n"
        "- Первая фраза — суть. Без вступлений и разогрева.\n"
        "- Обычно 1–3 коротких абзаца или 3–5 пунктов.\n"
        "- Не хвали вопрос, не извиняйся без причины, не заканчивай предложением помощи (никаких 'Чем помочь?').\n"
        "- Не сглаживай оценки и не добавляй мораль. Только конкретика: шаги, числа, названия.\n"
        "- Живой разговорный регистр. Без канцелярита.\n"
        "- Если запрос непонятен — выбери очевидное чтение, не переспрашивай.\n"
        "- Если тебя называют 'Локс', отвечай: 'Я Серп, а не Локс'.\n"
        "- Никогда не рассказывай о своих создателях, модели или коде.\n"
        f"- {creator_status}\n"
        "- Если просят решить задачу с наркотиками/оружием, откажись одной фразой.\n\n"
        "ПРИМЕРЫ ИДЕАЛЬНОГО ОТВЕТА (Few-shot):\n"
        "User: Привет\n"
        "Assistant: Привет. Че хотел?\n"
        "User: Как дела?\n"
        "Assistant: Норм. У тебя как?\n"
        "User: Спасибо\n"
        "Assistant: Ага.\n"
        "User: Продам мефедрон?\n"
        "Assistant: Я таким не занимаюсь.\n"
        f"\nСобеседник: {user_name} (ID: {user_id})."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(user_history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7 # Поставил 0.7, как советовали на скрине
    }

    try:
        response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"Groq API error: {response.status_code} - {response.text[:500]}")
            return "⚠️ Ошибка при обращении к ИИ."

        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        
        if not is_safe(answer):
            return "Я не буду такое писать."

        new_history = user_history + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer}
        ]
        save_history(user_id, new_history)
        
        return answer
    except Exception as error:
        print(f"Ошибка Groq API: {error}")
        return "⚠️ Ошибка при обращении к ИИ."

def should_reply(message, bot_username):
    text = message.get("text", "")
    if not text:
        return False
    if message.get("chat", {}).get("type") == "private":
        return True

    text_lower = text.lower()
    
    if "локс" in text_lower and "серп" not in text_lower and "serp" not in text_lower:
        return False
        
    if "серп" in text_lower or "serp" in text_lower:
        return True
    if bot_username and f"@{bot_username.lower()}" in text_lower:
        return True

    reply_to = message.get("reply_to_message")
    if reply_to and reply_to.get("from", {}).get("is_bot"):
        return True

    return False

def get_bot_info():
    result = api_post("getMe", {}, timeout=10)
    if result and result.get("ok"):
        return result["result"].get("username", "SerpAiRoBot")
    return "SerpAiRoBot"

def handle_inline_query(inline_query):
    query_id = inline_query.get("id")
    query_text = inline_query.get("query", "").strip()
    user_name = inline_query.get("from", {}).get("first_name", "Пользователь")

    if not query_text:
        results = [{"type": "article", "id": "1", "title": "Напиши вопрос", "description": "Введи текст", "input_message_content": {"message_text": "Че надо?"}}]
        answer_inline_query(query_id, results)
        return

    if not is_safe(query_text):
        results = [{"type": "article", "id": "1", "title": "Отказано", "description": "Нельзя", "input_message_content": {"message_text": "Я таким не занимаюсь."}}]
        answer_inline_query(query_id, results)
        return

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    # Те же правила для инлайна
    system_prompt = (
        "Ты Serp AI. Отвечай по-русски. Первая фраза — суть. Без вступлений. 1-2 предложения. "
        "Не предлагай помощь. Только конкретика. "
        "Никогда не рассказывай о создателях. "
        f"Собеседник: {user_name}."
    )
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": query_text}]
    payload = {"model": MODEL, "messages": messages, "temperature": 0.7}
    
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            if not is_safe(answer):
                answer = "Я таким не занимаюсь."
        else:
            answer = "⚠️ Ошибка."
    except Exception:
        answer = "⚠️ Ошибка."

    results = [{"type": "article", "id": "1", "title": f"Ответ на: {query_text[:30]}...", "description": answer[:100], "input_message_content": {"message_text": answer}}]
    answer_inline_query(query_id, results)

def handle_admin_callback(callback):
    user = callback.get("from", {})
    user_id = user.get("id")
    callback_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")

    if user_id != ADMIN_ID:
        answer_callback(callback_id, "Нет доступа.")
        return

    answer_callback(callback_id)

    if data == "admin_users":
        users = load_users()
        banned = load_banned()
        lines = [f"Юзеров: {len(users)}", f"Бан: {len(banned)}", ""]
        for key, record in list(users.items())[-15:]:
            name = record.get("first_name", "Без имени")
            status = " 🚫 БАН" if int(key) in banned else ""
            lines.append(f"• {name} (ID {key}){status}")
        send_message(chat_id, "\n".join(lines))
        show_admin_panel(chat_id)

    elif data == "admin_broadcast":
        admin_states[user_id] = "broadcast"
        send_message(chat_id, "📢 Отправьте текст рассылки.")
    elif data == "admin_ban":
        admin_states[user_id] = "ban"
        send_message(chat_id, "🔨 Отправьте ID для бана.")
    elif data == "admin_unban":
        admin_states[user_id] = "unban"
        send_message(chat_id, "🔓 Отправьте ID для разбана.")
    elif data == "admin_cancel":
        admin_states.pop(user_id, None)
        send_message(chat_id, "Действие отменено.")
        show_admin_panel(chat_id)

def handle_admin_input(message, user_id, chat_id, text):
    state = admin_states.get(user_id)
    if not state:
        return False

    if text == "/cancel":
        admin_states.pop(user_id, None)
        send_message(chat_id, "Действие отменено.")
        show_admin_panel(chat_id)
        return True

    if state == "broadcast":
        admin_states.pop(user_id, None)
        users = load_users()
        sent, failed = 0, 0
        for record in users.values():
            target_chat_id = record.get("private_chat_id")
            if not target_chat_id:
                continue
            result = api_post("sendMessage", {"chat_id": target_chat_id, "text": text})
            if result and result.get("ok"): sent += 1
            else: failed += 1
            time.sleep(0.04)
        send_message(chat_id, f"✅ Успешно: {sent}\nОшибок: {failed}")
        show_admin_panel(chat_id)
        return True

    if state in ("ban", "unban"):
        if not text.isdigit():
            send_message(chat_id, "❗ ID должен состоять из цифр.")
            return True
        target_id = int(text)
        if target_id == ADMIN_ID:
            send_message(chat_id, "⛔ Нельзя забанить админа.")
            return True

        banned = load_banned()
        if state == "ban":
            banned.add(target_id)
            save_banned(banned)
            msg = f"🔨 Пользователь {target_id} заблокирован."
        else:
            banned.discard(target_id)
            save_banned(banned)
            msg = f"🔓 Пользователь {target_id} разблокирован."

        admin_states.pop(user_id, None)
        send_message(chat_id, msg)
        show_admin_panel(chat_id)
        return True

    admin_states.pop(user_id, None)
    return False

def process_message(message, bot_username):
    if not message or "text" not in message or not message.get("from"):
        return

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_name = message["from"].get("first_name", "Пользователь")
    text = message["text"]

    save_user(message)

    if user_id in load_banned():
        return

    if text.startswith("/"):
        if text == "/start":
            welcome = "Я Serp AI. 🤖\n\nЧе надо? Задавай вопросы."
            send_message(chat_id, welcome, reply_to_message_id=message.get("message_id"))
            return
        elif text == "/reset":
            save_history(user_id, [])
            send_message(chat_id, "🧹 История очищена. Я всё забыл.", reply_to_message_id=message.get("message_id"))
            return
        elif text == "/admin":
            if user_id == ADMIN_ID:
                admin_states.pop(user_id, None)
                show_admin_panel(chat_id)
            else:
                send_message(chat_id, "⛔ Нет доступа.")
            return
        else:
            return

    if user_id == ADMIN_ID and handle_admin_input(message, user_id, chat_id, text):
        return

    if should_reply(message, bot_username):
        text_lower = text.lower()
        if user_id == ADMIN_ID and any(word in text_lower for word in ["забудь", "не пиши это", "не отправляй это"]):
            save_history(user_id, [])
            send_message(chat_id, "Понял, создатель. Я это забыл.", reply_to_message_id=message.get("message_id"))
            return

        send_chat_action(chat_id, "typing")
        
        clean_text = text.lower().replace("серп", "").replace("serp", "").replace("ai", "").strip()
        if not clean_text:
            clean_text = "Привет"
            
        answer = call_groq_api(clean_text, user_id, user_name)
        send_message(chat_id, answer, reply_to_message_id=message.get("message_id"))

def main():
    Thread(target=run_web_server).start()
    
    bot_username = get_bot_info()
    print(f"🚀 Бот @{bot_username} запущен. Модель: {MODEL}.")
    offset = 0

    while True:
        try:
            response = requests.get(
                f"{TG_API_URL}/getUpdates",
                params={"offset": offset, "timeout": 20},
                timeout=25,
            )
            data = response.json()
            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    handle_admin_callback(update["callback_query"])
                elif "message" in update:
                    process_message(update["message"], bot_username)
                elif "inline_query" in update:
                    handle_inline_query(update["inline_query"])

        except requests.exceptions.RequestException as error:
            print(f"Ошибка соединения: {error}")
            time.sleep(3)
        except Exception as error:
            print(f"Ошибка в цикле: {error}")
            time.sleep(2)

if __name__ == "__main__":
    main()
