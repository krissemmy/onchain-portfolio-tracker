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

from utils.prices import change1h, change6h, change24h, format_signed_percent
from typing import Any, Dict, List, Optional
import re
from base58 import b58decode
# Load env vars
load_dotenv()

SIM_API_KEY = os.getenv("SIM_API_KEY")

if not SIM_API_KEY:
    raise RuntimeError("FATAL ERROR: SIM_API_KEY is not set in environment (.env)")

app = FastAPI()

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -------- Portfolio content (static) --------
# TODO: Verify descriptions against upstream READMEs when network access is available.

CONTACTS = [
    {
        "name": "Twitter",
        "handle": "@krissemmy",
        "url": "https://twitter.com/krissemmy",
        "group": "primary",
    },
    {
        "name": "GitHub",
        "handle": "krissemmy",
        "url": "https://github.com/krissemmy",
        "group": "primary",
    },
    {
        "name": "LinkedIn",
        "handle": "@krissemmy",
        "url": "https://www.linkedin.com/in/krissemmy/",
        "group": "primary",
    },
    {
        "name": "Email",
        "handle": "krissemmy@gmail.com",
        "url": "mailto:krissemmy@gmail.com",
        "group": "secondary",
    },
]

PROJECTS = [
    {
        "title": "KraiNode",
        "repo_url": "https://github.com/krissemmy/krainode-rpc-proxy",
        "live_url": "https://krainode.krissemmy.com/",
        "description": (
            "Self-hosted RPC proxy that provides managed RPC endpoints with rate limits "
            "and multi-region failover so developers can drop in a stable URL."
        ),
        "tech": ["Node", "RPC"],
    },
    {
        "title": "Onchain Portfolio Tracker",
        "repo_url": "https://github.com/krissemmy/onchain-portfolio-tracker",
        "live_url": "https://portfolio.krissemmy.com/",
        "description": (
            "Web app that lets you paste multiple EVM wallets to view consolidated token "
            "balances and 24h PnL in one screen."
        ),
        "tech": ["FastAPI", "Sim API"],
    },
    {
        "title": "Node/RPC Benchmarking Devtool",
        "repo_url": "https://github.com/krissemmy/evm-node-rpc-benchmark",
        "live_url": "https://rpc.benchmark.krissemmy.com/",
        "description": (
            "Browser-based runner that hits RPC endpoints with configurable batches to measure "
            "latency, throughput, and error rates before choosing a provider."
        ),
        "tech": ["Benchmarking", "RPC"],
    },
    {
        "title": "Get Borrow APY for AaveV3 token",
        "repo_url": "https://github.com/krissemmy/Get-borrow-apy-for-a-token-on-aaveV3",
        "live_url": "https://get-borrow-apy-for-a-token-on-aave.krissemmy.com",
        "description": (
            "Small tool that returns the current borrow APR for any Aave V3 asset and shares a "
            "direct link so users can check rates without opening the app."
        ),
        "tech": ["Aave", "Rates"],
    },
    {
        "title": "Mattermost deployment with Kubernetes",
        "repo_url": "https://github.com/krissemmy/mattermost-deployment-with-k8s",
        "live_url": None,
        "description": (
            "Kubernetes manifests for a production-ready Mattermost rollout with ingress, TLS, "
            "persistent storage, and autoscaling defaults."
        ),
        "tech": ["Kubernetes", "Ingress"],
    },
    {
        "title": "Monitoring architecture with Kubernetes",
        "repo_url": "https://github.com/krissemmy/monitoring-architecture-with-kubernetes",
        "live_url": None,
        "description": (
            "Blueprint for deploying Alloy, Grafana, Loki, and Mimir on Kubernetes to collect "
            "logs and metrics with persistent storage."
        ),
        "tech": ["Grafana", "Loki", "Mimir"],
    },
    {
        "title": "EVM ETL pipeline using dlt",
        "repo_url": "https://github.com/krissemmy/ETL-with-dlt",
        "live_url": None,
        "description": (
            "Pipeline that ingests EVM chain data with dlt and lands it in a warehouse with reusable "
            "transform steps for analytics."
        ),
        "tech": ["dlt", "ETL"],
    },
    {
        "title": "HyperEVM node deployment with Kubernetes",
        "repo_url": "https://github.com/krissemmy/hyperevm-node-k8s",
        "live_url": None,
        "description": (
            "Kubernetes deployment files for running a HyperEVM full node with persistent volumes "
            "and liveness probes for automated restarts."
        ),
        "tech": ["Kubernetes", "HyperEVM"],
    },
    {
        "title": "IaC with Terraform",
        "repo_url": "https://github.com/krissemmy/IaC-With-Terraform",
        "live_url": None,
        "description": (
            "Terraform modules that spin up cloud networking, security groups, and compute defaults "
            "to bootstrap new projects quickly."
        ),
        "tech": ["Terraform", "IaC"],
    },
    {
        "title": "Polygon Finance data pipeline",
        "repo_url": "https://github.com/krissemmy/Polygon-Finance-Data-ELT",
        "live_url": None,
        "description": (
            "ELT workflow that extracts Polygon DeFi metrics and stages them for downstream dashboards "
            "and analysis."
        ),
        "tech": ["Polygon", "ELT"],
    },
    {
        "title": "Socrata API pipeline to GCS and BigQuery",
        "repo_url": "https://github.com/krissemmy/Socrata-API-Data-To-BigQuery",
        "live_url": None,
        "description": (
            "Connector that pulls Socrata open data into Google Cloud Storage and loads curated tables "
            "into BigQuery on a schedule."
        ),
        "tech": ["BigQuery", "GCS"],
    },
    {
        "title": "Hamoye CKD prediction (team project)",
        "repo_url": "https://github.com/krissemmy/Team-GCP-Hamoye-HDSC-Spring-23-Capstone-Project",
        "live_url": None,
        "description": (
            "Team-built model that predicts chronic kidney disease risk from lab results with explainability "
            "artifacts for clinicians."
        ),
        "tech": ["ML", "Healthcare"],
    },
]

