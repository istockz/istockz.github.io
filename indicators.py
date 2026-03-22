"""
Technical indicators and analysis engine.
"""
import pandas as pd
import numpy as np
from config import RSI_PERIOD, SMA_SHORT, SMA_LONG, RSI_OVERSOLD, RSI_OVERBOUGHT, TOP_N
from db import load_eod_prices, get_all_symbols


def calc_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_sma(series: pd.Series, window: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return series.rolling(window=window, min_periods=1).mean()


def analyze_stock(symbol: str) -> dict | None:
    """
    Run full analysis on a single stock.
    Returns a dict with latest values, or None if insufficient data.
    """
    df = load_eod_prices(symbol)
    if df.empty or len(df) < 2:
        return None

    close = df["close"]

    # Calculate indicators
    df["rsi"] = calc_rsi(close)
    df["sma_50"] = calc_sma(close, SMA_SHORT)
    df["sma_200"] = calc_sma(close, SMA_LONG)
    df["daily_pct_change"] = close.pct_change() * 100

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    return {
        "symbol": symbol,
        "date": str(latest.name.date()),
        "open": round(float(latest["open"]), 2),
        "high": round(float(latest["high"]), 2),
        "low": round(float(latest["low"]), 2),
        "close": round(float(latest["close"]), 2),
        "volume": int(latest["volume"]),
        "rsi": round(float(latest["rsi"]), 2) if not np.isnan(latest["rsi"]) else None,
        "sma_50": round(float(latest["sma_50"]), 2),
        "sma_200": round(float(latest["sma_200"]), 2),
        "daily_pct_change": round(float(latest["daily_pct_change"]), 2)
            if not np.isnan(latest["daily_pct_change"]) else 0.0,
        "prev_close": round(float(prev["close"]), 2),
    }


def analyze_all(symbols: list[str] | None = None) -> dict:
    """
    Analyze all stocks and return a structured report.
    """
    if symbols is None:
        symbols = get_all_symbols()

    results = []
    for symbol in symbols:
        r = analyze_stock(symbol)
        if r:
            results.append(r)

    if not results:
        return {"stocks": [], "top_gainers": [], "top_losers": [],
                "oversold": [], "overbought": []}

    # Sort by daily % change
    sorted_by_change = sorted(results, key=lambda x: x["daily_pct_change"], reverse=True)

    top_gainers = sorted_by_change[:TOP_N]
    top_losers = sorted_by_change[-TOP_N:][::-1]  # Worst first

    oversold = [s for s in results if s["rsi"] is not None and s["rsi"] < RSI_OVERSOLD]
    overbought = [s for s in results if s["rsi"] is not None and s["rsi"] > RSI_OVERBOUGHT]

    return {
        "stocks": results,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "oversold": oversold,
        "overbought": overbought,
    }


def get_stock_dataframe(symbol: str) -> pd.DataFrame | None:
    """
    Return a full DataFrame with indicators for charting.
    """
    df = load_eod_prices(symbol)
    if df.empty:
        return None
    df["rsi"] = calc_rsi(df["close"])
    df["sma_50"] = calc_sma(df["close"], SMA_SHORT)
    df["sma_200"] = calc_sma(df["close"], SMA_LONG)
    df["daily_pct_change"] = df["close"].pct_change() * 100
    return df
