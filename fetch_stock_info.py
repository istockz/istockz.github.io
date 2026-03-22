"""
Fetch stock metadata (sector, industry, market cap) from yfinance.
Stores results in the stock_info table for website filtering.
"""
import time
import yfinance as yf
from db import upsert_stock_info, get_stocks_without_info, get_all_symbols


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
    # yfinance returns market cap in the stock's currency (INR for Indian stocks)
    crores = cap / 1e7  # Convert to crores
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
    Fetch sector/industry/market cap for one stock from yfinance.
    Returns dict or None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or info.get("trailingPegRatio") is None and info.get("sector") is None:
            # Minimal info — might be invalid ticker
            pass

        sector = info.get("sector", "Unknown") or "Unknown"
        industry = info.get("industry", "Unknown") or "Unknown"
        market_cap = info.get("marketCap", 0) or 0

        return {
            "sector": sector,
            "industry": industry,
            "market_cap": float(market_cap),
            "market_cap_cat": classify_market_cap(float(market_cap)),
        }
    except Exception:
        return None


def fetch_and_store_info(symbols: list[str] | None = None, batch_size: int = 20):
    """
    Fetch stock info for all symbols missing from stock_info table.
    Uses individual API calls (yfinance .info doesn't support batch).
    """
    if symbols is None:
        symbols = get_stocks_without_info()

    if not symbols:
        print("[INFO] All stocks already have sector/market cap data.")
        return 0, 0

    total = len(symbols)
    success = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"  Fetching sector/market cap for {total} stocks")
    print(f"  (This is a one-time operation, will be cached)")
    print(f"{'='*60}")

    for i, sym in enumerate(symbols, 1):
        if i % 50 == 1 or i == total:
            print(f"\n  Processing {i}/{total} ...", flush=True)

        info = fetch_single_info(sym)
        if info:
            upsert_stock_info(
                symbol=sym,
                sector=info["sector"],
                industry=info["industry"],
                market_cap=info["market_cap"],
                market_cap_cat=info["market_cap_cat"],
            )
            success += 1
        else:
            # Store with defaults so we don't retry every time
            upsert_stock_info(sym, "Unknown", "Unknown", 0, "Unknown")
            failed += 1

        # Rate limit: small delay every batch_size stocks
        if i % batch_size == 0:
            time.sleep(1)

    print(f"\n{'='*60}")
    print(f"  Done: {success}/{total} got info, {failed} defaulted.")
    print(f"{'='*60}")

    return success, failed
