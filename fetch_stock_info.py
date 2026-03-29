"""
Fetch stock metadata (sector, industry, market cap) and fundamentals from yfinance.
Stores results in the stock_info and stock_fundamentals tables.
"""
import time
import yfinance as yf
from db import (
    upsert_stock_info, upsert_stock_fundamentals,
    get_stocks_without_info, get_stocks_without_fundamentals,
    get_all_symbols,
)


def classify_market_cap(cap: float) -> str:
    """
    Classify market cap into Indian market categories.
    Large Cap:  >= 20,000 Cr (200 billion INR)
    Mid Cap:    >= 5,000 Cr (50 billion INR)
    Small Cap:  >= 500 Cr (5 billion INR)
    Micro Cap:  < 500 Cr
    """
    if cap is None or cap <= 0:
        return "Unknown"
    crores = cap / 1e7
    if crores >= 20000:
        return "Large Cap"
    elif crores >= 5000:
        return "Mid Cap"
    elif crores >= 500:
        return "Small Cap"
    else:
        return "Micro Cap"


def fetch_single_info(symbol: str) -> dict | None:
    """
    Fetch all available data for one stock from yfinance.
    Returns the full info dict or None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info:
            return None

        sector = info.get("sector", "Unknown") or "Unknown"
        industry = info.get("industry", "Unknown") or "Unknown"
        market_cap = info.get("marketCap", 0) or 0

        return {
            "sector": sector,
            "industry": industry,
            "market_cap": float(market_cap),
            "market_cap_cat": classify_market_cap(float(market_cap)),
            "raw_info": info,  # Full info dict for fundamentals
        }
    except Exception:
        return None


def fetch_and_store_info(symbols: list[str] | None = None, batch_size: int = 20):
    """
    Fetch stock info + fundamentals for all symbols missing data.
    Uses individual API calls (yfinance .info doesn't support batch).
    """
    if symbols is None:
        # Get symbols missing either stock_info OR fundamentals
        missing_info = set(get_stocks_without_info())
        missing_fund = set(get_stocks_without_fundamentals())
        symbols = list(missing_info | missing_fund)

    if not symbols:
        print("[INFO] All stocks already have sector/market cap + fundamentals data.")
        return 0, 0

    total = len(symbols)
    success = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"  Fetching info + fundamentals for {total} stocks")
    print(f"  (This is a one-time operation, will be cached)")
    print(f"{'='*60}")

    for i, sym in enumerate(symbols, 1):
        if i % 50 == 1 or i == total:
            print(f"\n  Processing {i}/{total} ...", flush=True)

        info = fetch_single_info(sym)
        if info:
            # Store basic info (sector, industry, cap)
            upsert_stock_info(
                symbol=sym,
                sector=info["sector"],
                industry=info["industry"],
                market_cap=info["market_cap"],
                market_cap_cat=info["market_cap_cat"],
            )
            # Store full fundamentals
            upsert_stock_fundamentals(sym, info["raw_info"])
            success += 1
        else:
            upsert_stock_info(sym, "Unknown", "Unknown", 0, "Unknown")
            upsert_stock_fundamentals(sym, {})
            failed += 1

        # Rate limit
        if i % batch_size == 0:
            time.sleep(1)

    print(f"\n{'='*60}")
    print(f"  Done: {success}/{total} got info, {failed} defaulted.")
    print(f"{'='*60}")

    return success, failed
