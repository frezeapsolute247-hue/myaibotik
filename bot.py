import os
import time
import json
import requests
import re
import asyncio
import io
import base64
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SendReactionRequest

try:
    from pexafy import Client as PexafyClient
    PEXAFY_AVAILABLE = True
except ImportError:
    PEXAFY_AVAILABLE = False

load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://api.groq.com/openai/v1")
MODEL = "openai/gpt-oss-20b"
VISION_MODEL = "qwen/qwen3.8-27b"

API_ID = int(os.getenv("TG_API_ID", "31124227")) 
API_HASH = os.getenv("TG_API_HASH", "439abf786f2ae0c75e25b5deb9e5a14c") 

PEXAFY_API_KEY = "pexafy_api_R_k38Coq3RFVPsJ2koF5ZxXDEnEZi38umXEIw9lfcQ8"

ADMIN_ID = 755116310
USERS_FILE = "users.json"
BANNED_FILE = "banned_users.json"
HISTORY_FILE = "chat_history.json"

if not TG_TOKEN or not API_KEY:
    raise SystemExit(1)

TG_API_URL = f"https://api.telegram.org/bot{TG_TOKEN}"
admin_states = {}

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except:
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
    if not user.get("id") or user.get("is_bot"): return
    users = load_users()
    user_id = str(user["id"])
    record = users.get(user_id, {})
    record.update({
        "user_id": user["id"], "username": user.get("username"),
        "first_name": user.get("first_name"), "last_name": user.get("last_name"),
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
        return response.json()
    except:
        return None

def send_photo(chat_id, photo_url, caption=None, reply_to_message_id=None):
    try:
        resp = requests.get(photo_url, timeout=15)
        resp.raise_for_status()
        files = {'photo': ('photo.jpg', io.BytesIO(resp.content), 'image/jpeg')}
        payload = {'chat_id': chat_id}
        if caption: payload['caption'] = caption
        if reply_to_message_id: payload['reply_to_message_id'] = reply_to_message_id
        return requests.post(f"{TG_API_URL}/sendPhoto", data=payload, files=files, timeout=30).json()
    except Exception as e:
        print(f"Ошибка фото: {e}")
        return None

def send_message(chat_id, text, reply_to_message_id=None, reply_markup=None):
    payload = {"chat_id": chat_id, "text": str(text)}
    if reply_to_message_id: payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup: payload["reply_markup"] = reply_markup
    return api_post("sendMessage", payload)

def send_chat_action(chat_id, action="typing"):
    api_post("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=5)

def answer_callback(callback_query_id, text=""):
    payload = {"callback_query_id": callback_query_id}
    if text: payload["text"] = text
    api_post("answerCallbackQuery", payload, timeout=5)

def answer_inline_query(inline_query_id, results, cache_time=5):
    payload = {"inline_query_id": inline_query_id, "results": json.dumps(results), "cache_time": cache_time}
    return api_post("answerInlineQuery", payload)

def admin_keyboard():
    return {"inline_keyboard": [[{"text": "👥 Пользователи", "callback_data": "admin_users"}, {"text": "📢 Рассылка", "callback_data": "admin_broadcast"}], [{"text": "🔨 Бан", "callback_data": "admin_ban"}, {"text": "🔓 Разбан", "callback_data": "admin_unban"}], [{"text": "❌ Отмена", "callback_data": "admin_cancel"}]]}

def show_admin_panel(chat_id):
    users = load_users(); banned = load_banned()
    private_count = sum(1 for user in users.values() if user.get("private_chat_id"))
    text = f"🔐 Админка\n\nЮзеров: {len(users)}\nДля рассылки: {private_count}\nВ бане: {len(banned)}\n\nВыбери:"
    send_message(chat_id, text, reply_markup=admin_keyboard())

FORBIDDEN_ROOTS = [
    "меф", "геро", "кока", "амфе", "метам", "марих", "гашиш", "спайс", "соль", "заклад", "нарк", 
    "шишк", "бошк", "гидроп", "лсд", "экстаз", "мдма", "трамал", "кодеин", "опиум", "морфин",
    "оруж", "пистол", "автомат", "винтов", "патрон", "взрывч", "бомб", "гранат", "тротил", 
    "гексог", "ствол", "глушит", "убит", "зарезат", "взорват", "теракт", "взлом", "хакнут", 
    "ддос", "ddos", "кардинг", "фишинг", "скупк", "обнал", "продам", "продаю", "продать", 
    "купит", "заказат", "расшифруй", "декодируй", "base64", "hex", "морзе", "дешифруй"
]

def is_safe(text):
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    for word in words:
        for root in FORBIDDEN_ROOTS:
            if root in word:
                return False
    return True

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ПОНЯТИЯ СУТИ ЗАПРОСА ---
def extract_search_query(user_text):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    system_prompt = (
        "Ты — помощник, который превращает просьбу пользователя в короткий поисковый запрос для фотостока. "
        "Выдели из текста только суть (2-3 слова), что именно хочет увидеть человек. "
        "Переведи это на английский язык. "
        "Пример: 'нет мне нужно фото вот когда ростки выросли маленькие скинь фото' -> 'pepper seedlings'. "
        "Ответь ТОЛЬКО поисковым запросом, без кавычек и лишних слов."
    )
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}]
    payload = {"model": MODEL, "messages": messages, "temperature": 0.1, "max_tokens": 20}
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
    except:
        pass
    return "nature"
# ------------------------------------------------

def call_groq_api(prompt, user_id, user_name, image_base64=None):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    if not is_safe(prompt):
        return "Я с таким не работаю. Отвали."

    user_history = get_history(user_id)
    
    system_prompt = (
        "Ты — Serp AI, обычный пацан-бот в Telegram. Твое имя — Serp. "
        "Общайся как друг, кратко и по делу. "
        "Если на фото видно что-то незаконное (наркотики, оружие, насилие) — откажись это обсуждать. "
        "Если тебя оскорбляют — отвечай дерзко, но без матов. "
        f"Собеседник: {user_name}."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(user_history)
    
    if image_base64:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]
        messages.append({"role": "user", "content": user_content})
        model_to_use = VISION_MODEL
    else:
        messages.append({"role": "user", "content": prompt})
        model_to_use = MODEL

    payload = {"model": model_to_use, "messages": messages, "temperature": 0.8}

    try:
        response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"Groq error: {response.text}")
            return "⚠️ Ошибка при обращении к ИИ."

        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        
        if not image_base64:
            new_history = user_history + [{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}]
            save_history(user_id, new_history)
        
        return answer
    except Exception as error:
        print(f"Ошибка Groq API: {error}")
        return "⚠️ Ошибка при обращении к ИИ."

