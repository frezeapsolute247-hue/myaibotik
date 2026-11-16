"""Тексты экранов, кнопки и кастомные эмодзи SERP CASINO."""
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

import config
import games
from db import M, usd

TZ = timezone(timedelta(hours=config.TZ_OFFSET_HOURS))

# ── ID кастомных эмодзи ──────────────────────────────────────────────────
E_TITLE = "5800849384790828447"     # 🎰 SERP CASINO
E_BALANCE = "5472363448404809929"   # 👛 баланс
E_GAMES = "5938413566624272793"     # 🎮 игры
E_WIN = "5280769763398671636"       # 🏆 выиграно

I_PLAY = "5938413566624272793"
I_DEPOSIT = "5769126056262898415"
I_WITHDRAW = "5902206159095339799"
I_PROFILE = "6035084557378654059"
I_CASHBACK = "5773677501825945508"
I_STATS = "6037475557082403885"
I_XROCKET = "5415897719522744378"


def ce(emoji_id: str, fallback: str) -> str:
    """Кастомный эмодзи в тексте сообщения."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def quote(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"


HEAD = quote(f"{ce(E_TITLE, '🎰')} SERP CASINO")


def head(icon: str, title: str) -> str:
    return quote(f"{icon} {title}")


# ── кнопки ───────────────────────────────────────────────────────────────
def B(text, cb=None, url=None, icon=None, style=None) -> InlineKeyboardButton:
    extra = {}
    if icon and config.USE_BUTTON_ICONS:
        extra["icon_custom_emoji_id"] = icon
    if style and config.USE_BUTTON_STYLE:
        extra["style"] = style  # "primary" (синяя) | "success" (зелёная) | "danger"
    return InlineKeyboardButton(text=text, callback_data=cb, url=url, **extra)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def reply_kb() -> ReplyKeyboardMarkup:
    extra = {"style": "primary"} if config.USE_BUTTON_STYLE else {}
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Меню", **extra), KeyboardButton(text="Играть", **extra),
                   KeyboardButton(text="Баланс", **extra)]],
        resize_keyboard=True, is_persistent=True,
    )


BACK_MENU = kb([B("Меню", "menu")])


def main_kb():
    return kb(
        [B("Играть", "games", icon=I_PLAY, style="success")],
        [B("Пополнить", "deposit", icon=I_DEPOSIT, style="primary"),
         B("Вывести", "withdraw", icon=I_WITHDRAW, style="primary")],
        [B("Профиль", "profile", icon=I_PROFILE), B("Кэшбек", "cashback", icon=I_CASHBACK)],
        [B("Статистика", "stats", icon=I_STATS)],
    )


def games_kb(private: bool = True):
    rows, row = [], []
    for g in games.GAME_ORDER:
        icon, name = games.GAME_TITLES[g]
        row.append(B(f"{icon} {name}", f"g:{g}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if private:
        rows.append([B("Меню", "menu")])
    return kb(*rows)


def picks_kb(game: str):
    rows = []
    for prow in games.PICKS[game]:
        rows.append([B(f"{label} · {games.mult_text(m)}", f"p:{game}:{code}")
                     for label, code, m in prow])
    rows.append([B("Назад", "games")])
    return kb(*rows)


def bet_kb(game: str):
    presets = [0.1, 0.5, 1, 5, 10]
    return kb([B(f"{p:g}$", f"a:{p}") for p in presets], [B("Назад", f"g:{game}")])


def wallet_kb():
    return kb(
        [B("Пополнить", "deposit", icon=I_DEPOSIT, style="primary"),
         B("Вывести", "withdraw", icon=I_WITHDRAW, style="primary")],
        [B("Операции", "ops")],
        [B("Назад", "menu")],
    )


# ── форматирование ───────────────────────────────────────────────────────
def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m %H:%M")


def name_of(u) -> str:
    return f"@{escape(u['username'])}" if u["username"] else escape(u["first_name"] or "игрок")


def signed(a: int) -> str:
    return f"{'+' if a > 0 else '-'}{abs(a) / M:.2f} $"


KIND = {
    "bet": ("🎮", "Ставка"), "win": ("🏆", "Выигрыш"), "cashback": ("🎁", "Кэшбек"),
    "deposit": ("💳", "Пополнение"), "withdraw": ("💸", "Вывод"),
    "withdraw_refund": ("↩️", "Возврат вывода"), "refund": ("↩️", "Возврат ставки"),
}

MEDALS = ["🥇", "🥈", "🥉"]


# ── тексты экранов ───────────────────────────────────────────────────────
def menu_text(u) -> str:
    return (f"{HEAD}\n\nПривет, {name_of(u)} 👋\n\n"
            f"{ce(E_BALANCE, '👛')} Баланс — {usd(u['balance'])} $\n"
            f"{ce(E_GAMES, '🎮')} Игр — {u['games']} · "
            f"{ce(E_WIN, '🏆')} Выиграно — {usd(u['won'])} $")


def games_text(u) -> str:
    return (f"{quote(ce(E_GAMES, '🎮') + ' Игры')}\n\n"
            f"{ce(E_BALANCE, '👛')} Баланс — {usd(u['balance'])} $\n\n"
            f"Выбирай режим 👇")


def wallet_text(u) -> str:
    return (f"{head('👛', 'Кошелёк')}\n\n"
            f"Баланс — {usd(u['balance'])} $\n"
            f"Кэшбек — {usd(u['cashback'])} $")


def profile_text(u) -> str:
    wr = round(u["wins"] / u["games"] * 100) if u["games"] else 0
    joined = datetime.fromtimestamp(u["joined_at"], TZ).strftime("%d.%m.%Y")
    stats = quote(f"🎮 Игр — {u['games']} · винрейт {wr}%\n"
                  f"📈 Оборот — {usd(u['wagered'])} $\n"
                  f"📅 С нами с {joined}")
    return (f"{head('👤', 'Профиль')}\n\n{name_of(u)}\n"
            f"{ce(E_BALANCE, '👛')} Баланс — {usd(u['balance'])} $\n\n{stats}")


def profile_kb():
    return kb(
        [B("История", "history"), B("Операции", "ops")],
        [B("Поддержка", url=config.SUPPORT_LINK)],
        [B("Назад", "menu")],
    )


def history_text(rows) -> str:
    if not rows:
        return f"{head('🕘', 'История игр')}\n\nПока нет игр."
    lines = []
    for r in rows:
        icon, title = games.GAME_TITLES[r["game"]]
        if r["outcome"] == "win":
            res = f"🏆 +{usd(r['payout'])} $"
        elif r["outcome"] == "push":
            res = "↩️ возврат"
        else:
            res = f"❌ -{usd(r['bet'])} $"
        lines.append(f"{fmt_ts(r['ts'])} · {icon} {title} · {usd(r['bet'])} $ → {res}")
    return f"{head('🕘', 'История игр')}\n\n" + quote("\n".join(lines))


def ops_text(rows) -> str:
    if not rows:
        return f"{head('🧾', 'Операции')}\n\nПока нет операций."
    lines = []
    for r in rows:
        icon, title = KIND.get(r["kind"], ("•", r["kind"]))
        lines.append(f"{fmt_ts(r['ts'])} · {icon} {title} · {signed(r['amount'])}")
    return f"{head('🧾', 'Операции')}\n\n" + quote("\n".join(lines))


def cashback_text(u) -> str:
    return (f"{head('🎁', 'Кэшбек')}\n\nНакоплено — {usd(u['cashback'])} $\n\n"
            + quote(f"Возвращаем {config.CASHBACK_PERCENT}% с каждого проигрыша. "
                    f"Вывод на баланс от {config.MIN_CASHBACK_CLAIM:g} $"))


def cashback_kb():
    return kb([B("Забрать на баланс", "cb_claim", icon=I_DEPOSIT, style="success")],
              [B("Назад", "menu")])


def top_text(title: str, rows) -> str:
    if not rows:
        return f"{head('🏆', title)}\n\nПока нет данных."
    lines = []
    for i, r in enumerate(rows):
        mark = MEDALS[i] if i < 3 else f"{i + 1}."
        lines.append(f"{mark} {escape(r['name'] or '—')} — {usd(r['turnover'])} $")
    return f"{head('🏆', title)}\n\n" + "\n".join(lines)
