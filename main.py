# main.py
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from utils.prices import change1h, change6h, change24h, format_signed_percent

# Load env vars
load_dotenv()

SIM_API_KEY = os.getenv("SIM_API_KEY")

if not SIM_API_KEY:
    raise RuntimeError("FATAL ERROR: SIM_API_KEY is not set in environment (.env)")

app = FastAPI()

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- Helpers ----------

def format_usd(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"${value:,.2f}"


def format_amount_short(amount: Optional[float]) -> Optional[str]:
    """Simple numbro-like formatting: 1234 -> '1.23K', 1_000_000 -> '1.00M'."""
    if amount is None:
        return None
    n = float(amount)
    abs_n = abs(n)
    suffix = ""
    div = 1.0

    if abs_n >= 1_000_000_000:
        suffix = "B"
        div = 1_000_000_000
    elif abs_n >= 1_000_000:
        suffix = "M"
        div = 1_000_000
    elif abs_n >= 1_000:
        suffix = "K"
        div = 1_000

    base = n / div
    if abs(base) >= 100:
        s = f"{base:,.0f}"
    else:
        s = f"{base:,.2f}"
    return f"{s}{suffix}"


def safe_decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ---------- SIM API calls ----------

async def get_wallet_balances(
    wallet_address: str,
    include_historical_prices: bool = False
) -> List[Dict[str, Any]]:
    if not wallet_address:
        return []

    query_parts = [
        "metadata=url,logo",
        "exclude_spam_tokens",
    ]
    if include_historical_prices:
        query_parts.append("historical_prices=1,6,24")

    url = (
        f"https://api.sim.dune.com/v1/evm/balances/"
        f"{wallet_address}?{'&'.join(query_parts)}"
    )

    headers = {
        "X-Sim-Api-Key": SIM_API_KEY,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                body = resp.text
                print(f"Balances API failed {resp.status_code}: {resp.reason_phrase} {body}")
                return []

            data = resp.json()
        except Exception as e:
            print("Error fetching wallet balances:", e)
            return []

    balances = data.get("balances", []) or []
    enriched: List[Dict[str, Any]] = []

    for token in balances:
        # decimals and amount
        decimals_raw = token.get("decimals")
        amount_raw = token.get("amount")

        decimals = None
        amount_numeric = None
        try:
            if decimals_raw is not None:
                decimals = int(decimals_raw)
            if amount_raw is not None and decimals is not None and decimals >= 0:
                amount_int = safe_decimal(amount_raw)
                if amount_int is not None:
                    amount_numeric = float(amount_int / (Decimal(10) ** decimals))
        except Exception:
            amount_numeric = None

        # USD value
        value_usd_raw = token.get("value_usd")
        value_usd = None
        d_value = safe_decimal(value_usd_raw)
        if d_value is not None:
            value_usd = float(d_value)

        value_usd_formatted = format_usd(value_usd)
        amount_formatted = (
            format_amount_short(amount_numeric) if amount_numeric is not None else None
        )

        # 24h change badge
        price = None
        hist = None

        price_usd = token.get("price_usd")
        token_metadata = token.get("token_metadata") or {}
        if isinstance(price_usd, (int, float)):
            price = float(price_usd)
        elif isinstance(token_metadata.get("price_usd"), (int, float)):
            price = float(token_metadata["price_usd"])

        hist = token.get("historical_prices") or token_metadata.get("historical_prices")

        d24 = change24h(price, hist) if price is not None else None
        low_liquidity = bool(token.get("low_liquidity"))

        show_badge = d24 is not None and not low_liquidity
        badge_class = "badge-up" if (d24 or 0) >= 0 else "badge-down"
        badge_label = format_signed_percent(d24) if d24 is not None else None

        # Filter out RTFKT like original
        if token.get("symbol") == "RTFKT":
            continue

        enriched.append(
            {
                **token,
                "valueUSDFormatted": value_usd_formatted,
                "amountFormatted": amount_formatted,
                "change24h": d24,
                "change24hBadgeClass": badge_class if show_badge else None,
                "change24hBadgeLabel": badge_label if show_badge else None,
            }
        )

    return enriched


async def get_wallet_activity(wallet_address: str, limit: int = 25) -> List[Dict[str, Any]]:
    if not wallet_address:
        return []

    url = f"https://api.sim.dune.com/v1/evm/activity/{wallet_address}?limit={limit}"
    headers = {
        "X-Sim-Api-Key": SIM_API_KEY,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                body = resp.text
                print(f"Activity API failed {resp.status_code}: {resp.reason_phrase} {body}")
                return []
            data = resp.json()
        except Exception as e:
            print("Error fetching wallet activity:", e)
            return []

    raw_activities = data.get("activity", []) or []
    normalized: List[Dict[str, Any]] = []

    for a in raw_activities:
        t = a.get("type", "")
        token_md = a.get("token_metadata") or {}
        asset_type = a.get("asset_type")
        chain_id = a.get("chain_id")

        # Title and color class
        activity_title = t.capitalize()
        activity_color_class = t

        if t == "call" and a.get("function") and a["function"].get("name"):
            activity_title = f"Call: {a['function']['name']}"
            activity_color_class = "call"
        elif t in ("receive", "send"):
            symbol = token_md.get("symbol")
            if not symbol:
                if asset_type == "native":
                    if chain_id in (1, 8453, 10):
                        symbol = "ETH"
                    else:
                        symbol = "Native"
                else:
                    symbol = "Token"
            activity_title = ("Received " if t == "receive" else "Sent ") + symbol

        # party label / address
        if t == "receive":
            party_label = "From"
            party_address = a.get("from")
        elif t == "send":
            party_label = "To"
            party_address = a.get("to")
        elif t == "call":
            party_label = "Contract"
            party_address = a.get("to")
        else:
            party_label = "With"
            party_address = a.get("to") or a.get("from") or "Unknown"

        if party_address and party_address != "Unknown":
            short_addr = f"{party_address[:6]}...{party_address[-4:]}"
        else:
            short_addr = None

        # timestamp display
        block_time = a.get("block_time")
        block_time_display = None
        if isinstance(block_time, str):
            try:
                dt = datetime.fromisoformat(block_time.replace("Z", "+00:00"))
                block_time_display = dt.strftime("%Y-%m-%d")
            except Exception:
                block_time_display = block_time

        # amount & symbol (numeric)
        amount_display = None
        symbol_display = None
        direction_prefix = ""

        value_raw = a.get("value")
        if value_raw is not None:
            decimals = token_md.get("decimals")
            if decimals is None:
                decimals = 18
            try:
                decimals = int(decimals)
            except Exception:
                decimals = 18

            val = safe_decimal(value_raw)
            if val is not None:
                scaled = float(val / (Decimal(10) ** decimals))

                # small-value handling
                if 0 < abs(scaled) < 0.0001:
                    amount_display = "<0.0001"
                else:
                    amount_display = f"{scaled:.6f}".rstrip("0").rstrip(".")

                # large-value handling
                if abs(scaled) > 1e12 or len(amount_display) > 12:
                    amount_display = f"{scaled:.2e}"

                symbol = token_md.get("symbol")
                if not symbol:
                    if asset_type == "native":
                        if chain_id in (1, 8453, 10):
                            symbol = "ETH"
                        else:
                            symbol = "NTV"
                    else:
                        symbol = "Tokens"

                symbol = symbol.replace("$", "")
                for sep in [" ", "-", "["]:
                    symbol = symbol.split(sep)[0]
                symbol = symbol[:8]

                symbol_display = symbol

                if t == "receive":
                    direction_prefix = "+"
                elif t == "send":
                    direction_prefix = "-"

        normalized.append(
            {
                **a,
                "activityTitle": activity_title,
                "activityColorClass": activity_color_class,
                "partyLabel": party_label,
                "partyAddressShort": short_addr,
                "blockTimeDisplay": block_time_display,
                "amountDisplay": amount_display,
                "symbolDisplay": symbol_display,
                "directionPrefix": direction_prefix,
            }
        )

    return normalized


# ---------- Route ----------

@app.get("/", response_class=HTMLResponse)
async def wallet_view(
    request: Request,
    walletAddress: Optional[str] = None,
    tab: str = "tokens",
):
    tokens: List[Dict[str, Any]] = []
    activities: List[Dict[str, Any]] = []
    total_wallet_usd_value_num: float = 0.0
    error_message: Optional[str] = None

    if walletAddress:
        try:
            tokens = await get_wallet_balances(
                walletAddress,
                include_historical_prices=(tab == "tokens"),
            )
            activities = await get_wallet_activity(walletAddress, 25)

            for tkn in tokens:
                v_raw = tkn.get("value_usd")
                d_val = safe_decimal(v_raw)
                if d_val is not None:
                    total_wallet_usd_value_num += float(d_val)

        except Exception as e:
            print("Error in route handler:", e)
            error_message = "Failed to fetch wallet data. Please try again."

    total_wallet_usd_value = format_usd(total_wallet_usd_value_num)

    context = {
        "request": request,
        "walletAddress": walletAddress,
        "currentTab": tab,
        "totalWalletUSDValue": total_wallet_usd_value,
        "tokens": tokens,
        "activities": activities,
        "errorMessage": error_message,
        "change1h": change1h,
        "change6h": change6h,
        "change24h": change24h,
        "formatSignedPercent": format_signed_percent,
        "helpers": {
            "change1h": change1h,
            "change6h": change6h,
            "change24h": change24h,
            "formatSignedPercent": format_signed_percent,
        },
    }

    return templates.TemplateResponse("wallet.html", context)
