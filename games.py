"""Игры SERP CASINO.

Коэффициенты и условия выигрыша взяты из старого скрипта (C = COEFFICIENT = 1.8).
Кубики, мячи, дартс и слоты бросает сам Telegram (send_dice). Рулетка, монетка и КНБ
используют честный random. Коэффициенты в PICKS показываются игроку на кнопках,
выплата считается по ним же, так что подпись и выплата всегда совпадают.
"""
import asyncio
import random
from dataclasses import dataclass

_rng = random.SystemRandom()

C = 1.8  # базовый коэффициент (раньше COEFFICIENT в config.py)

GAME_ORDER = ["dice", "duel", "coin", "slots",
              "darts", "football", "basket", "bowling", "knb"]

GAME_TITLES = {
    "dice": ("🎲", "Кубик"),
    "duel": ("⚔️", "Дуэль"),
    "coin": ("🪙", "Монетка"),
    "slots": ("🎰", "Слоты"),
    "darts": ("🎯", "Дартс"),
    "football": ("⚽", "Футбол"),
    "basket": ("🏀", "Баскетбол"),
    "bowling": ("🎳", "Боулинг"),
    "knb": ("✊", "КНБ"),
}

# Строки кнопок выбора исхода: (подпись, код, коэффициент). None = особая выплата (слоты).
PICKS = {
    "dice": [
        [("1", "n1", 5), ("2", "n2", 5), ("3", "n3", 5)],
        [("4", "n4", 5), ("5", "n5", 5), ("6", "n6", 5)],
        [("Меньше", "less", C), ("Больше", "more", C)],
        [("Чётное", "even", C), ("Нечётное", "odd", C)],
    ],
    "duel": [
        [("Победа 1", "p1", C), ("Победа 2", "p2", C)],
        [("Ничья", "draw", 3)],
        [("2 меньше", "2less", 2.6), ("2 больше", "2more", 2.6)],
        [("2 чётных", "2even", 2.6), ("2 нечётных", "2odd", 2.6)],
    ],
    "coin": [
        [("Орёл", "heads", C), ("Решка", "tails", C)],
    ],
    "slots": [
        [("Крутить", "spin", None)],
    ],
    "darts": [
        [("Центр", "center", 3)],
        [("Красный", "red", C), ("Белый", "white", C)],
    ],
    "football": [
        [("Гол", "goal", 1.5), ("Промах", "miss", C)],
    ],
    "basket": [
        [("Попал", "hit", C), ("Мимо", "miss", 1.5)],
    ],
    "bowling": [
        [("Страйк", "strike", 2)],
        [("1", "n1", 3), ("2", "n2", 3), ("3", "n3", 3)],
        [("4", "n4", 3), ("5", "n5", 3), ("6", "n6", 3)],
    ],
    "knb": [
        [("Камень", "rock", C), ("Ножницы", "scissors", C), ("Бумага", "paper", C)],
    ],
}

SLOTS_PAYOUT = {1: 7, 22: 7, 43: 7, 16: 5, 32: 5, 48: 5, 64: 10}
SLOTS_NAMES = {7: "Занос", 5: "Куш", 10: "Джекпот"}

DICE_DELAY = {"🎲": 3.5, "🎯": 3.5, "⚽": 4.0, "🏀": 4.5, "🎳": 4.0, "🎰": 2.5}


@dataclass
class Round:
    outcome: str   # "win" | "lose" | "push"
    mult: float    # коэффициент выплаты (для win)
    detail: str    # что выпало


def pick_info(game: str, code: str):
    for row in PICKS[game]:
        for label, c, mult in row:
            if c == code:
                return label, mult
    return code, None


def pick_label(game: str, code: str, number: int | None = None) -> str:
    label, _ = pick_info(game, code)
    if code == "num" and number is not None:
        return f"Число {number}"
    if game in ("dice", "bowling") and code.startswith("n"):
        return f"Число {code[1:]}"
    return label


def mult_text(mult) -> str:
    return "до ×10" if mult is None else f"×{mult:g}"


async def _dice(bot, chat_id: int, emoji: str) -> int:
    msg = await bot.send_dice(chat_id, emoji=emoji)
    await asyncio.sleep(DICE_DELAY[emoji])
    return msg.dice.value


def _win(cond: bool, mult: float, detail: str) -> Round:
    return Round("win" if cond else "lose", mult, detail)


async def play(bot, chat_id: int, game: str, pick: str, number: int | None = None) -> Round:
    _, mult = pick_info(game, pick)

    if game == "dice":
        v = await _dice(bot, chat_id, "🎲")
        if pick.startswith("n"):
            ok = v == int(pick[1:])
        else:
            ok = {"less": v <= 3, "more": v >= 4, "even": v % 2 == 0, "odd": v % 2 == 1}[pick]
        return _win(ok, mult, f"Выпало {v}")

    if game == "duel":
        v1 = await _dice(bot, chat_id, "🎲")
        v2 = await _dice(bot, chat_id, "🎲")
        ok = {
            "p1": v1 > v2, "p2": v2 > v1, "draw": v1 == v2,
            "2less": v1 < 4 and v2 < 4, "2more": v1 > 3 and v2 > 3,
            "2even": v1 % 2 == 0 and v2 % 2 == 0, "2odd": v1 % 2 == 1 and v2 % 2 == 1,
        }[pick]
        return _win(ok, mult, f"Счёт {v1}:{v2}")

    if game == "coin":
        side = _rng.choice(["heads", "tails"])
        name = "орёл" if side == "heads" else "решка"
        return _win(side == pick, mult, f"Выпал {name}" if side == "heads" else f"Выпала {name}")

    if game == "slots":
        v = await _dice(bot, chat_id, "🎰")
        m = SLOTS_PAYOUT.get(v)
        if m:
            return Round("win", m, f"{SLOTS_NAMES[m]}!")
        return Round("lose", 0, "Не повезло")

    if game == "darts":
        v = await _dice(bot, chat_id, "🎯")
        ok = {"center": v == 6, "red": v % 2 == 0, "white": v % 2 == 1}[pick]
        return _win(ok, mult, f"Выпало {v}")

    if game == "football":
        v = await _dice(bot, chat_id, "⚽")
        ok = v in (3, 4, 5) if pick == "goal" else v in (1, 2)
        return _win(ok, mult, f"Выпало {v}")

    if game == "basket":
        v = await _dice(bot, chat_id, "🏀")
        ok = v in (4, 5) if pick == "hit" else v in (1, 2, 3)
        return _win(ok, mult, f"Выпало {v}")

    if game == "bowling":
        v = await _dice(bot, chat_id, "🎳")
        ok = v == 6 if pick == "strike" else v == int(pick[1:])
        return _win(ok, mult, f"Выпало {v}")

    if game == "knb":
        bot_pick = _rng.choice(["rock", "scissors", "paper"])
        icons = {"rock": "✊", "scissors": "✌️", "paper": "✋"}
        detail = f"Вы {icons[pick]} · бот {icons[bot_pick]}"
        if pick == bot_pick:
            return Round("push", 1, detail + " · ничья")
        beats = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        return _win(beats[pick] == bot_pick, mult, detail)

    raise ValueError(f"unknown game {game}")
