"""
EOD Stock Analysis System — Main entry point.

Usage:
    python main.py                      # Full run: fetch all NSE + generate website
    python main.py --website-only       # Skip fetch, generate website from existing DB
    python main.py --fetch-symbols      # Re-download NSE symbol list
    python main.py --analyze-only       # CLI analysis of existing DB data
    python main.py --stock TCS.NS       # Analyze a single stock with chart
    python main.py --chart INFY.NS      # Generate chart for a stock
"""
import argparse
import json
import csv
import os
import sys
from datetime import datetime

from config import REPORT_JSON, REPORT_CSV, CHART_DIR
from db import init_db
from fetch_data import fetch_and_store_all, load_symbols
from indicators import analyze_all, analyze_stock, get_stock_dataframe


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_stock_table(stocks: list[dict], title: str):
    """Print a table of stocks with key metrics."""
    if not stocks:
        print(f"\n  {title}: None")
        return
    print(f"\n  {title}:")
    print(f"  {'Symbol':<18} {'Close':>10} {'Chg%':>8} {'RSI':>8} {'SMA50':>10} {'SMA200':>10}")
    print(f"  {'-'*64}")
    for s in stocks:
        rsi_str = f"{s['rsi']:.1f}" if s["rsi"] is not None else "N/A"
        print(f"  {s['symbol']:<18} {s['close']:>10.2f} {s['daily_pct_change']:>+8.2f} "
              f"{rsi_str:>8} {s['sma_50']:>10.2f} {s['sma_200']:>10.2f}")


def display_report(report: dict):
    """Display the full analysis report in the terminal."""
    print_section(f"EOD STOCK ANALYSIS REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print_stock_table(report["top_gainers"], "TOP GAINERS")
    print_stock_table(report["top_losers"], "TOP LOSERS")
    print_stock_table(report["oversold"], "OVERSOLD (RSI < 30)")
    print_stock_table(report["overbought"], "OVERBOUGHT (RSI > 70)")

    print_section("ALL STOCKS SUMMARY")
    print_stock_table(report["stocks"], "Full List")
    print()


def save_json(report: dict, path: str = REPORT_JSON):
    """Save report as JSON."""
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[OUTPUT] JSON report saved to {path}")


def save_csv(report: dict, path: str = REPORT_CSV):
    """Save all stock data as CSV."""
    stocks = report.get("stocks", [])
    if not stocks:
        print("[OUTPUT] No data to save as CSV.")
        return

    fieldnames = ["symbol", "date", "open", "high", "low", "close", "volume",
                  "rsi", "sma_50", "sma_200", "daily_pct_change", "prev_close"]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stocks)
    print(f"[OUTPUT] CSV report saved to {path}")


def generate_chart(symbol: str):
    """Generate a matplotlib chart for a single stock."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("[WARN] matplotlib not installed. pip install matplotlib")
        return

    df = get_stock_dataframe(symbol)
    if df is None or df.empty:
        print(f"[WARN] No data for {symbol}, cannot generate chart.")
        return

    os.makedirs(CHART_DIR, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1],
                                    sharex=True, gridspec_kw={"hspace": 0.1})

    ax1.plot(df.index, df["close"], label="Close", color="#2196F3", linewidth=1.5)
    ax1.plot(df.index, df["sma_50"], label="SMA 50", color="#FF9800", linewidth=1, linestyle="--")
    ax1.plot(df.index, df["sma_200"], label="SMA 200", color="#E91E63", linewidth=1, linestyle="--")
    ax1.set_title(f"{symbol} - EOD Analysis", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Price (INR)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)

    ax2.plot(df.index, df["rsi"], color="#9C27B0", linewidth=1.2)
    ax2.axhline(y=70, color="red", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.axhline(y=30, color="green", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.fill_between(df.index, 70, 100, alpha=0.1, color="red")
    ax2.fill_between(df.index, 0, 30, alpha=0.1, color="green")
    ax2.set_ylabel("RSI")
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45)
    plt.tight_layout()

    chart_path = os.path.join(CHART_DIR, f"{symbol.replace('.', '_')}.png")
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"[CHART] Saved to {chart_path}")


def run_single_stock(symbol: str):
    """Fetch (if needed), analyze, and chart a single stock."""
    from fetch_data import fetch_single_stock
    from db import upsert_stock, upsert_eod_prices

    print(f"\nFetching latest data for {symbol}...")
    df = fetch_single_stock(symbol)
    if df is not None:
        upsert_stock(symbol)
        upsert_eod_prices(symbol, df)
        print(f"  Stored {len(df)} rows.")

    result = analyze_stock(symbol)
    if result is None:
        print(f"[ERROR] No data available for {symbol}.")
        sys.exit(1)

    print_section(f"ANALYSIS: {symbol}")
    print_stock_table([result], symbol)
    generate_chart(symbol)
    print()


def run_website_pipeline(skip_fetch: bool = False, refresh_symbols: bool = False):
    """
    Full website pipeline:
    1. Get all NSE symbols
    2. Fetch EOD data for all
    3. Generate static HTML website
    """
    from nse_symbols import get_yfinance_symbols
    from generate_site import generate_website

    if not skip_fetch:
        # Step 1: Get symbol list
        print_section("STEP 1: Loading NSE + BSE symbol list")
        symbols = get_yfinance_symbols(force_refresh=refresh_symbols)
        print(f"  Total symbols: {len(symbols)}")

        # Step 2: Fetch EOD price data
        print_section("STEP 2: Fetching EOD data")
        fetch_and_store_all(symbols)

        # Step 3: Fetch sector/industry/market cap info (only for new stocks)
        print_section("STEP 3: Fetching sector & market cap info")
        from fetch_stock_info import fetch_and_store_info
        fetch_and_store_info()

    # Step 4: Fetch global and Indian market indices
    print_section("STEP 4: Fetching market indices")
    from fetch_indices import fetch_and_save as fetch_indices
    fetch_indices()

    # Step 5: Generate website
    print_section("STEP 5: Generating website")
    generate_website()

    # Open in browser
    from config import SITE_OUTPUT
    print(f"\n  Opening {SITE_OUTPUT} in browser...")
    os.startfile(SITE_OUTPUT)

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="EOD Stock Analysis System (NSE)")
    parser.add_argument("--website-only", action="store_true",
                        help="Generate website from existing DB data (skip fetch)")
    parser.add_argument("--fetch-symbols", action="store_true",
                        help="Force re-download NSE symbol list")
    parser.add_argument("--analyze-only", action="store_true",
                        help="CLI analysis only (no website)")
    parser.add_argument("--stock", type=str,
                        help="Analyze a single stock (e.g., TCS.NS)")
    parser.add_argument("--chart", type=str,
                        help="Generate chart for a specific stock")
    args = parser.parse_args()

    # Initialize database
    init_db()

    # Single stock mode
    if args.stock:
        run_single_stock(args.stock)
        return

    # Chart-only mode
    if args.chart:
        generate_chart(args.chart)
        return

    # CLI analysis mode (original behavior)
    if args.analyze_only:
        print_section("RUNNING ANALYSIS")
        report = analyze_all()
        if not report["stocks"]:
            print("[WARN] No stock data found. Run without --analyze-only first.")
            return
        display_report(report)
        save_json(report)
        save_csv(report)
        return

    # Default: website pipeline
    run_website_pipeline(
        skip_fetch=args.website_only,
        refresh_symbols=args.fetch_symbols,
    )


if __name__ == "__main__":
    main()
