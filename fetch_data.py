"""
Data fetching module — downloads OHLCV data from Yahoo Finance via yfinance.
Supports both single-stock and batch downloading for large symbol lists.
"""
import time
import yfinance as yf
import pandas as pd
from config import STOCKS_FILE, HISTORY_PERIOD, BATCH_SIZE
from db import upsert_stock, upsert_eod_prices


def load_symbols(filepath: str = STOCKS_FILE) -> list[str]:
    """Read stock symbols from a text file (one per line)."""
    with open(filepath, "r") as f:
        symbols = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return symbols


def fetch_single_stock(symbol: str, period: str = HISTORY_PERIOD) -> pd.DataFrame | None:
    """
    Download historical OHLCV data for one symbol.
    Returns a DataFrame or None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        if df.empty:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        return df
    except Exception:
        return None


def fetch_batch(symbols: list[str], period: str = HISTORY_PERIOD) -> dict[str, pd.DataFrame]:
    """
    Download data for multiple symbols at once using yf.download().
    Returns a dict of symbol -> DataFrame.
    """
    if not symbols:
        return {}

    try:
        data = yf.download(
            tickers=symbols,
            period=period,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception as e:
        print(f"  [ERROR] Batch download failed: {e}")
        return {}

    result = {}
    if len(symbols) == 1:
        # yf.download returns flat columns for single ticker
        sym = symbols[0]
        if not data.empty:
            df = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if not df.empty:
                result[sym] = df
    else:
        for sym in symbols:
            try:
                df = data[sym][["Open", "High", "Low", "Close", "Volume"]].dropna()
                if not df.empty:
                    result[sym] = df
            except (KeyError, TypeError):
                continue

    return result


def fetch_and_store_all(symbols: list[str] | None = None):
    """
    Fetch data for all symbols and store in SQLite.
    Uses batch downloading for efficiency with large lists.
    """
    if symbols is None:
        symbols = load_symbols()

    total = len(symbols)
    success = 0
    failed = []

    print(f"\n{'='*60}")
    print(f"  Fetching EOD data for {total} stocks ({HISTORY_PERIOD})")
    print(f"{'='*60}")

    # Process in batches
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = symbols[start:end]

        print(f"\n  Batch {batch_idx + 1}/{num_batches} "
              f"[{start + 1}-{end} of {total}] ...", flush=True)

        results = fetch_batch(batch, HISTORY_PERIOD)

        for sym in batch:
            if sym in results:
                upsert_stock(sym)
                upsert_eod_prices(sym, results[sym])
                success += 1
            else:
                failed.append(sym)

        print(f"    Got {len(results)}/{len(batch)} stocks", flush=True)

        # Delay between batches to avoid rate-limiting
        if batch_idx < num_batches - 1:
            time.sleep(2)

    print(f"\n{'='*60}")
    print(f"  Done: {success}/{total} succeeded, {len(failed)} failed.")
    print(f"{'='*60}")

    if failed and len(failed) <= 20:
        print(f"  Failed: {', '.join(failed)}")

    return success, failed
