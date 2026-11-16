"""Настройки SERP CASINO. Токены вписываешь сам, в архив/чат их больше не кидай."""

# ── Токены ───────────────────────────────────────────────────────────────
BOT_TOKEN = "9146869125:AAFZRu06A2E8RK9w909b-tkPYa7utBppZL0"          # токен бота из @BotFather

# ВОТ ТУТ ТОКЕН xRocket (Pay API token из бота @xRocket)
XROCKET_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBJZCI6IjMwOTgyNCIsImp0aSI6ImFwcDozMDk4MjQ6MjI3NThiMjktNzk0NS00YWFlLThmYzMtZDExMjhhNzZkNjg0IiwiaWF0IjoxNzk0ODE5MzU4fQ.oPcGy5_wVRg5Klk_VJaHnxi4zOcFVLjVzgRHhVz2rxo"

# xRocket: адрес API и способ авторизации.
# Старый (Legacy) API, как в твоём прошлом боте (ссылки вида t.me/xrocket?start=inv_...):
XROCKET_BASE_URL = "https://pay.xrocket.tg"
XROCKET_AUTH_HEADER = "Rocket-Pay-Key"
XROCKET_AUTH_PREFIX = ""
# Если приложение переключено на новый Pay API, поменяй так (и поправь пути в xrocket.py):
# XROCKET_BASE_URL = "https://pay.api.xrocket.exchange"
# XROCKET_AUTH_HEADER = "Authorization"
# XROCKET_AUTH_PREFIX = "Bearer "

# ── Общее ────────────────────────────────────────────────────────────────
BOT_NAME = "SERP CASINO"
SUPPORT_LINK = "none"
DB_PATH = "serp_casino.db"
TZ_OFFSET_HOURS = 3            # время в истории и операциях (Москва)

# ── Лимиты (в $) ─────────────────────────────────────────────────────────
MIN_DEPOSIT = 0.10
MIN_WITHDRAW = 0.50
MIN_BET = 0.10
MAX_BET = 100.0
MIN_CASHBACK_CLAIM = 0.20
CASHBACK_PERCENT = 2           # возврат с каждого проигрыша, %
INVOICE_LIFETIME_MIN = 15      # сколько живёт счёт на пополнение

# ── Внешний вид кнопок ───────────────────────────────────────────────────
# Цвет кнопок (зелёная «Играть», синие «Пополнить/Вывести») и кастомные эмодзи
# на кнопках. Нужна свежая версия aiogram (см. requirements.txt).
# Если Telegram ругается на кнопки, поставь False.
USE_BUTTON_STYLE = True
USE_BUTTON_ICONS = True
