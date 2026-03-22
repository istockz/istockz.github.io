"""
Fetch all Indian stock symbols from NSE and BSE exchanges.
Uses NSE CSV + BSE Python package. Caches locally.
"""
import os
import csv
import io
from datetime import datetime, timedelta
from config import BASE_DIR

SYMBOLS_CACHE = os.path.join(BASE_DIR, "all_symbols_cache.csv")
NSE_SYMBOLS_CACHE = os.path.join(BASE_DIR, "nse_symbols_cache.csv")  # backward compat


def _download_nse_list() -> list[dict]:
    """Download NSE equity list. Returns list of dicts with symbol, name, exchange."""
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    session = requests.Session()
    session.headers.update(headers)

    csv_urls = [
        "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    ]

    # Get cookies first
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass

    for url in csv_urls:
        try:
            print(f"[NSE] Trying {url}...")
            resp = session.get(url, timeout=15)
            if resp.status_code == 200 and "SYMBOL" in resp.text[:200]:
                reader = csv.DictReader(io.StringIO(resp.text))
                stocks = []
                for row in reader:
                    symbol = row.get("SYMBOL", "").strip()
                    name = row.get("NAME OF COMPANY", "").strip()
                    if symbol:
                        stocks.append({
                            "symbol": symbol,
                            "name": name,
                            "exchange": "NSE",
                            "yf_symbol": f"{symbol}.NS",
                        })
                if stocks:
                    print(f"[NSE] Got {len(stocks)} equities.")
                    return stocks
        except Exception as e:
            print(f"[NSE] Failed: {e}")

    # Fallback: try old NSE cache
    if os.path.exists(NSE_SYMBOLS_CACHE):
        print("[NSE] Using old NSE cache as fallback...")
        with open(NSE_SYMBOLS_CACHE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            stocks = []
            for row in reader:
                stocks.append({
                    "symbol": row["symbol"],
                    "name": row.get("name", row["symbol"]),
                    "exchange": "NSE",
                    "yf_symbol": f"{row['symbol']}.NS",
                })
            if stocks:
                print(f"[NSE] Got {len(stocks)} from old cache.")
                return stocks

    print("[NSE] All attempts failed.")
    return []


def _download_bse_list() -> list[dict]:
    """Download BSE equity list using the bse package."""
    try:
        from bse import BSE
    except ImportError:
        print("[BSE] 'bse' package not installed. Run: pip install bse")
        return []

    bse_dir = os.path.join(BASE_DIR, "bse_data")
    os.makedirs(bse_dir, exist_ok=True)

    try:
        b = BSE(download_folder=bse_dir)
        groups = b.getScripGroups()
        print(f"[BSE] Fetching securities from {len(groups)} groups...")

        all_stocks = []
        for group in groups:
            try:
                securities = b.listSecurities(group=group)
                all_stocks.extend(securities)
                print(f"  Group {group:>3}: {len(securities)} stocks")
            except Exception:
                continue

        # Convert to our format
        stocks = []
        seen = set()
        for s in all_stocks:
            scrip_id = s.get("scrip_id", "").strip()
            name = s.get("Issuer_Name", s.get("Scrip_Name", scrip_id)).strip()
            if scrip_id and scrip_id not in seen:
                seen.add(scrip_id)
                stocks.append({
                    "symbol": scrip_id,
                    "name": name,
                    "exchange": "BSE",
                    "yf_symbol": f"{scrip_id}.BO",
                })

        print(f"[BSE] Got {len(stocks)} unique equities.")
        return stocks

    except Exception as e:
        print(f"[BSE] Failed: {e}")
        return []


def _merge_lists(nse_stocks: list[dict], bse_stocks: list[dict]) -> list[dict]:
    """
    Merge NSE and BSE lists. Stocks on both get exchange='NSE+BSE'.
    NSE is preferred for yf_symbol (better liquidity).
    """
    merged = {}

    # Add NSE stocks first (preferred)
    for s in nse_stocks:
        merged[s["symbol"]] = s.copy()

    # Add BSE stocks, marking duplicates
    bse_only_count = 0
    dual_count = 0
    for s in bse_stocks:
        sym = s["symbol"]
        if sym in merged:
            # Dual-listed — keep NSE yf_symbol, update exchange
            merged[sym]["exchange"] = "NSE+BSE"
            dual_count += 1
        else:
            # BSE only
            merged[sym] = s.copy()
            bse_only_count += 1

    result = sorted(merged.values(), key=lambda x: x["symbol"])
    print(f"\n[MERGED] NSE: {len(nse_stocks)}, BSE: {len(bse_stocks)}")
    print(f"  Dual-listed: {dual_count}")
    print(f"  BSE-only: {bse_only_count}")
    print(f"  Total unique: {len(result)}")
    return result


def _save_cache(stocks: list[dict]):
    """Save combined stock list to local cache."""
    with open(SYMBOLS_CACHE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "name", "exchange", "yf_symbol"])
        writer.writeheader()
        writer.writerows(stocks)
    print(f"[CACHE] Saved {len(stocks)} symbols to {SYMBOLS_CACHE}")


def _load_cache() -> list[dict]:
    """Load stock list from local cache."""
    if not os.path.exists(SYMBOLS_CACHE):
        return []
    with open(SYMBOLS_CACHE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _cache_is_fresh(max_age_days: int = 7) -> bool:
    """Check if cache is less than max_age_days old."""
    if not os.path.exists(SYMBOLS_CACHE):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(SYMBOLS_CACHE))
    return (datetime.now() - mtime) < timedelta(days=max_age_days)


def get_all_symbols(force_refresh: bool = False) -> list[dict]:
    """
    Get all Indian stock symbols (NSE + BSE combined).
    Returns list of dicts: [{"symbol", "name", "exchange", "yf_symbol"}, ...]
    """
    if not force_refresh and _cache_is_fresh():
        stocks = _load_cache()
        print(f"[SYMBOLS] Using cached list ({len(stocks)} stocks)")
        return stocks

    print("[SYMBOLS] Refreshing stock list from NSE + BSE...")
    nse = _download_nse_list()
    bse = _download_bse_list()

    if nse or bse:
        merged = _merge_lists(nse, bse)
        _save_cache(merged)
        return merged

    # Fallback to cache even if stale
    stocks = _load_cache()
    if stocks:
        print(f"[SYMBOLS] Using stale cache ({len(stocks)} stocks)")
        return stocks

    # Last resort: stocks.txt
    print("[SYMBOLS] No source available. Using stocks.txt.")
    from fetch_data import load_symbols
    syms = load_symbols()
    return [{"symbol": s.replace(".NS", ""), "name": s.replace(".NS", ""),
             "exchange": "NSE", "yf_symbol": s} for s in syms]


# Backward-compatible aliases
def get_nse_symbols(force_refresh: bool = False) -> list[dict]:
    return get_all_symbols(force_refresh)


def get_yfinance_symbols(force_refresh: bool = False) -> list[str]:
    """Get all symbols in yfinance format."""
    stocks = get_all_symbols(force_refresh)
    return [s["yf_symbol"] for s in stocks]


def get_symbol_name_map(force_refresh: bool = False) -> dict[str, str]:
    """Get a mapping of yf_symbol -> Company Name."""
    stocks = get_all_symbols(force_refresh)
    return {s["yf_symbol"]: s["name"] for s in stocks}


def get_symbol_exchange_map(force_refresh: bool = False) -> dict[str, str]:
    """Get a mapping of yf_symbol -> Exchange (NSE, BSE, NSE+BSE)."""
    stocks = get_all_symbols(force_refresh)
    return {s["yf_symbol"]: s["exchange"] for s in stocks}
