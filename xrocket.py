"""Клиент xRocket Pay. ВСЕ запросы к xRocket только здесь.

Токен и адрес API берутся из config.py (XROCKET_TOKEN, XROCKET_BASE_URL).
Код написан под Legacy API (pay.xrocket.tg), как в твоём прошлом боте. Если твоё приложение
в @xRocket переключено на новый Pay API, поменяй адрес/заголовок в config.py и поправь
пути и поля в трёх функциях ниже (документация: docs.xrocket.exchange).
"""
import aiohttp

import config


class XRocketError(Exception):
    pass


async def _request(method: str, path: str, json: dict | None = None) -> dict:
    headers = {config.XROCKET_AUTH_HEADER: config.XROCKET_AUTH_PREFIX + config.XROCKET_TOKEN}
    url = config.XROCKET_BASE_URL.rstrip("/") + path
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, url, json=json, headers=headers) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400 or (isinstance(data, dict) and data.get("success") is False):
                raise XRocketError(f"{resp.status}: {data}")
            return data


async def create_invoice(amount: float, description: str, payload: str) -> tuple[str, str]:
    """Счёт на пополнение. Возвращает (id счёта, ссылка на оплату)."""
    data = await _request("POST", "/tg-invoices", {
        "amount": amount,
        "numPayments": 1,
        "currency": "USDT",
        "description": description,
        "expiredIn": config.INVOICE_LIFETIME_MIN * 60,
        "payload": payload,
    })
    inv = data["data"]
    return str(inv["id"]), inv["link"]


async def invoice_status(invoice_id: str) -> str:
    """'active' | 'paid' | 'expired'"""
    data = await _request("GET", f"/tg-invoices/{invoice_id}")
    return data["data"]["status"]


async def create_cheque(tg_user_id: int, amount: float, description: str) -> str:
    """Личный чек на 1 активацию для игрока (вывод). Возвращает ссылку на чек."""
    data = await _request("POST", "/multi-cheques", {
        "currency": "USDT",
        "chequePerUser": amount,
        "usersNumber": 1,
        "refProgram": 0,
        "description": description,
        "userId": tg_user_id,
    })
    return data["data"]["link"]