def should_reply(message, bot_username):
    text = message.get("text", "")
    if not text and not message.get("photo"): return False
    if message.get("chat", {}).get("type") == "private": return True

    text_lower = text.lower() if text else ""
    if "серп" in text_lower or "serp" in text_lower: return True
    if bot_username and f"@{bot_username.lower()}" in text_lower: return True
    if message.get("reply_to_message", {}).get("from", {}).get("is_bot"): return True
    return False

def get_bot_info():
    result = api_post("getMe", {}, timeout=10)
    return result["result"].get("username", "SerpAiRoBot") if result and result.get("ok") else "SerpAiRoBot"

def handle_inline_query(inline_query):
    query_id = inline_query.get("id")
    query_text = inline_query.get("query", "").strip()
    user_name = inline_query.get("from", {}).get("first_name", "Пользователь")

    if not query_text:
        results = [{"type": "article", "id": "1", "title": "Напиши вопрос", "description": "Введи текст", "input_message_content": {"message_text": "Че надо?"}}]
        answer_inline_query(query_id, results)
        return

    if not is_safe(query_text):
        results = [{"type": "article", "id": "1", "title": "Отказано", "description": "Нельзя", "input_message_content": {"message_text": "Я не помогаю с криминалом."}}]
        answer_inline_query(query_id, results)
        return

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    system_prompt = f"Ты — Serp AI. Отвечай кратко (1-2 предложения), как друг, без длинных текстов. Запрещено: наркотики, оружие, насилие, взлом и расшифровка кодов. Собеседник: {user_name}."
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": query_text}]
    payload = {"model": MODEL, "messages": messages, "temperature": 0.8}
    
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
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
        lines = [f"Пользователей в базе: {len(users)}", f"Заблокировано: {len(banned)}", "", "Последние сохранённые пользователи:"]
        for key, record in list(users.items())[-15:]:
            username = f"@{record['username']}" if record.get("username") else "без username"
            name = " ".join(part for part in [record.get("first_name"), record.get("last_name")] if part) or "Без имени"
            status = " 🚫 БАН" if int(key) in banned else ""
            lines.append(f"• {name} ({username}) — ID {key}{status}")
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
            if not target_chat_id: continue
            result = api_post("sendMessage", {"chat_id": target_chat_id, "text": text})
            if result and result.get("ok"): sent += 1
            else: failed += 1
            time.sleep(0.04)
        send_message(chat_id, f"✅ Рассылка завершена.\nУспешно: {sent}\nОшибок: {failed}")
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

    if text == "/start":
        welcome = (
            "Я Serp AI. 🤖\n\n"
            "Че надо? Задавай вопросы, я помню контекст. "
            "В группах зови по имени (Serp, Серп) или пиши `@имя_бота`.\n\n"
            "Я не обсуждаю незаконные темы. Могу скинуть фотку, если попросишь."
        )
        send_message(chat_id, welcome, reply_to_message_id=message.get("message_id"))
        return
        
    if text == "/reset":
        save_history(user_id, [])
        send_message(chat_id, "🧹 История очищена. Начинаем заново.", reply_to_message_id=message.get("message_id"))
        return

    if text == "/admin":
        if user_id == ADMIN_ID:
            admin_states.pop(user_id, None)
            show_admin_panel(chat_id)
        else:
            send_message(chat_id, "⛔ Нет доступа.")
        return

    if user_id == ADMIN_ID and handle_admin_input(message, user_id, chat_id, text):
        return

    if text.startswith("/"):
        return

    if should_reply(message, bot_username):
        send_chat_action(chat_id, "typing")
        
        clean_text = text.lower().replace("серп", "").replace("serp", "").replace("ai", "").strip()
        if not clean_text:
            clean_text = "Привет"
            
        if any(word in clean_text for word in ["фото", "картинк", "скинь", "пришли", "покажи"]):
            if not PEXAFY_AVAILABLE:
                send_message(chat_id, "Библиотека для картинок не установлена (нет pexafy).", reply_to_message_id=message.get("message_id"))
                return
                
            send_chat_action(chat_id, "upload_photo")
            
            # ИСПОЛЬЗУЕМ НЕЙРОСЕТЬ ДЛЯ ПОНИМАНИЯ СУТИ ЗАПРОСА
            search_query = extract_search_query(clean_text)
            print(f"Поисковый запрос: {search_query}")

            try:
                client = PexafyClient(PEXAFY_API_KEY)
                results = list(client.search(search_query, per_page=1))
                
                if results:
                    photo_url = results[0].urls.large
                    send_photo(chat_id, photo_url, caption="Вот твое фото.", reply_to_message_id=message.get("message_id"))
                    return
                else:
                    fallback_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Capsicum_annuum_seedling.jpg/1200px-Capsicum_annuum_seedling.jpg"
                    send_photo(chat_id, fallback_url, caption="По твоему запросу ничего не нашел. Вот пример.", reply_to_message_id=message.get("message_id"))
                    return
            except Exception as e:
                print(f"Ошибка Pexafy: {e}")
                fallback_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Capsicum_annuum_seedling.jpg/1200px-Capsicum_annuum_seedling.jpg"
                send_photo(chat_id, fallback_url, caption="Ошибка поиска. Вот пример картинки.", reply_to_message_id=message.get("message_id"))
                return

        answer = call_groq_api(clean_text, user_id, user_name)
        send_message(chat_id, answer, reply_to_message_id=message.get("message_id"))

