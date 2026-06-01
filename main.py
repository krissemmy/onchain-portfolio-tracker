import asyncio
import base64
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Body

from utils.prices import format_signed_percent
import re
from base58 import b58decode
# Load env vars
load_dotenv()

ZERION_API_KEY = os.getenv("ZERION_API_KEY")

if not ZERION_API_KEY:
    raise RuntimeError("FATAL ERROR: ZERION_API_KEY is not set in environment (.env)")

app = FastAPI()

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
ZERION_API_BASE = "https://api.zerion.io/v1"

CHAIN_LABELS = {
    "abstract": "Abstract",
    "arbitrum": "Arbitrum",
    "avalanche": "Avalanche",
    "base": "Base",
    "binance-smart-chain": "BNB Chain",
    "blast": "Blast",
    "ethereum": "Ethereum",
    "linea": "Linea",
    "optimism": "Optimism",
    "polygon": "Polygon",
    "scroll": "Scroll",
    "solana": "Solana",
    "svm": "Solana",
    "zksync-era": "zkSync Era",
}

# ---------- Helpers ----------


def detect_chain_type(address: str) -> str:
    """
    Returns: 'evm', 'svm', or 'unknown'
    """

    addr = address.strip()

    # EVM
    if EVM_RE.match(addr):
        return "evm"

    # SVM pattern → verify base58 decoding
    if BASE58_RE.match(addr):
        try:
            decoded = b58decode(addr)
            if len(decoded) in (32, 64):  # Solana address / PDA
                return "svm"
        except Exception:
            pass

    return "unknown"


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


def get_chain_label(token: Dict[str, Any]) -> str:
    """
    Get Chain Name
    """
    chain_name = token.get("chain")

    # If we have a string like "base", "ethereum"
    if isinstance(chain_name, str) and not str(chain_name).isdigit():
        return CHAIN_LABELS.get(
            chain_name,
            chain_name.replace("_", " ").replace("-", " ").title(),
        )
    else:
        return "Unknown chain"

def format_signed_currency(value: Optional[float]) -> Optional[str]:
    """
    Format a signed USD amount like '+$123.45' or '-$12.34'.
    """
    if value is None:
        return None
    base = format_usd(abs(value)) or "$0.00"
    if value == 0:
        return base
    sign = "+" if value > 0 else "-"
    return f"{sign}{base}"


# ---------- Zerion API calls for a single wallet ----------

def zerion_headers() -> Dict[str, str]:
    token = base64.b64encode(f"{ZERION_API_KEY}:".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
    }


