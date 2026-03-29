"""
Fetch global and Indian market indices data from yfinance.
Returns current values with daily change for display.
"""
import json
import os
import yfinance as yf
from config import DATA_DIR


# All indices grouped by region
INDICES = {
    "India - Broad": {
        "^NSEI": "Nifty 50",
        "^BSESN": "Sensex",
        "^NSEBANK": "Bank Nifty",
        "^CNXSC": "Nifty Smallcap",
        "^CNXMC": "Nifty Midcap",
    },
    "India - Sectoral": {
        "^CNXIT": "Nifty IT",
        "^CNXPHARMA": "Nifty Pharma",
        "^CNXAUTO": "Nifty Auto",
        "^CNXMETAL": "Nifty Metal",
        "^CNXFMCG": "Nifty FMCG",
        "^CNXREALTY": "Nifty Realty",
        "^CNXENERGY": "Nifty Energy",
        "^CNXINFRA": "Nifty Infra",
        "^CNXPSUBANK": "Nifty PSU Bank",
        "^CNXMEDIA": "Nifty Media",
    },
    "United States": {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq",
        "^DJI": "Dow Jones",
        "^RUT": "Russell 2000",
    },
    "Europe": {
        "^FTSE": "FTSE 100",
        "^GDAXI": "DAX",
        "^FCHI": "CAC 40",
        "^STOXX50E": "Euro Stoxx 50",
    },
    "Asia Pacific": {
        "^N225": "Nikkei 225",
        "^HSI": "Hang Seng",
        "^KS11": "KOSPI",
        "^TWII": "TAIEX",
        "^STI": "STI Singapore",
        "^AXJO": "ASX 200",
        "^JKSE": "Jakarta",
    },
}


def fetch_all_indices():
    """
    Fetch latest data for all indices.
    Returns a dict grouped by region with index data.
    """
    result = {}

    for region, indices in INDICES.items():
        region_data = []
        for symbol, name in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if len(hist) < 1:
                    continue

                last = hist.iloc[-1]
                close = round(float(last["Close"]), 2)

                # Calculate change from previous day
                if len(hist) >= 2:
                    prev_close = round(float(hist.iloc[-2]["Close"]), 2)
                    change = round(close - prev_close, 2)
                    change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                else:
                    prev_close = close
                    change = 0
                    change_pct = 0

                region_data.append({
                    "symbol": symbol,
                    "name": name,
                    "close": close,
                    "prev_close": prev_close,
                    "change": change,
                    "change_pct": change_pct,
                    "high": round(float(last["High"]), 2),
                    "low": round(float(last["Low"]), 2),
                    "open": round(float(last["Open"]), 2),
                    "volume": int(last["Volume"]) if last["Volume"] else 0,
                    "date": str(hist.index[-1].date()),
                })
                print(f"  {name}: {close} ({change_pct:+.2f}%)")

            except Exception as e:
                print(f"  {name}: FAILED - {e}")
                continue

        if region_data:
            result[region] = region_data

    return result


def save_indices_json(data):
    """Save indices data as JSON file for the website."""
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "indices.json")
    with open(filepath, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"[INDICES] Saved to {filepath}")
    return filepath


def fetch_and_save():
    """Main function: fetch all indices and save to JSON."""
    print("\n" + "=" * 60)
    print("  Fetching Global & Indian Market Indices")
    print("=" * 60)

    data = fetch_all_indices()
    save_indices_json(data)

    total = sum(len(v) for v in data.values())
    print(f"\n  Done: {total} indices across {len(data)} regions")
    print("=" * 60)

    return data


if __name__ == "__main__":
    fetch_and_save()