OSS_CONTRIBUTIONS = [
    {
        "title": "HyperEVM node",
        "repo_url": "https://github.com/krissemmy/node",
        "description": "Documented node setup steps and defaults to simplify spinning up HyperEVM infrastructure.",
    },
    {
        "title": "DeFiLlama Chainlist",
        "repo_url": "https://github.com/krissemmy/chainlist",
        "description": "Added chain metadata updates that keep DeFiLlama's network directory accurate for RPC consumers.",
    },
    {
        "title": "EVM Tools",
        "repo_url": "https://github.com/krissemmy/evm-tools",
        "description": "Contributed utility fixes to improve address validation and network configuration helpers.",
    },
]

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

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
        return chain_name.capitalize()
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


# ---------- SIM API calls for a single wallet ----------

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
                "chain_label": get_chain_label(token),
                # numeric helpers for aggregation
                "amountNumeric": amount_numeric if amount_numeric is not None else 0.0,
                "valueUSDNumeric": value_usd if value_usd is not None else 0.0,
            }
        )

    return enriched

async def get_svm_balances(wallet_address: str) -> List[Dict[str, Any]]:
    """
    Fetch SVM (Solana / Eclipse) balances for a given address.
    Endpoint: https://api.sim.dune.com/beta/svm/balances/{address}

    Returns tokens enriched similarly to get_wallet_balances():
      - amountNumeric
      - valueUSDNumeric
      - valueUSDFormatted
      - amountFormatted
      - change24h = None (no historical yet)
    """
    if not wallet_address:
        return []

    url = f"https://api.sim.dune.com/beta/svm/balances/{wallet_address}"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                headers={
                    "X-Sim-Api-Key": SIM_API_KEY,
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code != 200:
            print(
                "SVM balances request failed:",
                resp.status_code,
                resp.text[:500],
            )
            return []
        data = resp.json()
    except Exception as e:
        print("Error fetching SVM balances:", e)
        return []

    balances = data.get("balances") or []
    enriched: List[Dict[str, Any]] = []

    for token in balances:
        t = dict(token)

        # Chain marker
        chain = (t.get("chain") or "").lower()
        t["chain"] = chain

        # Normalise identifiers so your token_key works
        # (chain_id can be a string for SVM, contract_address uses mint/address)
        chain_id = t.get("chain_id")
        if chain_id is None:
            chain_id = chain or "svm"
        t["chain_id"] = chain_id

        contract_addr = t.get("contract_address") or t.get("mint") or t.get("address") or "svm-native"
        t["contract_address"] = contract_addr
        t["asset_type"] = t.get("asset_type") or "svm"

        # decimals + amountNumeric
        decimals_raw = t.get("decimals")
        amount_raw = t.get("amount")
        decimals = None
        amount_numeric = None
        try:
            if decimals_raw is not None:
                decimals = int(decimals_raw)
            if amount_raw is not None and decimals is not None and decimals >= 0:
                amt_dec = safe_decimal(amount_raw)
                if amt_dec is not None:
                    amount_numeric = float(amt_dec / (Decimal(10) ** decimals))
        except Exception:
            amount_numeric = None

        # valueUSDNumeric
        value_usd_raw = t.get("value_usd")
        value_usd_num = None
        d_val = safe_decimal(value_usd_raw)
        if d_val is not None:
            value_usd_num = float(d_val)

        # display formatting
        t["amountNumeric"] = amount_numeric or 0.0
        t["valueUSDNumeric"] = value_usd_num or 0.0
        t["valueUSDFormatted"] = format_usd(value_usd_num) if value_usd_num is not None else None
        t["amountFormatted"] = (
            format_amount_short(amount_numeric) if amount_numeric is not None else None
        )

        # No historical_prices for SVM yet
        t["change24h"] = None
        t["change24hBadgeLabel"] = None
        t["change24hBadgeClass"] = "badge-neutral"

        enriched.append(t)

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
    token_filter: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, float]:
    portfolio_tokens: Dict[Tuple[Any, Any, Any, Any], Dict[str, Any]] = {}
    all_activities: List[Dict[str, Any]] = []

    for addr in wallets:
        chain_type = detect_chain_type(addr)
        # EVM Address
        if chain_type == "evm":
            tokens = await get_wallet_balances(addr, include_historical_prices)
            activities = await get_wallet_activity(addr, 25)
        # SVM Address
        elif chain_type == "svm":
            tokens = await get_svm_balances(addr)
            activities = [] 

        else:
            # unknown or invalid address
            tokens = []
            activities = []

        for t in tokens:
            key = token_key(t)
            amount_num = float(t.get("amountNumeric") or 0.0)
            value_num = float(t.get("valueUSDNumeric") or 0.0)

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
async def portfolio_view(request: Request):
    primary_contacts = [c for c in CONTACTS if c.get("group") == "primary"]
    secondary_contacts = [c for c in CONTACTS if c.get("group") == "secondary"]

    return templates.TemplateResponse(
        "portfolio.html",
        {
            "request": request,
            "projects": PROJECTS,
            "oss_contributions": OSS_CONTRIBUTIONS,
            "primary_contacts": primary_contacts,
            "secondary_contacts": secondary_contacts,
        },
    )


@app.get("/wallet", response_class=HTMLResponse)
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