async def zerion_get(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[Dict[str, Any]],
    label: str,
) -> Optional[httpx.Response]:
    for attempt in range(3):
        resp = await client.get(url, headers=zerion_headers(), params=params)
        if resp.status_code != 429:
            return resp
        if attempt < 2:
            await asyncio.sleep(1.2 * (attempt + 1))

    print(
        f"Zerion {label} API failed {resp.status_code}: "
        f"{resp.reason_phrase} {resp.text}"
    )
    return None


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def extract_address(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None

    attrs = value.get("attributes") or {}
    return (
        value.get("address")
        or value.get("id")
        or attrs.get("address")
        or attrs.get("hash")
    )


def quantity_to_float(quantity: Any) -> Optional[float]:
    if not isinstance(quantity, dict):
        return None

    numeric = first_present(
        quantity.get("float"),
        quantity.get("numeric"),
        quantity.get("value"),
    )
    if numeric is not None:
        d_numeric = safe_decimal(numeric)
        if d_numeric is not None:
            return float(d_numeric)

    integer_raw = first_present(quantity.get("int"), quantity.get("integer"))
    decimals_raw = quantity.get("decimals")
    d_integer = safe_decimal(integer_raw)
    if d_integer is None or decimals_raw is None:
        return None

    try:
        decimals = int(decimals_raw)
        return float(d_integer / (Decimal(10) ** decimals))
    except Exception:
        return None


def clean_symbol(symbol: Optional[str]) -> str:
    if not symbol:
        return ""
    symbol = symbol.replace("$", "")
    for sep in [" ", "-", "["]:
        symbol = symbol.split(sep)[0]
    return symbol[:12]


def zerion_chain_from_item(item: Dict[str, Any]) -> str:
    relationships = item.get("relationships") or {}
    chain_data = (relationships.get("chain") or {}).get("data") or {}
    chain_id = chain_data.get("id")
    if isinstance(chain_id, str) and chain_id:
        return chain_id

    attrs = item.get("attributes") or {}
    chain = attrs.get("chain") or attrs.get("chain_id")
    if isinstance(chain, str) and chain:
        return chain

    return "unknown"


def normalize_zerion_position(position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    attrs = position.get("attributes") or {}
    fungible_info = attrs.get("fungible_info") or {}

    symbol = clean_symbol(fungible_info.get("symbol") or attrs.get("symbol"))
    name = fungible_info.get("name") or attrs.get("name") or symbol or "Token"

    if symbol == "RTFKT":
        return None

    chain = zerion_chain_from_item(position)
    implementations = fungible_info.get("implementations") or []
    implementation = None
    for candidate in implementations:
        if candidate.get("chain_id") == chain:
            implementation = candidate
            break
    if implementation is None and implementations:
        implementation = implementations[0]
    implementation = implementation or {}

    contract_address = (
        implementation.get("address")
        or fungible_info.get("id")
        or position.get("id")
    )
    if not contract_address:
        contract_address = f"{chain}:{symbol or name}"

    quantity = attrs.get("quantity") or {}
    amount_numeric = quantity_to_float(quantity)

    value_usd = None
    d_value = safe_decimal(attrs.get("value"))
    if d_value is not None:
        value_usd = float(d_value)
    if value_usd is None or value_usd <= 0:
        return None

    price = None
    d_price = safe_decimal(attrs.get("price"))
    if d_price is not None:
        price = float(d_price)

    changes = attrs.get("changes") or {}
    change_24h = first_present(
        changes.get("percent_1d"),
        changes.get("relative_1d"),
        changes.get("percent_24h"),
        changes.get("relative_24h"),
    )
    d_change_24h = safe_decimal(change_24h)
    change_24h_float = float(d_change_24h) if d_change_24h is not None else None

    change_24h_usd = first_present(
        changes.get("absolute_1d"),
        changes.get("value_1d"),
        changes.get("absolute_24h"),
        changes.get("value_24h"),
    )
    d_change_24h_usd = safe_decimal(change_24h_usd)
    change_24h_usd_float = (
        float(d_change_24h_usd) if d_change_24h_usd is not None else None
    )

    icon = fungible_info.get("icon") or {}
    logo = icon.get("url") if isinstance(icon, dict) else None
    external_links = fungible_info.get("external_links") or {}
    url = external_links.get("homepage") or external_links.get("website")

    token_metadata = {
        "name": name,
        "symbol": symbol,
        "logo": logo,
        "url": url,
        "price_usd": price,
    }

    show_badge = change_24h_float is not None
    badge_class = "badge-up" if (change_24h_float or 0) >= 0 else "badge-down"
    badge_label = (
        format_signed_percent(change_24h_float)
        if change_24h_float is not None
        else None
    )

    return {
        "id": position.get("id"),
        "chain": chain,
        "chain_id": chain,
        "contract_address": contract_address,
        "asset_type": attrs.get("position_type") or attrs.get("type") or "token",
        "name": name,
        "symbol": symbol,
        "decimals": quantity.get("decimals"),
        "amount": quantity.get("int") or quantity.get("numeric"),
        "price_usd": price,
        "value_usd": value_usd or 0.0,
        "token_metadata": token_metadata,
        "valueUSDFormatted": format_usd(value_usd),
        "amountFormatted": (
            format_amount_short(amount_numeric) if amount_numeric is not None else None
        ),
        "change24h": change_24h_float,
        "change24hUSDNumeric": change_24h_usd_float,
        "change24hBadgeClass": badge_class if show_badge else None,
        "change24hBadgeLabel": badge_label if show_badge else None,
        "chain_label": CHAIN_LABELS.get(chain, chain.replace("-", " ").title()),
        "amountNumeric": amount_numeric if amount_numeric is not None else 0.0,
        "valueUSDNumeric": value_usd if value_usd is not None else 0.0,
    }

async def get_wallet_balances(
    wallet_address: str,
    include_historical_prices: bool = False
) -> List[Dict[str, Any]]:
    if not wallet_address:
        return []

    url = f"{ZERION_API_BASE}/wallets/{wallet_address}/positions/"
    params = {
        "currency": "usd",
        "filter[positions]": "only_simple",
        "filter[trash]": "only_non_trash",
        "sort": "-value",
        "page[size]": 100,
    }
    if include_historical_prices:
        params["filter[changes]"] = "1d"

    positions: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            while url:
                resp = await zerion_get(client, url, params, "positions")
                params = None
                if resp is None:
                    return []
                if resp.status_code != 200:
                    body = resp.text
                    print(
                        f"Zerion positions API failed {resp.status_code}: "
                        f"{resp.reason_phrase} {body}"
                    )
                    return []

                data = resp.json()
                positions.extend(data.get("data", []) or [])
                links = data.get("links") or {}
                url = links.get("next")
                if len(positions) >= 500:
                    break
        except Exception as e:
            print("Error fetching wallet balances:", e)
            return []

    enriched: List[Dict[str, Any]] = []
    for position in positions:
        token = normalize_zerion_position(position)
        if token is not None:
            enriched.append(token)

    return enriched


async def get_svm_balances(wallet_address: str) -> List[Dict[str, Any]]:
    return await get_wallet_balances(wallet_address, include_historical_prices=False)


def select_primary_transfer(
    transfers: List[Dict[str, Any]],
    wallet_address: str,
) -> Optional[Dict[str, Any]]:
    if not transfers:
        return None

    wallet_lower = wallet_address.lower()

    def score(transfer: Dict[str, Any]) -> int:
        fungible_info = transfer.get("fungible_info") or {}
        symbol = fungible_info.get("symbol")
        value = safe_decimal(transfer.get("value"))
        sender = extract_address(transfer.get("sender"))
        recipient = extract_address(transfer.get("recipient"))
        direction_score = 1 if (
            (sender and sender.lower() == wallet_lower)
            or (recipient and recipient.lower() == wallet_lower)
        ) else 0
        value_score = 1 if value is not None and value > 0 else 0
        symbol_score = 1 if symbol else 0
        return direction_score + value_score + symbol_score

    return max(transfers, key=score)


def normalize_transfer_direction(
    transfer: Dict[str, Any],
    wallet_address: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    raw_direction = str(
        transfer.get("direction")
        or transfer.get("type")
        or transfer.get("effect")
        or ""
    ).lower()

    sender = extract_address(transfer.get("sender"))
    recipient = extract_address(transfer.get("recipient"))
    wallet_lower = wallet_address.lower()

    if raw_direction in ("in", "incoming", "receive", "received"):
        return "receive", "From", sender
    if raw_direction in ("out", "outgoing", "send", "sent"):
        return "send", "To", recipient

    if recipient and recipient.lower() == wallet_lower:
        return "receive", "From", sender
    if sender and sender.lower() == wallet_lower:
        return "send", "To", recipient

    return "call", "With", recipient or sender


def normalize_zerion_transaction(
    tx: Dict[str, Any],
    wallet_address: str,
) -> Dict[str, Any]:
    attrs = tx.get("attributes") or {}
    operation_type = attrs.get("operation_type") or attrs.get("type") or "call"
    transfers = attrs.get("transfers") or []
    primary_transfer = select_primary_transfer(transfers, wallet_address)

    t = "call"
    party_label = "With"
    party_address = None
    amount_display = None
    symbol_display = None
    direction_prefix = ""

    if primary_transfer:
        t, party_label, party_address = normalize_transfer_direction(
            primary_transfer,
            wallet_address,
        )

        fungible_info = primary_transfer.get("fungible_info") or {}
        symbol_display = clean_symbol(fungible_info.get("symbol"))
        amount_numeric = quantity_to_float(primary_transfer.get("quantity") or {})
        if amount_numeric is not None:
            if 0 < abs(amount_numeric) < 0.0001:
                amount_display = "<0.0001"
            else:
                amount_display = f"{amount_numeric:.6f}".rstrip("0").rstrip(".")

            if abs(amount_numeric) > 1e12 or len(amount_display) > 12:
                amount_display = f"{amount_numeric:.2e}"

        if t == "receive":
            direction_prefix = "+"
        elif t == "send":
            direction_prefix = "-"

    activity_title = str(operation_type).replace("_", " ").title()
    if primary_transfer and t in ("receive", "send"):
        verb = "Received" if t == "receive" else "Sent"
        activity_title = f"{verb} {symbol_display or 'Token'}"

    party_address_short = None
    if party_address:
        party_address_short = f"{party_address[:6]}...{party_address[-4:]}"

    block_time = (
        attrs.get("mined_at")
        or attrs.get("block_time")
        or attrs.get("created_at")
    )
    block_time_display = None
    if isinstance(block_time, str):
        try:
            dt = datetime.fromisoformat(block_time.replace("Z", "+00:00"))
            block_time_display = dt.strftime("%Y-%m-%d")
        except Exception:
            block_time_display = block_time

    transaction_hash = (
        attrs.get("hash")
        or attrs.get("transaction_hash")
        or tx.get("id")
    )

    return {
        "id": tx.get("id"),
        "type": t,
        "hash": transaction_hash,
        "block_time": block_time,
        "activityTitle": activity_title,
        "activityColorClass": t,
        "partyLabel": party_label,
        "partyAddressShort": party_address_short,
        "blockTimeDisplay": block_time_display,
        "amountDisplay": amount_display,
        "symbolDisplay": symbol_display,
        "directionPrefix": direction_prefix,
    }


async def get_wallet_activity(wallet_address: str, limit: int = 25) -> List[Dict[str, Any]]:
    if not wallet_address:
        return []

    url = f"{ZERION_API_BASE}/wallets/{wallet_address}/transactions/"
    params = {
        "currency": "usd",
        "page[size]": limit,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await zerion_get(client, url, params, "transactions")
            if resp is None:
                return []
            if resp.status_code != 200:
                body = resp.text
                print(
                    f"Zerion transactions API failed {resp.status_code}: "
                    f"{resp.reason_phrase} {body}"
                )
                return []
            data = resp.json()
        except Exception as e:
            print("Error fetching wallet activity:", e)
            return []

    raw_activities = data.get("data", []) or []
    normalized = [
        normalize_zerion_transaction(activity, wallet_address)
        for activity in raw_activities
    ]

    return normalized


# ---------- Aggregation across multiple wallets ----------

def token_key(token: Dict[str, Any]) -> Tuple[Any, Any, Any, Any]:
    """
    Key to identify 'same token' across wallets.
    Uses chain + contract + asset_type + symbol.
    """
    return (
        token.get("chain_id"),
        token.get("contract_address"),
        token.get("asset_type"),
        token.get("symbol"),
    )

def token_matches_filter(token: Dict[str, Any], token_filter: Optional[str]) -> bool:
    """
    Case-insensitive match against contract address / mint / name / symbol.
    If token_filter is empty/None, always returns True.
    """
    if not token_filter:
        return True

    f = token_filter.strip().lower()
    if not f:
        return True

    tm = token.get("token_metadata") or {}

    candidates = [
        token.get("contract_address"),
        token.get("address"),
        token.get("mint"),
        tm.get("address"),
        token.get("symbol"),
        token.get("name"),
    ]

    for v in candidates:
        if not v:
            continue
        if f in str(v).lower():
            return True

    return False


async def get_portfolio(
    wallets: List[str],
    include_historical_prices: bool,
    include_activities: bool,
    token_filter: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, float]:
    portfolio_tokens: Dict[Tuple[Any, Any, Any, Any], Dict[str, Any]] = {}
    all_activities: List[Dict[str, Any]] = []

    for addr in wallets:
        chain_type = detect_chain_type(addr)
        # EVM Address
        if chain_type == "evm":
            tokens = await get_wallet_balances(addr, include_historical_prices)
            activities = await get_wallet_activity(addr, 25) if include_activities else []
        # SVM Address
        elif chain_type == "svm":
            tokens = await get_svm_balances(addr)
            activities = await get_wallet_activity(addr, 25) if include_activities else []

        else:
            # unknown or invalid address
            tokens = []
            activities = []

        for t in tokens:
            key = token_key(t)
            amount_num = float(t.get("amountNumeric") or 0.0)
            value_num = float(t.get("valueUSDNumeric") or 0.0)
            change_24h_usd_num = t.get("change24hUSDNumeric")

            existing = portfolio_tokens.get(key)
            if existing is None:
                new_tok = dict(t)
                new_tok["amountNumeric"] = amount_num
                new_tok["valueUSDNumeric"] = value_num
                new_tok["source_wallets"] = [addr]
                portfolio_tokens[key] = new_tok
            else:
                existing["amountNumeric"] += amount_num
                existing["valueUSDNumeric"] += value_num
                if change_24h_usd_num is not None:
                    existing["change24hUSDNumeric"] = float(
                        existing.get("change24hUSDNumeric") or 0.0
                    ) + float(change_24h_usd_num)
                if addr not in existing["source_wallets"]:
                    existing["source_wallets"].append(addr)

        for a in activities:
            a = dict(a)
            a["source_wallet"] = addr
            all_activities.append(a)

    aggregated_tokens: List[Dict[str, Any]] = []
    total_value = 0.0
    total_pnl_24h = 0.0

    for t in portfolio_tokens.values():
        # Apply token filter (by contract / mint / name / symbol), case-insensitive
        if not token_matches_filter(t, token_filter):
            continue

        value_num = float(t.get("valueUSDNumeric", 0.0))
        amount_num = float(t.get("amountNumeric", 0.0))

        t["value_usd"] = value_num
        t["valueUSDFormatted"] = format_usd(value_num)
        t["amountFormatted"] = format_amount_short(amount_num)
        # make sure chain label is set for EVM + SVM
        t["chain_label"] = get_chain_label(t)

        aggregated_tokens.append(t)
        total_value += value_num

        change_usd = t.get("change24hUSDNumeric")
        if change_usd is not None:
            try:
                total_pnl_24h += float(change_usd)
            except Exception:
                pass
        else:
            change_pct = t.get("change24h")
            if change_pct is not None:
                try:
                    total_pnl_24h += value_num * (float(change_pct) / 100.0)
                except Exception:
                    pass

    aggregated_tokens.sort(key=lambda x: x.get("valueUSDNumeric", 0.0), reverse=True)
    all_activities.sort(key=lambda x: x.get("block_time") or "", reverse=True)

    return aggregated_tokens, all_activities, total_value, total_pnl_24h




# ---------- Route ----------

@app.post("/api/portfolio")
async def api_portfolio(payload: dict = Body(...)):
    """
    JSON API: given a list of wallet addresses and a tab ('tokens' or 'activity'),
    return aggregated portfolio data.
    """
    wallets_raw = payload.get("walletAddresses") or []
    tab = payload.get("tab") or "tokens"
    token_filter = payload.get("tokenFilter") or None


    # clean + dedupe
    wallets = []
    seen = set()
    for w in wallets_raw:
        if not w:
            continue
        w = str(w).strip()
        if not w:
            continue
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            wallets.append(w)

    if not wallets:
        return {
            "walletAddresses": [],
            "currentTab": tab,
            "totalWalletUSDValue": format_usd(0.0),
            "totalPnLUSD": 0.0,
            "totalPnLUSDFormatted": None,
            "totalPnLClass": "pnl-neutral",
            "tokens": [],
            "activities": [],
        }

    try:
        tokens, activities, total_value_num, total_pnl_num = await get_portfolio(
            wallets,
            include_historical_prices=(tab == "tokens"),
            include_activities=(tab == "activity"),
            token_filter=token_filter,
        )
    except Exception as e:
        print("Error in /api/portfolio:", e)
        return {
            "walletAddresses": wallets,
            "currentTab": tab,
            "totalWalletUSDValue": format_usd(0.0),
            "totalPnLUSD": 0.0,
            "totalPnLUSDFormatted": None,
            "totalPnLClass": "pnl-neutral",
            "tokens": [],
            "activities": [],
            "error": "Failed to fetch wallet data. Please try again.",
        }

    total_wallet_usd_value = format_usd(total_value_num)
    total_pnl_usd_formatted = format_signed_currency(total_pnl_num)

    total_pnl_class = "pnl-neutral"
    if total_pnl_num != 0:
        total_pnl_class = "pnl-up" if total_pnl_num > 0 else "pnl-down"

    return {
        "walletAddresses": wallets,
        "currentTab": tab,
        "tokenFilter": token_filter,        
        "totalWalletUSDValue": total_wallet_usd_value,
        "totalPnLUSD": total_pnl_num,
        "totalPnLUSDFormatted": total_pnl_usd_formatted,
        "totalPnLClass": total_pnl_class,
        "tokens": tokens,
        "activities": activities,
    }


@app.get("/", response_class=HTMLResponse)
async def wallet_view(request: Request):
    context = {
        "request": request,
        "walletAddresses": [],
        "currentTab": "tokens",
        "totalWalletUSDValue": None,
        "totalPnLUSD": None,
        "totalPnLUSDFormatted": None,
        "totalPnLClass": "pnl-neutral",
        "tokens": [],
        "activities": [],
    }
    return templates.TemplateResponse("wallet.html", context)
