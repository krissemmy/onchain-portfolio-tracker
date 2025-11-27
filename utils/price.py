# utils/prices.py

from typing import Optional, Any


def pct(curr: Optional[float], past: Optional[float]) -> Optional[float]:
    if curr is None or past is None or past == 0:
        return None
    return (curr - past) / past * 100.0


def price_at(hist: Any, h: int) -> Optional[float]:
    if not isinstance(hist, list):
        return None
    for p in hist:
        if p and p.get("offset_hours") == h:
            return p.get("price_usd")
    return None


def change1h(price: Optional[float], hist: Any) -> Optional[float]:
    return pct(price, price_at(hist, 1))


def change6h(price: Optional[float], hist: Any) -> Optional[float]:
    return pct(price, price_at(hist, 6))


def change24h(price: Optional[float], hist: Any) -> Optional[float]:
    return pct(price, price_at(hist, 24))


def format_signed_percent(x: Optional[float]) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.2f}%"