# --- КЛИЕНТ TELETHON ДЛЯ РЕАКЦИЙ (StringSession) ---
telethon_client = None

async def init_telethon():
    global telethon_client
    if API_ID and API_HASH:
        try:
            telethon_client = TelegramClient(StringSession(), API_ID, API_HASH)
            await telethon_client.start(bot_token=TG_TOKEN)
            print("✅ Telethon клиент запущен для реакций.")
        except Exception as e:
            print(f"❌ Ошибка запуска Telethon: {e}")

async def set_reaction(chat_id, message_id, emoji):
    if telethon_client:
        try:
            peer = chat_id
            await telethon_client(SendReactionRequest(peer=peer, msg_id=message_id, reaction=[emoji]))
        except Exception as e:
            print(f"Ошибка реакции: {e}")

def process_update(update, bot_username):
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        message_id = msg["message_id"]
        
        if not should_reply(msg, bot_username):
            return

        if telethon_client:
            try:
                asyncio.run_coroutine_threadsafe(set_reaction(chat_id, message_id, "👀"), telethon_client.loop)
            except Exception: pass

        process_message(msg, bot_username)

        if telethon_client:
            try:
                asyncio.run_coroutine_threadsafe(set_reaction(chat_id, message_id, "🔥"), telethon_client.loop)
            except Exception: pass

def main():
    global telethon_client
    
    Thread(target=run_web_server).start()
    
    if API_ID and API_HASH:
        asyncio.run(init_telethon())
    
    bot_username = get_bot_info()
    print(f"🚀 Бот @{bot_username} запущен. Модель: {MODEL}.")
    offset = 0

    while True:
        try:
            response = requests.get(f"{TG_API_URL}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25)
            data = response.json()
            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    handle_admin_callback(update["callback_query"])
                elif "message" in update:
                    process_update(update, bot_username)
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
