"""База данных (SQLite). Все суммы хранятся целыми числами в микродолларах (1$ = 1 000 000)."""
import asyncio
import time

import aiosqlite

import config

M = 1_000_000


def micro(x) -> int:
    return int(round(float(x) * M))


def usd(m: int) -> str:
    return f"{m / M:.2f}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    cashback INTEGER NOT NULL DEFAULT 0,
    games INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    wagered INTEGER NOT NULL DEFAULT 0,
    won INTEGER NOT NULL DEFAULT 0,
    joined_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS operations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    amount INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ops_user ON operations(user_id, id);
CREATE TABLE IF NOT EXISTS games(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER,
    ts INTEGER NOT NULL,
    game TEXT NOT NULL,
    pick TEXT NOT NULL,
    bet INTEGER NOT NULL,
    payout INTEGER NOT NULL,
    outcome TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_games_user ON games(user_id, id);
CREATE INDEX IF NOT EXISTS ix_games_ts ON games(ts);
CREATE TABLE IF NOT EXISTS chats(
    id INTEGER PRIMARY KEY,
    title TEXT
);
CREATE TABLE IF NOT EXISTS deposits(
    invoice_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL,
    created INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.db: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def init(self):
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()

    # ── пользователи ─────────────────────────────────────────────────────
    async def upsert_user(self, user_id: int, first_name: str, username: str | None):
        async with self.lock:
            await self.db.execute(
                "INSERT INTO users(id, first_name, username, joined_at) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET first_name=excluded.first_name, username=excluded.username",
                (user_id, first_name, username, int(time.time())),
            )
            await self.db.commit()

    async def get_user(self, user_id: int):
        async with self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cur:
            return await cur.fetchone()

    async def upsert_chat(self, chat_id: int, title: str):
        async with self.lock:
            await self.db.execute(
                "INSERT INTO chats(id, title) VALUES(?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title",
                (chat_id, title),
            )
            await self.db.commit()

    async def _op(self, user_id: int, kind: str, amount: int):
        await self.db.execute(
            "INSERT INTO operations(user_id, ts, kind, amount) VALUES(?,?,?,?)",
            (user_id, int(time.time()), kind, amount),
        )

    # ── игры ─────────────────────────────────────────────────────────────
    async def debit_bet(self, user_id: int, bet: int) -> bool:
        """Списывает ставку. False, если не хватает денег."""
        async with self.lock:
            cur = await self.db.execute(
                "UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                (bet, user_id, bet),
            )
            if cur.rowcount == 0:
                await self.db.rollback()
                return False
            await self._op(user_id, "bet", -bet)
            await self.db.commit()
            return True

    async def settle(self, user_id: int, chat_id: int | None, game: str, pick: str,
                     bet: int, payout: int, outcome: str) -> int:
        """Записывает итог игры, начисляет выигрыш и кэшбек. Возвращает новый баланс."""
        cashback_add = int(bet * config.CASHBACK_PERCENT / 100) if outcome == "lose" else 0
        async with self.lock:
            await self.db.execute(
                "UPDATE users SET balance=balance+?, games=games+1, wins=wins+?, "
                "wagered=wagered+?, won=won+?, cashback=cashback+? WHERE id=?",
                (payout, 1 if outcome == "win" else 0, bet,
                 payout if outcome == "win" else 0, cashback_add, user_id),
            )
            await self.db.execute(
                "INSERT INTO games(user_id, chat_id, ts, game, pick, bet, payout, outcome) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (user_id, chat_id, int(time.time()), game, pick, bet, payout, outcome),
            )
            if outcome == "win" and payout > 0:
                await self._op(user_id, "win", payout)
            elif outcome == "push":
                await self._op(user_id, "refund", payout)
            await self.db.commit()
            async with self.db.execute("SELECT balance FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
            return row["balance"]

    async def refund_bet(self, user_id: int, bet: int):
        """Возврат ставки, если игра не состоялась по технической причине."""
        async with self.lock:
            await self.db.execute("UPDATE users SET balance=balance+? WHERE id=?", (bet, user_id))
            await self._op(user_id, "refund", bet)
            await self.db.commit()

    # ── кэшбек ───────────────────────────────────────────────────────────
    async def claim_cashback(self, user_id: int, min_amount: int) -> int:
        async with self.lock:
            async with self.db.execute("SELECT cashback FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
            if not row or row["cashback"] < min_amount:
                return 0
            amount = row["cashback"]
            await self.db.execute(
                "UPDATE users SET balance=balance+?, cashback=0 WHERE id=?", (amount, user_id)
            )
            await self._op(user_id, "cashback", amount)
            await self.db.commit()
            return amount

    # ── пополнения ───────────────────────────────────────────────────────
    async def create_deposit(self, invoice_id: str, user_id: int, amount: int):
        async with self.lock:
            await self.db.execute(
                "INSERT INTO deposits(invoice_id, user_id, amount, status, created) VALUES(?,?,?,?,?)",
                (invoice_id, user_id, amount, "pending", int(time.time())),
            )
            await self.db.commit()

    async def pending_deposits(self):
        async with self.db.execute("SELECT * FROM deposits WHERE status='pending'") as cur:
            return await cur.fetchall()

    async def credit_deposit(self, invoice_id: str):
        """Один раз зачисляет оплаченный счёт. Возвращает (user_id, amount) или None."""
        async with self.lock:
            cur = await self.db.execute(
                "UPDATE deposits SET status='paid' WHERE invoice_id=? AND status='pending'",
                (invoice_id,),
            )
            if cur.rowcount == 0:
                await self.db.rollback()
                return None
            async with self.db.execute(
                "SELECT user_id, amount FROM deposits WHERE invoice_id=?", (invoice_id,)
            ) as c2:
                dep = await c2.fetchone()
            await self.db.execute(
                "UPDATE users SET balance=balance+? WHERE id=?", (dep["amount"], dep["user_id"])
            )
            await self._op(dep["user_id"], "deposit", dep["amount"])
            await self.db.commit()
            return dep["user_id"], dep["amount"]

    async def expire_deposit(self, invoice_id: str):
        async with self.lock:
            await self.db.execute(
                "UPDATE deposits SET status='expired' WHERE invoice_id=? AND status='pending'",
                (invoice_id,),
            )
            await self.db.commit()

    # ── выводы ───────────────────────────────────────────────────────────
    async def debit_withdraw(self, user_id: int, amount: int) -> bool:
        async with self.lock:
            cur = await self.db.execute(
                "UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                (amount, user_id, amount),
            )
            if cur.rowcount == 0:
                await self.db.rollback()
                return False
            await self._op(user_id, "withdraw", -amount)
            await self.db.commit()
            return True

    async def refund_withdraw(self, user_id: int, amount: int):
        async with self.lock:
            await self.db.execute(
                "UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id)
            )
            await self._op(user_id, "withdraw_refund", amount)
            await self.db.commit()

    # ── выборки для экранов ──────────────────────────────────────────────
    async def recent_ops(self, user_id: int, limit: int = 12):
        async with self.db.execute(
            "SELECT ts, kind, amount FROM operations WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return await cur.fetchall()

    async def recent_games(self, user_id: int, limit: int = 10):
        async with self.db.execute(
            "SELECT ts, game, pick, bet, payout, outcome FROM games "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return await cur.fetchall()

    async def top_players(self, since: int, limit: int = 10):
        async with self.db.execute(
            "SELECT u.first_name AS name, SUM(g.bet) AS turnover FROM games g "
            "JOIN users u ON u.id=g.user_id WHERE g.ts>=? "
            "GROUP BY g.user_id ORDER BY turnover DESC LIMIT ?",
            (since, limit),
        ) as cur:
            return await cur.fetchall()

    async def top_chats(self, since: int, limit: int = 10):
        async with self.db.execute(
            "SELECT c.title AS name, SUM(g.bet) AS turnover FROM games g "
            "JOIN chats c ON c.id=g.chat_id WHERE g.ts>=? AND g.chat_id IS NOT NULL "
            "GROUP BY g.chat_id ORDER BY turnover DESC LIMIT ?",
            (since, limit),
        ) as cur:
            return await cur.fetchall()
