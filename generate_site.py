"""
Static HTML site generator -- produces a self-contained index.html
with all EOD stock data, dark trading-terminal theme, search, sort,
pagination, and GLOBAL sector/market-cap/exchange filters that affect
the ticker tape, stats cards, top movers, and the data table.
"""
import json
import os
from datetime import datetime
from config import SITE_OUTPUT, DATA_DIR
from db import get_latest_prices, get_stock_count, get_stock_info_map, get_all_fundamentals_map
from nse_symbols import get_symbol_name_map, get_symbol_exchange_map


def generate_chart_data():
    """Generate individual JSON files with OHLCV data + fundamentals for each stock."""
    from db import get_connection

    os.makedirs(DATA_DIR, exist_ok=True)

    # Load all fundamentals
    fund_map = get_all_fundamentals_map()

    conn = get_connection()
    cursor = conn.execute(
        "SELECT symbol, date, open, high, low, close, volume "
        "FROM eod_prices ORDER BY symbol, date"
    )

    current_symbol = None
    current_data = []
    file_count = 0

    # Fields to include in the JSON (skip huge text fields for file size)
    FUND_KEYS = [
        "long_name", "website", "city", "full_time_employees",
        "trailing_pe", "forward_pe", "price_to_book", "book_value",
        "eps_trailing", "eps_forward", "dividend_rate", "dividend_yield",
        "payout_ratio", "five_yr_avg_div_yield", "revenue",
        "revenue_per_share", "revenue_growth", "ebitda", "ebitda_margins",
        "gross_margins", "operating_margins", "profit_margins",
        "net_income", "total_cash", "total_cash_per_share", "total_debt",
        "debt_to_equity", "current_ratio", "free_cashflow",
        "return_on_equity", "enterprise_value", "enterprise_to_ebitda",
        "enterprise_to_revenue", "earnings_growth", "shares_outstanding",
        "float_shares", "held_pct_insiders", "held_pct_institutions",
        "beta", "fifty_two_week_high", "fifty_two_week_low",
        "fifty_day_average", "two_hundred_day_avg", "target_high_price",
        "target_low_price", "target_mean_price", "recommendation",
        "num_analyst_opinions", "all_time_high", "all_time_low",
        "long_business_summary",
    ]

    def write_stock_file(symbol, ohlcv_data):
        safe_name = symbol.replace(".", "_")
        filepath = os.path.join(DATA_DIR, f"{safe_name}.json")
        # Build output: { "ohlcv": [...], "fundamentals": {...} }
        fund = fund_map.get(symbol, {})
        fund_out = {}
        for k in FUND_KEYS:
            v = fund.get(k)
            if v is not None:
                fund_out[k] = v
        output = {"ohlcv": ohlcv_data, "fundamentals": fund_out}
        with open(filepath, "w") as f:
            json.dump(output, f, separators=(",", ":"))

    for row in cursor:
        symbol, date, o, h, l, c, v = row
        if symbol != current_symbol:
            if current_symbol and current_data:
                write_stock_file(current_symbol, current_data)
                file_count += 1
            current_symbol = symbol
            current_data = []
        current_data.append([
            date,
            round(o, 2) if o else 0,
            round(h, 2) if h else 0,
            round(l, 2) if l else 0,
            round(c, 2) if c else 0,
            int(v) if v else 0,
        ])

    # Write the last symbol
    if current_symbol and current_data:
        write_stock_file(current_symbol, current_data)
        file_count += 1

    conn.close()
    print(f"[SITE] Generated {file_count} chart data files in {DATA_DIR}")


def generate_website():
    """Generate index.html with embedded stock data."""
    prices = get_latest_prices()
    if not prices:
        print("[SITE] No price data in database. Fetch data first.")
        return

    # Generate individual stock chart data files
    generate_chart_data()

    # Enrich with company names, exchange, and sector info
    name_map = get_symbol_name_map()
    exchange_map = get_symbol_exchange_map()
    info_map = get_stock_info_map()

    # Collect unique sectors and market cap categories
    sectors = set()
    caps = set()

    for row in prices:
        row["name"] = name_map.get(
            row["symbol"],
            row["symbol"].replace(".NS", "").replace(".BO", ""),
        )
        row["exchange"] = exchange_map.get(
            row["symbol"],
            "BSE" if row["symbol"].endswith(".BO") else "NSE",
        )
        si = info_map.get(row["symbol"], {})
        row["sector"] = si.get("sector", "Unknown")
        row["industry"] = si.get("industry", "Unknown")
        row["market_cap_cat"] = si.get("market_cap_cat", "Unknown")
        sectors.add(row["sector"])
        caps.add(row["market_cap_cat"])

    # Sort filter options
    sectors = sorted(s for s in sectors if s and s != "Unknown") + ["Unknown"]
    caps_order = ["Large Cap", "Mid Cap", "Small Cap", "Micro Cap", "Unknown"]
    caps = [c for c in caps_order if c in caps]

    # Market stats (computed on full set -- JS will recompute for filtered view)
    total = len(prices)
    gainers = sum(1 for p in prices if p["change_pct"] > 0)
    losers = sum(1 for p in prices if p["change_pct"] < 0)
    unchanged = total - gainers - losers
    avg_change = round(sum(p["change_pct"] for p in prices) / total, 2) if total else 0

    data_date = prices[0]["date"] if prices else "N/A"

    stats = {
        "total": total,
        "gainers": gainers,
        "losers": losers,
        "unchanged": unchanged,
        "avg_change": avg_change,
        "date": data_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    html = _build_html(prices, stats, sectors, caps)

    with open(SITE_OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[SITE] Generated {SITE_OUTPUT} ({total} stocks, {len(sectors)} sectors)")


def _build_html(prices, stats, sectors, caps):
    """Build the complete HTML string."""
    prices_json = json.dumps(prices)
    stats_json = json.dumps(stats)
    sectors_json = json.dumps(sectors)
    caps_json = json.dumps(caps)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Istockz - Indian Stock Market EOD Prices</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --border: #30363d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --green: #26a641;
    --green-bg: rgba(38,166,65,0.15);
    --red: #f85149;
    --red-bg: rgba(248,81,73,0.15);
    --blue: #58a6ff;
    --orange: #d29922;
    --purple: #bc8cff;
}}

body {{
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    line-height: 1.5;
    min-height: 100vh;
}}

/* Header */
.header {{
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
}}
.header-content {{
    max-width: 1400px; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 12px;
}}
.logo {{ font-size: 22px; font-weight: 700; color: var(--blue); letter-spacing: -0.5px; display: flex; align-items: center; gap: 12px; }}
.logo span {{ color: var(--text-muted); font-weight: 400; font-size: 13px; }}
.header-meta {{ color: var(--text-secondary); font-size: 13px; text-align: right; }}

/* Hamburger Menu */
.hamburger {{
    width: 36px; height: 36px; display: flex; flex-direction: column;
    justify-content: center; align-items: center; gap: 5px; cursor: pointer;
    background: none; border: 1px solid var(--border); border-radius: 6px;
    padding: 6px; transition: all 0.2s;
}}
.hamburger:hover {{ border-color: var(--blue); background: rgba(88,166,255,0.08); }}
.hamburger span {{
    display: block; width: 18px; height: 2px; background: var(--text-secondary);
    border-radius: 1px; transition: all 0.3s;
}}
.hamburger.active span:nth-child(1) {{ transform: rotate(45deg) translate(5px, 5px); }}
.hamburger.active span:nth-child(2) {{ opacity: 0; }}
.hamburger.active span:nth-child(3) {{ transform: rotate(-45deg) translate(5px, -5px); }}

.nav-menu {{
    position: fixed; top: 0; left: -320px; width: 300px; height: 100vh;
    background: var(--bg-secondary); border-right: 1px solid var(--border);
    z-index: 10001; transition: left 0.3s ease; overflow-y: auto;
    box-shadow: 4px 0 20px rgba(0,0,0,0.4);
}}
.nav-menu.open {{ left: 0; }}
.nav-backdrop {{
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.5); z-index: 10000; display: none;
}}
.nav-backdrop.open {{ display: block; }}
.nav-header {{
    padding: 16px 20px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
}}
.nav-header h3 {{ color: var(--blue); font-size: 18px; margin: 0; font-weight: 700; }}
.nav-close {{
    background: none; border: none; color: var(--text-muted); font-size: 24px;
    cursor: pointer; padding: 0; line-height: 1;
}}
.nav-close:hover {{ color: var(--red); }}
.nav-section {{
    border-bottom: 1px solid var(--border);
}}
.nav-section-title {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px;
    color: var(--text-muted); padding: 14px 20px 6px; font-weight: 600;
}}
.nav-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 20px; cursor: pointer; transition: all 0.15s;
    color: var(--text-secondary); font-size: 13px;
}}
.nav-item:hover {{ background: rgba(88,166,255,0.08); color: var(--text-primary); }}
.nav-item.active {{ background: rgba(88,166,255,0.12); color: var(--blue); border-left: 3px solid var(--blue); padding-left: 17px; }}
.nav-item .nav-count {{
    font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary);
    padding: 2px 8px; border-radius: 10px; font-weight: 500;
}}
.nav-item .nav-icon {{ margin-right: 10px; font-size: 14px; }}
.nav-item-all {{
    color: var(--blue); font-weight: 600;
}}

/* Ticker Tape */
.ticker-wrap {{
    background: #010409; border-bottom: 1px solid var(--border);
    position: relative; height: 40px;
}}
.ticker-track-clip {{
    overflow: hidden; width: 100%; height: 100%;
}}
.ticker-track {{
    display: flex; width: max-content;
    animation: ticker-scroll var(--ticker-duration, 120s) linear infinite;
}}
.ticker-track-clip:hover .ticker-track {{ animation-play-state: paused; }}

/* Universal ticker search box */
.ticker-search-box {{
    position: absolute; right: 44px; top: 50%; transform: translateY(-50%); z-index: 100;
}}
.ticker-search-box.fs-search {{
    right: 60px; top: 12px; transform: none;
}}
.ticker-wrap {{ position: relative; z-index: 50; }}
.ticker-search-box input {{
    width: 120px; height: 28px; background: rgba(22,27,34,0.9);
    border: 1px solid var(--border); border-radius: 14px; color: var(--text-primary);
    font-size: 11px; padding: 0 12px; outline: none;
    transition: width 0.3s, border-color 0.2s, background 0.2s;
    backdrop-filter: blur(8px);
}}
.ticker-search-box input:focus {{
    width: 200px; border-color: var(--blue); background: rgba(22,27,34,0.95);
}}
.ticker-search-results {{
    position: absolute; top: 34px; right: 0; width: 320px;
    max-height: 400px; overflow-y: auto; background: #161b22;
    border: 1px solid var(--border); border-radius: 8px;
    display: none; z-index: 9999; box-shadow: 0 12px 40px rgba(0,0,0,0.7);
}}
.ticker-search-results.active {{ display: block; }}
.ticker-search-result {{
    display: flex; align-items: center; gap: 8px;
    padding: 10px 14px; cursor: pointer; font-size: 12px;
    border-bottom: 1px solid rgba(48,54,61,0.3); transition: background 0.15s;
}}
.ticker-search-result:hover {{ background: rgba(88,166,255,0.08); }}
.ticker-search-result:last-child {{ border-bottom: none; }}
.ticker-search-result .tsr-sym {{ color: var(--blue); font-weight: 700; min-width: 70px; font-family: 'SF Mono','Consolas',monospace; }}
.ticker-search-result .tsr-name {{ color: var(--text-muted); font-size: 11px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.ticker-search-result .tsr-price {{ color: var(--text-secondary); font-weight: 600; }}
.ticker-search-result .tsr-chg {{ font-weight: 600; font-size: 11px; padding: 2px 6px; border-radius: 3px; margin-left: 4px; }}
.ticker-search-result .tsr-chg.up {{ color: var(--green); background: var(--green-bg); }}
.ticker-search-result .tsr-chg.down {{ color: var(--red); background: var(--red-bg); }}
@keyframes ticker-scroll {{
    0%   {{ transform: translateX(0); }}
    100% {{ transform: translateX(-50%); }}
}}
.ticker-item {{
    display: flex; align-items: center; gap: 6px;
    padding: 0 20px; height: 40px; white-space: nowrap;
    font-size: 13px; font-family: 'SF Mono','Cascadia Code','Consolas',monospace;
    border-right: 1px solid var(--border);
}}
.ticker-symbol {{ color: var(--text-primary); font-weight: 600; }}
.ticker-price  {{ color: var(--text-secondary); }}
.ticker-change {{ font-weight: 600; font-size: 12px; padding: 1px 6px; border-radius: 3px; }}
.ticker-change.up   {{ color: var(--green); background: var(--green-bg); }}
.ticker-change.down {{ color: var(--red);   background: var(--red-bg); }}
.ticker-change.flat {{ color: var(--text-muted); }}

/* Stats Bar */
.stats-bar {{ background: var(--bg-secondary); border-bottom: 1px solid var(--border); padding: 12px 24px; }}
.stats-grid {{ max-width: 1400px; margin: 0 auto; display: flex; gap: 16px; flex-wrap: wrap; }}
.stat-card {{
    background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 20px; flex: 1; min-width: 120px; text-align: center;
}}
.stat-card .label {{
    font-size: 11px; text-transform: uppercase; color: var(--text-muted);
    letter-spacing: 0.5px; margin-bottom: 4px;
}}
.stat-card .value {{
    font-size: 22px; font-weight: 700;
    font-family: 'SF Mono','Cascadia Code','Consolas',monospace;
}}
.stat-card .value.green {{ color: var(--green); }}
.stat-card .value.red   {{ color: var(--red); }}
.stat-card .value.blue  {{ color: var(--blue); }}

/* Global Filters Bar */
.global-filters {{
    max-width: 1400px; margin: 16px auto 0; padding: 0 24px;
}}
.filter-bar {{
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px 18px;
}}
.filter-group {{
    display: flex; align-items: center; gap: 8px;
}}
.filter-group label {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-muted); white-space: nowrap;
}}
.filter-select {{
    padding: 8px 32px 8px 12px;
    background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text-primary); font-size: 13px; cursor: pointer;
    outline: none; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%238b949e'%3E%3Cpath d='M6 8.5L1 3.5h10z'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center;
    min-width: 140px;
    transition: border-color 0.2s;
}}
.filter-select:hover, .filter-select:focus {{ border-color: var(--blue); }}
.filter-divider {{ width: 1px; height: 28px; background: var(--border); }}
.filter-reset {{
    padding: 8px 14px; background: transparent; border: 1px solid var(--border);
    border-radius: 6px; color: var(--text-muted); font-size: 12px; cursor: pointer;
    transition: all 0.2s; margin-left: auto;
}}
.filter-reset:hover {{ color: var(--red); border-color: var(--red); }}
.active-filter-tag {{
    font-size: 12px; color: var(--blue); background: rgba(88,166,255,0.1);
    border: 1px solid rgba(88,166,255,0.3); border-radius: 4px; padding: 2px 8px;
}}

/* Top Movers */
.movers-section {{
    max-width: 1400px; margin: 16px auto; padding: 0 24px;
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
}}
.mover-card {{
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
}}
.mover-card h3 {{
    font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 12px; color: var(--text-secondary);
}}
.mover-card h3.gainers {{ color: var(--green); }}
.mover-card h3.losers  {{ color: var(--red); }}
.mover-list {{ list-style: none; }}
.mover-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px;
}}
.mover-item:last-child {{ border-bottom: none; }}
.mover-symbol {{ font-weight: 600; font-family: 'SF Mono','Consolas',monospace; color: var(--text-primary); }}
.mover-name   {{ color: var(--text-muted); font-size: 11px; margin-left: 8px; }}
.mover-change {{
    font-family: 'SF Mono','Consolas',monospace; font-weight: 600;
    font-size: 13px; padding: 2px 8px; border-radius: 4px;
}}
.mover-change.positive {{ color: var(--green); background: var(--green-bg); }}
.mover-change.negative {{ color: var(--red);   background: var(--red-bg); }}

/* Controls (search + price filter) */
.controls {{
    max-width: 1400px; margin: 16px auto; padding: 0 24px;
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
}}
.search-box {{ flex: 1; min-width: 250px; position: relative; }}
.search-box input {{
    width: 100%; padding: 10px 16px 10px 40px;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px;
    color: var(--text-primary); font-size: 14px; outline: none; transition: border-color 0.2s;
}}
.search-box input:focus {{ border-color: var(--blue); }}
.search-box input::placeholder {{ color: var(--text-muted); }}
.search-box svg {{
    position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
    width: 18px; height: 18px; fill: var(--text-muted);
}}
.filter-btn {{
    padding: 10px 16px; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: 8px;
    color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: all 0.2s;
}}
.filter-btn:hover, .filter-btn.active {{
    background: var(--bg-tertiary); color: var(--text-primary); border-color: var(--blue);
}}
.result-count {{ color: var(--text-muted); font-size: 13px; white-space: nowrap; }}

/* Table */
.table-container {{ max-width: 1400px; margin: 0 auto 20px; padding: 0 24px; overflow-x: auto; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; table-layout: fixed; }}
thead th {{
    background: var(--bg-secondary); padding: 10px 12px; text-align: right;
    font-weight: 600; font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.5px; color: var(--text-secondary);
    border-bottom: 2px solid var(--border); cursor: pointer;
    white-space: nowrap; user-select: none; position: sticky; top: 0; z-index: 50;
}}
thead th:first-child {{ text-align: left; }}
thead th:nth-child(2) {{ text-align: left; }}
thead th:hover {{ color: var(--blue); }}
thead th .sort-arrow {{ margin-left: 4px; opacity: 0.3; }}
thead th.sorted .sort-arrow {{ opacity: 1; color: var(--blue); }}
tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.15s; }}
tbody tr:hover {{ background: var(--bg-secondary); }}
tbody td {{
    padding: 10px 12px; text-align: right;
    font-family: 'SF Mono','Cascadia Code','Consolas',monospace;
    font-size: 13px; white-space: nowrap;
}}
tbody td:first-child {{ text-align: left; font-weight: 600; color: var(--blue); }}
tbody td:nth-child(2) {{
    text-align: left; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    color: var(--text-secondary); font-weight: 400; max-width: 180px;
    overflow: hidden; text-overflow: ellipsis;
}}
/* Mobile-only elements - hidden on desktop */
.mobile-vol {{ display: none; }}
.mobile-chg-abs {{ display: none; }}
.mobile-sort {{ display: none; }}

.positive {{ color: var(--green) !important; }}
.negative {{ color: var(--red) !important; }}
.change-cell {{
    font-weight: 600; padding: 2px 8px; border-radius: 4px;
    display: inline-block; min-width: 70px; text-align: right;
}}
.change-cell.positive {{ background: var(--green-bg); }}
.change-cell.negative {{ background: var(--red-bg); }}
.sector-cell {{
    font-family: -apple-system,sans-serif !important;
    font-size: 11px !important; color: var(--text-muted) !important;
    text-align: left !important; max-width: 120px;
    overflow: hidden; text-overflow: ellipsis;
}}
.cap-badge {{
    font-size: 10px; padding: 1px 6px; border-radius: 3px;
    font-family: sans-serif !important; display: inline-block;
}}
.cap-large {{ color: #58a6ff; background: rgba(88,166,255,0.12); }}
.cap-mid   {{ color: #bc8cff; background: rgba(188,140,255,0.12); }}
.cap-small {{ color: #d29922; background: rgba(210,153,34,0.12); }}
.cap-micro {{ color: #8b949e; background: rgba(139,148,158,0.1); }}

/* Pagination */
.pagination {{
    max-width: 1400px; margin: 0 auto 40px; padding: 0 24px;
    display: flex; justify-content: center; align-items: center; gap: 8px;
}}
.page-btn {{
    padding: 8px 14px; background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 6px; color: var(--text-secondary); font-size: 13px;
    cursor: pointer; transition: all 0.2s;
}}
.page-btn:hover {{ background: var(--bg-tertiary); color: var(--text-primary); }}
.page-btn.active {{ background: var(--blue); color: #fff; border-color: var(--blue); }}
.page-btn:disabled {{ opacity: 0.3; cursor: not-allowed; }}
.page-info {{ color: var(--text-muted); font-size: 13px; margin: 0 12px; }}

/* Footer */
.footer {{
    text-align: center; padding: 20px; color: var(--text-muted);
    font-size: 12px; border-top: 1px solid var(--border);
}}

/* Tab bar scrollable */
.price-tabs {{
    display: flex; gap: 8px; flex-wrap: wrap;
}}

/* Responsive */
@media (max-width: 768px) {{
    .movers-section {{ grid-template-columns: 1fr; }}
    .header-content {{ flex-direction: column; text-align: center; }}
    .stats-grid {{ flex-direction: row; flex-wrap: wrap; gap: 8px; }}
    .stat-card {{ min-width: 0; flex: 1 1 45%; padding: 8px 12px; }}
    .stat-card .label {{ font-size: 9px; }}
    .stat-card .value {{ font-size: 16px; }}
    .controls {{ flex-direction: column; padding: 0 12px !important; }}
    .search-box {{ min-width: 100%; }}
    .filter-bar {{ flex-direction: column; align-items: stretch; }}
    .filter-group {{ flex-wrap: wrap; }}
    .filter-divider {{ display: none; }}
    .pagination {{ display: none; }}

    /* Tab bar: horizontal scroll */
    .price-tabs {{
        flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch;
        gap: 6px; padding-bottom: 4px;
    }}
    .price-tabs .filter-btn {{ white-space: nowrap; flex-shrink: 0; font-size: 12px; padding: 8px 12px; }}

    /* Mobile sort dropdown */
    .mobile-sort {{ display: block; width: 100%; }}
    .mobile-sort .filter-select {{ width: 100%; }}

    /* Hide table header + non-card columns */
    table {{ table-layout: auto; border-collapse: separate; border-spacing: 0 6px; }}
    colgroup {{ display: none; }}
    thead {{ display: none !important; }}

    /* Each row becomes a card */
    tbody tr {{
        display: grid;
        grid-template-columns: 1fr auto;
        grid-template-rows: auto auto;
        background: var(--bg-secondary); border: 1px solid var(--border);
        border-radius: 10px; padding: 14px 16px; margin: 0;
        cursor: pointer; transition: background 0.15s;
        row-gap: 4px;
    }}
    tbody tr:hover {{ background: var(--bg-tertiary); }}

    /* Hide columns: Sector(3), Cap(4), Exch(5), Open(6), High(7), Low(8) */
    tbody td:nth-child(3),
    tbody td:nth-child(4),
    tbody td:nth-child(5),
    tbody td:nth-child(6),
    tbody td:nth-child(7),
    tbody td:nth-child(8) {{
        display: none !important;
    }}

    /* Row 1 Left: Symbol (bold, large) */
    tbody td:nth-child(1) {{
        grid-row: 1; grid-column: 1;
        text-align: left !important;
        font-size: 16px; font-weight: 700; color: var(--text-primary);
        padding: 0; border: none; white-space: nowrap;
        font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    }}
    tbody td:nth-child(1) span {{ display: none; }} /* hide chart icon on mobile */

    /* Row 1 Right: Close price (bold, large) */
    tbody td:nth-child(9) {{
        grid-row: 1; grid-column: 2;
        text-align: right !important;
        font-size: 16px; font-weight: 700; color: var(--text-primary);
        padding: 0; border: none;
        font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    }}

    /* Row 2 Left: Company name + Volume (small, muted) */
    tbody td:nth-child(2) {{
        grid-row: 2; grid-column: 1;
        text-align: left !important;
        font-size: 12px; color: var(--text-muted) !important;
        padding: 0; border: none; max-width: none;
        overflow: hidden; text-overflow: ellipsis;
    }}

    /* Row 2 Right: Change amount + Chg% */
    tbody td:nth-child(10) {{
        grid-row: 2; grid-column: 2;
        text-align: right !important;
        padding: 0; border: none;
        display: flex !important; align-items: center; justify-content: flex-end; gap: 6px;
    }}
    tbody td:nth-child(10) .change-cell {{
        font-size: 12px; min-width: auto; padding: 2px 6px;
    }}

    /* Change abs (col 11) - show inline next to chg% */
    tbody td:nth-child(11) {{
        display: none !important;
    }}

    /* Volume (col 12) - hide, show via JS in company cell */
    tbody td:nth-child(12) {{
        display: none !important;
    }}

    /* Show volume inline in company cell on mobile */
    .mobile-vol {{
        display: block; font-size: 11px; color: var(--text-muted);
        font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        margin-top: 2px;
    }}
    .company-name {{ display: block; }}
    /* Show change amount next to chg% */
    .mobile-chg-abs {{
        display: inline; font-size: 12px; margin-right: 6px;
        font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; font-weight: 600;
    }}
    tbody td:nth-child(10) .change-cell {{
        font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    }}

    .table-container {{ padding: 0 10px; overflow-x: visible; }}
    .global-filters {{ padding: 0 12px; }}
    .stats-bar {{ padding: 10px 12px; }}
    .movers-section {{ padding: 0 12px; }}

    /* Ticker smaller on mobile */
    .ticker-wrap {{ height: 36px; }}
    .ticker-item {{ font-size: 11px; padding: 0 12px; height: 36px; }}
}}

/* Ticker Zoom Button */
.ticker-zoom {{
    position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
    background: rgba(22,27,34,0.85); border: 1px solid var(--border);
    color: var(--text-secondary); font-size: 16px; cursor: pointer;
    width: 30px; height: 30px; border-radius: 6px; z-index: 10;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.2s;
}}
.ticker-zoom:hover {{ color: var(--blue); border-color: var(--blue); background: rgba(22,27,34,0.95); }}

/* Ticker Fullscreen Overlay */
.ticker-overlay {{
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: #000; z-index: 2000; display: none;
    flex-direction: column; justify-content: center; align-items: stretch;
}}
.ticker-overlay.active {{ display: flex; }}
.ticker-overlay-close {{
    position: absolute; top: 20px; right: 24px;
    background: none; border: none; color: #555; font-size: 32px;
    cursor: pointer; transition: color 0.2s; z-index: 2001;
}}
.ticker-overlay-close:hover {{ color: var(--red); }}
.ticker-overlay-track {{
    display: flex; width: max-content;
    animation: ticker-scroll var(--fs-ticker-duration, 180s) linear infinite;
}}
.ticker-overlay-track.paused {{ animation-play-state: paused; }}
.ticker-overlay:hover .ticker-overlay-track {{ animation-play-state: paused; }}
.ticker-overlay .fs-ticker-item {{
    display: flex; align-items: center; gap: 14px;
    padding: 0 40px; white-space: nowrap; height: 60px;
    font-size: 22px; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    border-right: 1px solid #1a1a1a;
}}
.ticker-overlay .fs-ticker-symbol {{ color: #e6edf3; font-weight: 700; }}
.ticker-overlay .fs-ticker-price  {{ color: #8b949e; }}
.ticker-overlay .fs-ticker-change {{ font-weight: 600; padding: 2px 10px; border-radius: 4px; }}
.ticker-overlay .fs-ticker-change.up   {{ color: var(--green); background: var(--green-bg); }}
.ticker-overlay .fs-ticker-change.down {{ color: var(--red);   background: var(--red-bg); }}
.ticker-overlay .fs-ticker-change.flat {{ color: #555; }}
.ticker-overlay-paused {{
    position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
    color: #555; font-size: 14px; letter-spacing: 2px; display: none;
}}
.ticker-overlay-paused.visible {{ display: block; }}
.ticker-overlay-controls {{
    position: absolute; bottom: 24px; left: 24px;
    display: flex; gap: 16px; align-items: center;
}}
.ticker-overlay-controls .ctrl-group {{
    display: flex; align-items: center; gap: 6px;
}}
.ticker-overlay-controls .ctrl-label {{
    color: #444; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
}}
.ticker-overlay-controls .ctrl-btn {{
    background: #1a1a1a; border: 1px solid #333; border-radius: 4px;
    color: #888; font-size: 16px; width: 28px; height: 28px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    transition: all 0.2s; line-height: 1;
}}
.ticker-overlay-controls .ctrl-btn:hover {{ color: var(--blue); border-color: var(--blue); }}
.ticker-overlay-controls .ctrl-val {{
    color: #666; font-size: 12px; min-width: 30px; text-align: center;
}}
.ticker-overlay-hints {{
    position: absolute; bottom: 30px; right: 24px;
    color: #333; font-size: 12px;
}}
.ticker-overlay-hints kbd {{
    background: #1a1a1a; border: 1px solid #333; border-radius: 3px;
    padding: 1px 6px; font-family: inherit; color: #555; margin: 0 2px;
}}
/* Ticker Overlay Stock Detail Panel */
.fs-stock-panel {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 12px; width: 92vw; max-width: 800px;
    max-height: 90vh; overflow-y: auto; z-index: 2010;
    display: none;
}}
.fs-stock-panel.active {{ display: block; }}
.fs-stock-backdrop {{
    position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.6); z-index: 2005; display: none;
}}
.fs-stock-backdrop.active {{ display: block; }}
.fs-panel-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 20px; border-bottom: 1px solid var(--border);
}}
.fs-panel-header .sym {{ font-size: 20px; font-weight: 700; color: var(--blue); }}
.fs-panel-header .name {{ color: var(--text-secondary); font-size: 14px; margin-left: 12px; }}
.fs-panel-close {{
    background: none; border: none; color: var(--text-muted);
    font-size: 28px; cursor: pointer; padding: 0 8px; transition: color 0.2s;
}}
.fs-panel-close:hover {{ color: var(--red); }}
.fs-panel-chart {{ height: 320px; padding: 8px; }}
.fs-panel-chart-legend {{
    padding: 8px 20px; font-size: 12px; color: var(--text-secondary);
    font-family: 'SF Mono','Consolas',monospace;
    border-bottom: 1px solid var(--border);
}}
.fs-panel-info {{
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 12px; padding: 16px; background: var(--bg-primary);
}}
.fund-card {{
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden;
}}
.fund-card-title {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    color: var(--text-muted); padding: 10px 14px 6px;
    border-bottom: 1px solid var(--border); font-weight: 600;
}}
.fund-card-body {{ padding: 4px 0; }}
.fund-row {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 14px; transition: background 0.15s;
}}
.fund-row:hover {{ background: rgba(255,255,255,0.03); }}
.fund-row .f-label {{ font-size: 12px; color: var(--text-secondary); }}
.fund-row .f-val {{ font-size: 13px; font-weight: 600; color: var(--text-primary); text-align: right; }}
.fund-row .f-val.green {{ color: var(--green); }}
.fund-row .f-val.red {{ color: var(--red); }}
.fund-row .f-val.blue {{ color: var(--blue); }}
.fund-row .f-val.gold {{ color: #f0b90b; }}
/* Key metric highlight */
.fund-row.key-metric {{
    background: rgba(88,166,255,0.06); border-left: 3px solid var(--blue);
    padding-left: 11px;
}}
.fund-row.key-metric .f-val {{ font-size: 15px; }}
/* Recommendation badge */
.rec-badge {{
    display: inline-block; padding: 3px 10px; border-radius: 4px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}}
.rec-buy {{ background: rgba(38,166,65,0.2); color: var(--green); border: 1px solid rgba(38,166,65,0.3); }}
.rec-hold {{ background: rgba(240,185,11,0.15); color: #f0b90b; border: 1px solid rgba(240,185,11,0.3); }}
.rec-sell {{ background: rgba(248,81,73,0.2); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }}
/* 52W range bar */
.range-bar-container {{ padding: 8px 14px; }}
.range-bar {{
    position: relative; height: 6px; background: linear-gradient(90deg, var(--red), #f0b90b, var(--green));
    border-radius: 3px; margin: 8px 0 4px;
}}
.range-dot {{
    position: absolute; top: -5px; width: 16px; height: 16px;
    background: var(--blue); border: 2px solid #fff; border-radius: 50%;
    transform: translateX(-50%); box-shadow: 0 0 8px rgba(88,166,255,0.5);
}}
.range-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); }}
.range-current {{ font-size: 14px; font-weight: 700; color: var(--text-primary); text-align: center; margin-top: 2px; }}
/* About section */
.fund-about {{
    padding: 12px 14px; font-size: 12px; color: var(--text-secondary);
    line-height: 1.5; border-top: 1px solid var(--border);
    max-height: 80px; overflow-y: auto;
}}
/* Tags */
.fs-panel-tags {{
    display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 16px;
}}
.fs-panel-tag {{
    font-size: 11px; padding: 4px 10px; border-radius: 12px;
    background: rgba(88,166,255,0.1); color: var(--blue);
    border: 1px solid rgba(88,166,255,0.2); font-weight: 500;
}}
.fs-panel-tag.sector {{ background: rgba(163,113,247,0.12); color: #a371f7; border-color: rgba(163,113,247,0.25); }}
.fs-panel-tag.cap {{ background: rgba(38,166,65,0.1); color: var(--green); border-color: rgba(38,166,65,0.2); }}
.fs-panel-tag.exchange {{ background: rgba(240,185,11,0.1); color: #f0b90b; border-color: rgba(240,185,11,0.2); }}

@media (max-width: 768px) {{
    .ticker-overlay .fs-ticker-item {{ font-size: 16px; padding: 0 20px; height: 48px; gap: 10px; }}
    .ticker-zoom {{ width: 26px; height: 26px; font-size: 13px; right: 4px; }}
    .fs-stock-panel {{ width: 98vw; border-radius: 8px; }}
    .fs-panel-chart {{ height: 240px; }}
    .fs-panel-info {{ grid-template-columns: 1fr; gap: 8px; padding: 8px; }}
}}

/* Chart Modal */
.chart-modal {{
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.85); z-index: 1000;
    display: flex; align-items: center; justify-content: center;
}}
.chart-modal-content {{
    background: var(--bg-secondary); border: 1px solid var(--border);
    border-radius: 12px; width: 92vw; max-width: 960px;
    max-height: 90vh; overflow: hidden;
}}
.chart-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 20px; border-bottom: 1px solid var(--border);
}}
.chart-symbol {{
    font-size: 18px; font-weight: 700; color: var(--blue);
    font-family: 'SF Mono','Consolas',monospace;
}}
.chart-name {{ color: var(--text-secondary); font-size: 14px; margin-left: 12px; }}
.chart-close {{
    background: none; border: none; color: var(--text-muted);
    font-size: 28px; cursor: pointer; padding: 0 8px; transition: color 0.2s;
}}
.chart-close:hover {{ color: var(--red); }}
.chart-container {{ height: 420px; padding: 8px; }}
.chart-legend {{
    padding: 10px 20px; border-top: 1px solid var(--border);
    font-size: 13px; color: var(--text-secondary);
    font-family: 'SF Mono','Consolas',monospace;
}}
.chart-loading {{
    display: flex; align-items: center; justify-content: center;
    height: 420px; color: var(--text-muted); font-size: 14px;
}}
@media (max-width: 768px) {{
    .chart-modal-content {{ width: 98vw; border-radius: 8px; }}
    .chart-container {{ height: 300px; }}
    .chart-loading {{ height: 300px; }}
    .chart-symbol {{ font-size: 15px; }}
    .chart-name {{ font-size: 12px; }}
}}

/* ============ Stock Detail Split-Panel View ============ */
.stock-detail-view {{
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: var(--bg-primary); z-index: 900;
    display: none; flex-direction: column;
}}
.stock-detail-view.active {{ display: flex; }}

.detail-ticker-bar {{
    height: 36px; background: #010409;
    border-bottom: 1px solid var(--border); flex-shrink: 0;
    position: relative;
}}
.detail-ticker-clip {{
    overflow: hidden; width: 100%; height: 100%;
}}
.detail-ticker-track {{
    display: flex; width: max-content;
    animation: ticker-scroll var(--detail-ticker-duration, 120s) linear infinite;
}}
.detail-ticker-clip:hover .detail-ticker-track {{ animation-play-state: paused; }}
.detail-ticker-track.paused {{ animation-play-state: paused; }}
/* Old detail-ticker-search CSS removed — using universal .ticker-search-box */
.detail-ticker-speed {{
    position: absolute; left: 8px; top: 4px; z-index: 5;
    display: flex; align-items: center; gap: 4px;
}}
.detail-ticker-speed button {{
    width: 24px; height: 24px; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary);
    cursor: pointer; font-size: 12px; display: flex; align-items: center; justify-content: center;
    transition: all 0.2s;
}}
.detail-ticker-speed button:hover {{ color: var(--blue); border-color: var(--blue); }}
.detail-ticker-speed .speed-label {{
    font-size: 10px; color: var(--text-muted); min-width: 24px; text-align: center;
}}
.detail-ticker-item {{
    display: flex; align-items: center; gap: 6px;
    padding: 0 16px; height: 36px; white-space: nowrap;
    font-size: 12px; font-family: 'SF Mono','Consolas',monospace;
    border-right: 1px solid var(--border); cursor: pointer;
    transition: background 0.15s;
}}
.detail-ticker-item:hover {{ background: rgba(88,166,255,0.08); }}
.detail-ticker-item.highlight {{
    background: rgba(88,166,255,0.2); box-shadow: 0 0 12px rgba(88,166,255,0.3);
    border-left: 2px solid var(--blue); border-right: 2px solid var(--blue);
    animation: highlight-pulse 0.6s ease-in-out 3;
}}
@keyframes highlight-pulse {{
    0%, 100% {{ background: rgba(88,166,255,0.15); }}
    50% {{ background: rgba(88,166,255,0.3); }}
}}
.detail-ticker-sym {{ color: var(--text-primary); font-weight: 600; }}
.detail-ticker-price {{ color: var(--text-secondary); }}
.detail-ticker-chg {{ font-weight: 600; font-size: 11px; padding: 1px 5px; border-radius: 3px; }}
.detail-ticker-chg.up   {{ color: var(--green); background: var(--green-bg); }}
.detail-ticker-chg.down {{ color: var(--red);   background: var(--red-bg); }}
.detail-ticker-chg.flat {{ color: var(--text-muted); }}

.detail-toolbar {{
    display: flex; align-items: center; gap: 12px;
    padding: 10px 20px; background: var(--bg-secondary);
    border-bottom: 1px solid var(--border); flex-shrink: 0;
}}
.detail-back-btn {{
    background: var(--bg-tertiary); border: 1px solid var(--border);
    color: var(--text-secondary); padding: 6px 14px; border-radius: 6px;
    cursor: pointer; font-size: 14px; transition: all 0.2s;
}}
.detail-back-btn:hover {{ color: var(--text-primary); border-color: var(--blue); }}
.detail-title {{ display: flex; align-items: baseline; gap: 8px; flex: 1; min-width: 0; }}
.detail-symbol {{ color: var(--blue); font-weight: 700; font-size: 18px; }}
.detail-name {{ color: var(--text-secondary); font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.detail-fs-buttons {{ display: flex; gap: 8px; flex-shrink: 0; }}
.detail-fs-btn {{
    background: var(--bg-tertiary); border: 1px solid var(--border);
    color: var(--text-muted); padding: 5px 10px; border-radius: 5px;
    cursor: pointer; font-size: 12px; transition: all 0.2s; white-space: nowrap;
}}
.detail-fs-btn:hover {{ color: var(--text-primary); border-color: var(--blue); }}

.detail-split {{
    flex: 1; display: flex; overflow: hidden; min-height: 0;
}}
.detail-data-pane {{
    width: 40%; flex-shrink: 0; overflow: hidden;
    display: flex; flex-direction: column;
    border-right: 1px solid var(--border);
}}
.detail-data-scroll {{
    flex: 1; overflow-y: auto;
}}
.detail-chart-pane {{
    flex: 1; display: flex; flex-direction: column; min-width: 0; padding-right: 8px;
}}
.detail-chart-container {{
    flex: 1; min-height: 0; overflow: hidden;
}}
.detail-chart-legend {{
    padding: 8px 16px; font-size: 12px; color: var(--text-secondary);
    font-family: 'SF Mono','Consolas',monospace;
    border-top: 1px solid var(--border); flex-shrink: 0;
}}

.detail-price-bar {{
    display: flex;
    gap: 16px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
}}
.detail-price-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
}}
.detail-price-label {{
    font-size: 9px;
    text-transform: uppercase;
    color: var(--text-muted);
    letter-spacing: 0.5px;
}}
.detail-price-val {{
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
}}
.detail-price-val.green {{ color: var(--green); }}
.detail-price-val.red {{ color: var(--red); }}

.detail-cards {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    padding: 12px;
}}
.detail-card {{
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0;
    overflow: hidden;
}}
.detail-card-header {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    padding: 8px 12px 6px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
}}
.detail-card-row {{
    display: flex;
    justify-content: space-between;
    padding: 5px 12px;
    font-size: 13px;
    border-bottom: 1px solid rgba(48,54,61,0.3);
}}
.detail-card-row:last-child {{
    border-bottom: none;
}}
.detail-card-label {{
    color: var(--text-muted);
    font-size: 11px;
}}
.detail-card-val {{
    color: var(--text-primary);
    font-weight: 600;
    font-size: 13px;
}}
.detail-card-val.green {{ color: var(--green); }}
.detail-card-val.red {{ color: var(--red); }}

.detail-range-bar {{
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    position: relative;
    margin: 8px 12px;
}}
.detail-range-marker {{
    position: absolute;
    width: 8px;
    height: 8px;
    background: var(--blue);
    border-radius: 50%;
    top: -2px;
}}
.detail-range-labels {{
    display: flex;
    justify-content: space-between;
    padding: 0 12px 8px;
    font-size: 11px;
    color: var(--text-muted);
}}

.detail-tags {{
    display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 14px;
    border-top: 1px solid var(--border);
}}
.detail-tags .fs-panel-tag {{
    font-size: 11px; padding: 3px 9px; border-radius: 4px;
    background: var(--bg-tertiary); color: var(--text-secondary);
    border: 1px solid var(--border);
}}
.detail-about {{
    padding: 12px 14px; border-top: 1px solid var(--border);
    font-size: 13px; color: var(--text-secondary); line-height: 1.6;
    max-height: 140px; overflow-y: auto;
}}
.detail-about:empty {{ display: none; }}

/* Fullscreen pane modes */
.detail-split.fs-chart .detail-data-pane {{ display: none; }}
.detail-split.fs-chart .detail-chart-pane {{ flex: 1; }}
.detail-split.fs-data .detail-chart-pane {{ display: none; }}
.detail-split.fs-data .detail-data-pane {{ width: 100%; border-right: none; }}

@media (max-width: 768px) {{
    .detail-split {{ flex-direction: column; }}
    .detail-data-pane {{ width: 100%; border-right: none; border-bottom: 1px solid var(--border); max-height: 45vh; }}
    .detail-chart-pane {{ min-height: 250px; }}
    .detail-toolbar {{ flex-wrap: wrap; gap: 8px; padding: 8px 12px; }}
    .detail-fs-buttons {{ width: 100%; justify-content: flex-end; }}
    .detail-symbol {{ font-size: 15px; }}
    .detail-name {{ font-size: 12px; }}
    .detail-cards {{ grid-template-columns: repeat(2, 1fr); gap: 8px; padding: 8px; }}
}}
</style>
<script src="https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>

<!-- Login Gate -->
<div id="login-gate" style="position:fixed;top:0;left:0;width:100%;height:100%;background:#0d1117;z-index:99999;display:flex;align-items:center;justify-content:center;">
    <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;padding:40px;width:340px;text-align:center;box-shadow:0 16px 48px rgba(0,0,0,0.5);">
        <div style="font-size:28px;font-weight:800;color:#58a6ff;margin-bottom:6px;font-family:'SF Mono','Consolas',monospace;letter-spacing:2px;">ISTOCKZ</div>
        <div style="font-size:12px;color:#8b949e;margin-bottom:28px;">Indian Stock Market Dashboard</div>
        <input id="login-pw" type="password" placeholder="Enter password"
            style="width:100%;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;font-size:14px;outline:none;box-sizing:border-box;margin-bottom:12px;transition:border-color 0.2s;"
            onfocus="this.style.borderColor='#58a6ff'" onblur="this.style.borderColor='#30363d'"
            onkeydown="if(event.key==='Enter')loginCheck()" />
        <button onclick="loginCheck()"
            style="width:100%;padding:12px;background:#238636;border:none;border-radius:8px;color:#fff;font-size:14px;font-weight:600;cursor:pointer;transition:background 0.2s;"
            onmouseover="this.style.background='#2ea043'" onmouseout="this.style.background='#238636'">
            Sign In
        </button>
        <div id="login-error" style="color:#f85149;font-size:12px;margin-top:12px;display:none;">Incorrect password</div>
    </div>
</div>
<script>
const _PH='a46e37e886f4931bddaa2c05d4a0d6531e614f0fdec369a3d86e0bf29ee4ca2f';
async function _sha(s){{const e=new TextEncoder().encode(s);const h=await crypto.subtle.digest('SHA-256',e);return Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('');}}
async function loginCheck(){{const pw=document.getElementById('login-pw').value;const h=await _sha(pw);if(h===_PH){{document.getElementById('login-gate').style.display='none';sessionStorage.setItem('_auth','1');}}else{{const err=document.getElementById('login-error');err.style.display='block';document.getElementById('login-pw').style.borderColor='#f85149';setTimeout(()=>{{err.style.display='none';}},3000);}}}}
if(sessionStorage.getItem('_auth')==='1'){{document.getElementById('login-gate').style.display='none';}}
</script>

<!-- Nav Menu -->
<div class="nav-backdrop" id="nav-backdrop" onclick="closeNavMenu()"></div>
<nav class="nav-menu" id="nav-menu">
    <div class="nav-header">
        <h3>Stock Groups</h3>
        <button class="nav-close" onclick="closeNavMenu()">&times;</button>
    </div>
    <div class="nav-section">
        <div class="nav-item nav-item-all active" onclick="applyNavFilter('all')">
            <span>All Stocks</span>
            <span class="nav-count" id="nav-count-all"></span>
        </div>
        <div class="nav-item" onclick="openIndicesPanel()" style="color:#58a6ff;font-weight:600;">
            <span>Market Indices</span>
            <span style="font-size:11px;color:#8b949e;">India + Global</span>
        </div>
    </div>
    <div class="nav-section" id="nav-cap-section">
        <div class="nav-section-title">Market Cap</div>
    </div>
    <div class="nav-section" id="nav-sector-section">
        <div class="nav-section-title">Sectors</div>
    </div>
    <div class="nav-section" id="nav-group-section">
        <div class="nav-section-title">Business Groups</div>
    </div>
    <div class="nav-section" id="nav-index-section">
        <div class="nav-section-title">Indices</div>
    </div>
</nav>

<!-- Header -->
<header class="header">
    <div class="header-content">
        <div class="logo">
            <button class="hamburger" id="hamburger" onclick="toggleNavMenu()">
                <span></span><span></span><span></span>
            </button>
            ISTOCKZ <span>Indian Stock Market &mdash; End-of-Day Prices</span>
        </div>
        <div class="header-meta">
            <div>Market Date: <strong id="market-date"></strong></div>
            <div>Generated: <span id="gen-time"></span></div>
        </div>
    </div>
</header>

<!-- Ticker Tape -->
<div class="ticker-wrap">
    <div class="ticker-track-clip">
        <div class="ticker-track" id="ticker-track"></div>
    </div>
    <div class="ticker-search-box" id="main-ticker-search">
        <input type="text" placeholder="&#128269; Search..." oninput="tickerSearch(this.value, 'main')" onfocus="tickerSearch(this.value, 'main')" autocomplete="off" />
        <div class="ticker-search-results" id="main-ticker-results"></div>
    </div>
    <button class="ticker-zoom" onclick="openTickerOverlay()" title="Fullscreen Ticker">&#x26F6;</button>
</div>

<!-- Ticker Fullscreen Overlay -->
<div class="ticker-overlay" id="ticker-overlay">
    <button class="ticker-overlay-close" onclick="closeTickerOverlay()">&times;</button>
    <div class="ticker-search-box fs-search" id="fs-ticker-search" style="position:absolute;top:16px;right:60px;z-index:100;">
        <input type="text" placeholder="&#128269; Search..." oninput="tickerSearch(this.value, 'fs')" onfocus="tickerSearch(this.value, 'fs')" autocomplete="off" />
        <div class="ticker-search-results" id="fs-ticker-results"></div>
    </div>
    <div style="overflow:hidden;width:100%;">
        <div class="ticker-overlay-track" id="fs-ticker-track"></div>
    </div>
    <div class="fs-stock-backdrop" id="fs-stock-backdrop" onclick="closeFsStockPanel()"></div>
    <div class="fs-stock-panel" id="fs-stock-panel">
        <div class="fs-panel-header">
            <div><span class="sym" id="fs-panel-sym"></span><span class="name" id="fs-panel-name"></span></div>
            <button class="fs-panel-close" onclick="closeFsStockPanel()">&times;</button>
        </div>
        <div class="fs-panel-chart" id="fs-panel-chart">
            <div style="display:flex;align-items:center;justify-content:center;height:100%;color:#555;">Loading chart...</div>
        </div>
        <div class="fs-panel-chart-legend" id="fs-panel-legend"></div>
        <div class="fs-panel-info" id="fs-panel-info"></div>
        <div class="fs-panel-tags" id="fs-panel-tags"></div>
    </div>
    <div class="ticker-overlay-paused" id="fs-paused-label">&#9654; PAUSED</div>
    <div class="ticker-overlay-controls">
        <div class="ctrl-group">
            <span class="ctrl-label">Speed</span>
            <button class="ctrl-btn" onclick="changeTickerSpeed(-1)">&#x2212;</button>
            <span class="ctrl-val" id="fs-speed-val">1x</span>
            <button class="ctrl-btn" onclick="changeTickerSpeed(1)">+</button>
        </div>
        <div class="ctrl-group">
            <span class="ctrl-label">Size</span>
            <button class="ctrl-btn" onclick="changeTickerFontSize(-1)">A&#x2212;</button>
            <span class="ctrl-val" id="fs-font-val">M</span>
            <button class="ctrl-btn" onclick="changeTickerFontSize(1)">A+</button>
        </div>
    </div>
    <div class="ticker-overlay-hints">
        <kbd>Space</kbd> Pause &nbsp; <kbd>F</kbd> Fullscreen &nbsp; <kbd>Esc</kbd> Close
    </div>
</div>

<!-- Stats Bar -->
<div class="stats-bar">
    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Total Stocks</div>
            <div class="value blue" id="stat-total"></div>
        </div>
        <div class="stat-card">
            <div class="label">Advancers</div>
            <div class="value green" id="stat-gainers"></div>
        </div>
        <div class="stat-card">
            <div class="label">Decliners</div>
            <div class="value red" id="stat-losers"></div>
        </div>
        <div class="stat-card">
            <div class="label">Unchanged</div>
            <div class="value" id="stat-unchanged"></div>
        </div>
        <div class="stat-card">
            <div class="label">Avg Change</div>
            <div class="value" id="stat-avg"></div>
        </div>
    </div>
</div>

<!-- Global Filter Bar -->
<div class="global-filters">
    <div class="filter-bar">
        <div class="filter-group">
            <label>Sector</label>
            <select class="filter-select" id="filter-sector" onchange="onGlobalFilter()">
                <option value="all">All Sectors</option>
            </select>
        </div>
        <div class="filter-divider"></div>
        <div class="filter-group">
            <label>Market Cap</label>
            <select class="filter-select" id="filter-cap" onchange="onGlobalFilter()">
                <option value="all">All Market Cap</option>
            </select>
        </div>
        <div class="filter-divider"></div>
        <div class="filter-group">
            <label>Exchange</label>
            <select class="filter-select" id="filter-exchange" onchange="onGlobalFilter()">
                <option value="all">All Exchanges</option>
                <option value="NSE">NSE</option>
                <option value="BSE">BSE</option>
            </select>
        </div>
        <button class="filter-reset" id="reset-btn" onclick="resetFilters()">Reset All</button>
        <span class="active-filter-tag" id="active-tag" style="display:none"></span>
    </div>
</div>

<!-- Top Movers -->
<div class="movers-section">
    <div class="mover-card">
        <h3 class="gainers" id="movers-gain-title">Top 5 Gainers</h3>
        <ul class="mover-list" id="top-gainers"></ul>
    </div>
    <div class="mover-card">
        <h3 class="losers" id="movers-lose-title">Top 5 Losers</h3>
        <ul class="mover-list" id="top-losers"></ul>
    </div>
</div>

<!-- Controls (search + price filter) -->
<div class="controls">
    <div class="search-box">
        <svg viewBox="0 0 24 24"><path d="M10 2a8 8 0 105.3 14.7l4.5 4.5a1 1 0 001.4-1.4l-4.5-4.5A8 8 0 0010 2zm0 2a6 6 0 110 12 6 6 0 010-12z"/></svg>
        <input type="text" id="search" placeholder="Search by symbol or company name..." autocomplete="off">
    </div>
    <div class="price-tabs">
        <button class="filter-btn active" id="btn-all" onclick="setPriceFilter('all')">All</button>
        <button class="filter-btn" id="btn-gainers" onclick="setPriceFilter('gainers')">Gainers</button>
        <button class="filter-btn" id="btn-losers" onclick="setPriceFilter('losers')">Losers</button>
        <button class="filter-btn" id="btn-volume" onclick="setPriceFilter('volume')">By Volume</button>
        <button class="filter-btn" id="btn-value" onclick="setPriceFilter('value')">By Value</button>
    </div>
    <div class="mobile-sort" id="mobile-sort">
        <select class="filter-select" id="mobile-sort-select" onchange="mobileSort(this.value)">
            <option value="symbol-asc">Name A-Z</option>
            <option value="symbol-desc">Name Z-A</option>
            <option value="close-desc">Price High-Low</option>
            <option value="close-asc">Price Low-High</option>
            <option value="change_pct_abs-desc" selected>Change% Max</option>
            <option value="change_pct_abs-asc">Change% Min</option>
            <option value="volume-desc">Volume High-Low</option>
        </select>
    </div>
    <span class="result-count" id="result-count"></span>
</div>

<!-- Table -->
<div class="table-container">
    <table>
        <colgroup>
            <col style="width:8%">
            <col style="width:14%">
            <col style="width:9%">
            <col style="width:6%">
            <col style="width:5%">
            <col style="width:8%">
            <col style="width:8%">
            <col style="width:8%">
            <col style="width:8%">
            <col style="width:7%">
            <col style="width:7%">
            <col style="width:8%">
        </colgroup>
        <thead>
            <tr>
                <th data-col="symbol" onclick="sortTable('symbol')">Symbol <span class="sort-arrow">&#9650;</span></th>
                <th data-col="name" onclick="sortTable('name')">Company <span class="sort-arrow">&#9650;</span></th>
                <th data-col="sector" onclick="sortTable('sector')">Sector <span class="sort-arrow">&#9650;</span></th>
                <th data-col="market_cap_cat" onclick="sortTable('market_cap_cat')">Cap <span class="sort-arrow">&#9650;</span></th>
                <th data-col="exchange" onclick="sortTable('exchange')">Exch <span class="sort-arrow">&#9650;</span></th>
                <th data-col="open" onclick="sortTable('open')">Open <span class="sort-arrow">&#9650;</span></th>
                <th data-col="high" onclick="sortTable('high')">High <span class="sort-arrow">&#9650;</span></th>
                <th data-col="low" onclick="sortTable('low')">Low <span class="sort-arrow">&#9650;</span></th>
                <th data-col="close" onclick="sortTable('close')">Close <span class="sort-arrow">&#9650;</span></th>
                <th data-col="change_pct" onclick="sortTable('change_pct')">Chg% <span class="sort-arrow">&#9650;</span></th>
                <th data-col="change_abs" onclick="sortTable('change_abs')">Change <span class="sort-arrow">&#9650;</span></th>
                <th data-col="volume" onclick="sortTable('volume')">Volume <span class="sort-arrow">&#9650;</span></th>
            </tr>
        </thead>
        <tbody id="stock-table"></tbody>
    </table>
</div>

<!-- Pagination -->
<div class="pagination" id="pagination"></div>

<!-- Chart Modal -->
<div class="chart-modal" id="chart-modal" style="display:none">
    <div class="chart-modal-content">
        <div class="chart-header">
            <div>
                <span class="chart-symbol" id="chart-symbol"></span>
                <span class="chart-name" id="chart-name"></span>
            </div>
            <button class="chart-close" id="chart-close" onclick="closeChart()">&times;</button>
        </div>
        <div class="chart-container" id="chart-container"></div>
        <div class="chart-legend" id="chart-legend"></div>
    </div>
</div>

<!-- Footer -->
<div class="footer">
    Istockz &mdash; Indian Stock Market EOD Analysis &bull; Data from Yahoo Finance via yfinance &bull; For educational purposes only
</div>

<!-- Stock Detail Split-Panel View -->
<div id="stock-detail-view" class="stock-detail-view">
    <div class="detail-ticker-bar" id="detail-ticker-bar">
        <div class="detail-ticker-speed">
            <button onclick="changeDetailSpeed(-1)">&#9664;</button>
            <span class="speed-label" id="detail-speed-label">1x</span>
            <button onclick="changeDetailSpeed(1)">&#9654;</button>
        </div>
        <div class="detail-ticker-clip">
            <div class="detail-ticker-track" id="detail-ticker-track"></div>
        </div>
        <div class="ticker-search-box" id="detail-ticker-search" style="right:8px;top:4px;transform:none;">
            <input type="text" id="detail-ticker-search-input" placeholder="&#128269; Search..."
                   oninput="tickerSearch(this.value, 'detail')"
                   onfocus="tickerSearch(this.value, 'detail')"
                   autocomplete="off" />
            <div class="ticker-search-results" id="detail-ticker-results"></div>
        </div>
    </div>
    <div class="detail-toolbar">
        <button class="detail-back-btn" onclick="closeStockDetail()">&#8592; Back</button>
        <div class="detail-title">
            <span class="detail-symbol" id="detail-symbol"></span>
            <span class="detail-name" id="detail-name"></span>
        </div>
        <div class="detail-fs-buttons">
            <button class="detail-fs-btn" onclick="detailFullscreen('both')" title="Fullscreen Both">&#x26F6; Full</button>
            <button class="detail-fs-btn" onclick="detailFullscreen('data')" title="Fullscreen Data">&#128202; Data FS</button>
            <button class="detail-fs-btn" onclick="detailFullscreen('chart')" title="Fullscreen Chart">&#128200; Chart FS</button>
        </div>
    </div>
    <div class="detail-split" id="detail-split">
        <div class="detail-data-pane" id="detail-data-pane">
            <div class="detail-data-scroll">
                <div class="detail-price-bar" id="detail-price-bar"></div>
                <div class="detail-cards" id="detail-cards"></div>
                <div class="detail-tags" id="detail-tags"></div>
                <div class="detail-about" id="detail-about"></div>
            </div>
        </div>
        <div class="detail-chart-pane" id="detail-chart-pane">
            <div class="detail-chart-container" id="detail-chart-container"></div>
            <div class="detail-chart-legend" id="detail-chart-legend"></div>
        </div>
    </div>
</div>

<script>
// ==========================================
// EMBEDDED DATA
// ==========================================
const ALL_STOCKS   = {prices_json};
const ORIG_STATS   = {stats_json};
const SECTORS_LIST = {sectors_json};
const CAPS_LIST    = {caps_json};

// ==========================================
// BUSINESS GROUPS (Indian conglomerates)
// ==========================================
const BUSINESS_GROUPS = {{
    'Tata Group': ['TATACONSUM','TATACHEM','TATACOMM','TATAELXSI','TATAINVEST','TATAMOTORS','TATAMTRDVR','TATAPOWER','TATASTEEL','TATASPONGE','TATATECH','TCS','TITAN','VOLTAS','IHCL','TRENT','NELCO','RALLIS','TMRVL','TATASTEELLP','TATASTLLP','TATAMETALI','TATACONSUM','TINPLATE'],
    'Adani Group': ['ADANIENT','ADANIGREEN','ADANIPORTS','ADANIPOWER','ADANITRANS','ATGL','AWL','ADANIENSOL','ADANIWILMAR','NDTV','ACC','AMBUJACEMENT'],
    'Reliance Group': ['RELIANCE','JIOFIN','JUST DIAL','RELINFRA','RPOWER','RCOM','RNAVAL'],
    'Birla Group': ['GRASIM','ULTRATECH','HINDALCO','ABCAPITAL','ABFRL','ABSLAMC','CENTURYTEX','CENTURY'],
    'Bajaj Group': ['BAJAJ-AUTO','BAJAJFINSV','BAJFINANCE','BAJAJHLDNG','BAJAJCON','BAJAJELEC','BAJAJHFL'],
    'Mahindra Group': ['M&M','MAHINDCIE','MHRIL','TECHM','MAHLOG','MAHLIFE','MAHSCOOTER','MFSL'],
    'Godrej Group': ['GODREJCP','GODREJPROP','GODREJIND','GODREJAGRO','ASTEC'],
    'JSW Group': ['JSWSTEEL','JSPL','JSWENERGY','JSWINFRA','JSWHL'],
    'Vedanta Group': ['VEDL','HINDZINC','STERLITE','SESAGOA'],
    'L&T Group': ['LT','LTTS','LTIM','LTTECHFIN','LTFOODS'],
    'HDFC Group': ['HDFCBANK','HDFCLIFE','HDFCAMC','HDFCERGO'],
    'ICICI Group': ['ICICIBANK','ICICIGI','ICICIPRULI','ICICISEC'],
    'SBI Group': ['SBIN','SBILIFE','SBICARD','SBICAP'],
    'Kotak Group': ['KOTAKBANK','KOTAKMAH'],
    'Wipro Group': ['WIPRO'],
    'Infosys Group': ['INFY'],
    'ITC Group': ['ITC','ITCHOTELS'],
    'Aditya Birla Group': ['ABCAPITAL','ABFRL','GRASIM','HINDALCO','ULTRATECH','VODAFONE','IDEA'],
    'Murugappa Group': ['TIINDIA','CGTL','CHOLAMANDALAM','CARBORUNIV','SHANTHI'],
    'TVS Group': ['TVSMOTOR','TVSSRICHAK','TVSELECT','SUNDRMFAST'],
    'Hero Group': ['HEROMOTOCO','HEROPROP'],
    'Piramal Group': ['PEL','PIRPHYTO','PIRAMAL'],
    'Hindustan Unilever': ['HINDUNILVR'],
    'Bharti Group': ['BHARTIARTL','BHARTIHEXA'],
    'PSU Companies': ['SBIN','BANKBARODA','PNB','CANBK','UNIONBANK','IOB','CENTRALBK','UCOBANK','INDIANB','MAHABANK','BANKINDIA','PSB','COALINDIA','ONGC','IOC','BPCL','HPCL','GAIL','NTPC','POWERGRID','NHPC','SJVN','IREDA','PFC','RECLTD','IRFC','IRCTC','RVNL','NBCC','BEL','HAL','BDL','BHEL','BEML','CONCOR','NMDC','NALCO','SAIL','HINDCOPPER','MOIL','NFL','RCF','FACT','HUDCO','NLC','OIL','MRPL','CHENNPETRO','MIDHANI','GRSE','COCHINSHIP','GSL','MAZAGON','GARDENREACH','ITI','MTNL','NATIONALUM','HINDZINC','VEDL','ENGINERSIN','RITES','RAILTEL','IREL','KIOCL'],
}};

// Nifty index constituents (approximate - top stocks)
const INDEX_GROUPS = {{
    'Nifty 50': ['ADANIENT','ADANIPORTS','APOLLOHOSP','ASIANPAINT','AXISBANK','BAJAJ-AUTO','BAJFINANCE','BAJAJFINSV','BPCL','BHARTIARTL','BRITANNIA','CIPLA','COALINDIA','DIVISLAB','DRREDDY','EICHERMOT','GRASIM','HCLTECH','HDFCBANK','HDFCLIFE','HEROMOTOCO','HINDALCO','HINDUNILVR','ICICIBANK','ITC','INDUSINDBK','INFY','JSWSTEEL','KOTAKBANK','LT','M&M','MARUTI','NTPC','NESTLEIND','ONGC','POWERGRID','RELIANCE','SBILIFE','SBIN','SUNPHARMA','TCS','TATACONSUM','TATAMOTORS','TATASTEEL','TECHM','TITAN','ULTRACEMCO','WIPRO','SHRIRAMFIN','TRENT'],
    'Bank Nifty': ['HDFCBANK','ICICIBANK','KOTAKBANK','AXISBANK','SBIN','INDUSINDBK','BANDHANBNK','AUBANK','IDFCFIRSTB','FEDERALBNK','PNB','BANKBARODA'],
}};

// ==========================================
// STATE
// ==========================================
let navFilterActive = null;  // Current nav group filter
let globalFiltered = [...ALL_STOCKS];   // After sector/cap/exchange dropdown
let filteredData   = [...ALL_STOCKS];   // After search + price filter too
let currentPage = 1;
const PAGE_SIZE = 50;
let isLoadingMore = false;
let isMobile = window.innerWidth <= 768;
let sortCol = 'symbol';
let sortDir = 'asc';
let priceFilter = 'all'; // all | gainers | losers

// Current dropdown values
let activeSector   = 'all';
let activeCap      = 'all';
let activeExchange = 'all';

// ==========================================
// INIT
// ==========================================
document.addEventListener('DOMContentLoaded', () => {{
    populateDropdowns();
    buildNavMenu();
    applyGlobalFilter();
    document.getElementById('search').addEventListener('input', () => {{ currentPage = 1; applyLocalFilters(); }});

    // Infinite scroll for mobile
    window.addEventListener('scroll', () => {{
        if (!isMobile || isLoadingMore) return;
        const scrollBottom = window.innerHeight + window.scrollY;
        const docHeight = document.documentElement.scrollHeight;
        if (scrollBottom >= docHeight - 300) {{
            const totalPages = Math.ceil(filteredData.length / PAGE_SIZE);
            if (currentPage < totalPages) {{
                isLoadingMore = true;
                currentPage++;
                appendTablePage();
                isLoadingMore = false;
            }}
        }}
    }});
    window.addEventListener('resize', () => {{ isMobile = window.innerWidth <= 768; }});
}});

// ==========================================
// POPULATE DROPDOWN OPTIONS
// ==========================================
function populateDropdowns() {{
    const sectorSel = document.getElementById('filter-sector');
    SECTORS_LIST.forEach(s => {{
        const opt = document.createElement('option');
        opt.value = s; opt.textContent = s;
        sectorSel.appendChild(opt);
    }});

    const capSel = document.getElementById('filter-cap');
    CAPS_LIST.forEach(c => {{
        const opt = document.createElement('option');
        opt.value = c; opt.textContent = c;
        capSel.appendChild(opt);
    }});
}}

// ==========================================
// NAV MENU (hamburger)
// ==========================================
function toggleNavMenu() {{
    const menu = document.getElementById('nav-menu');
    const backdrop = document.getElementById('nav-backdrop');
    const hamburger = document.getElementById('hamburger');
    menu.classList.toggle('open');
    backdrop.classList.toggle('open');
    hamburger.classList.toggle('active');
}}
function closeNavMenu() {{
    document.getElementById('nav-menu').classList.remove('open');
    document.getElementById('nav-backdrop').classList.remove('open');
    document.getElementById('hamburger').classList.remove('active');
}}

function buildNavMenu() {{
    // Count stocks per group
    function countMatch(filterFn) {{
        return ALL_STOCKS.filter(filterFn).length;
    }}
    function symClean(s) {{ return s.symbol.replace('.NS','').replace('.BO',''); }}

    // All stocks count
    document.getElementById('nav-count-all').textContent = ALL_STOCKS.length;

    // Market Cap section
    const capSection = document.getElementById('nav-cap-section');
    const capIcons = {{ 'Large Cap': '\u25c9', 'Mid Cap': '\u25ce', 'Small Cap': '\u25cb', 'Micro Cap': '\u00b7' }};
    CAPS_LIST.forEach(cap => {{
        const count = countMatch(s => s.market_cap_cat === cap);
        if (count === 0) return;
        const div = document.createElement('div');
        div.className = 'nav-item';
        div.setAttribute('data-filter', 'cap:' + cap);
        div.innerHTML = `<span>${{capIcons[cap] || ''}} ${{cap}}</span><span class="nav-count">${{count}}</span>`;
        div.onclick = () => applyNavFilter('cap:' + cap);
        capSection.appendChild(div);
    }});

    // Sectors section
    const secSection = document.getElementById('nav-sector-section');
    const secIcons = {{}};
    SECTORS_LIST.forEach(sec => {{
        const count = countMatch(s => s.sector === sec);
        if (count === 0) return;
        const div = document.createElement('div');
        div.className = 'nav-item';
        div.setAttribute('data-filter', 'sector:' + sec);
        div.innerHTML = `<span>${{sec}}</span><span class="nav-count">${{count}}</span>`;
        div.onclick = () => applyNavFilter('sector:' + sec);
        secSection.appendChild(div);
    }});

    // Business Groups section
    const grpSection = document.getElementById('nav-group-section');
    Object.keys(BUSINESS_GROUPS).sort().forEach(grp => {{
        const symbols = BUSINESS_GROUPS[grp];
        const count = countMatch(s => symbols.includes(symClean(s)));
        if (count === 0) return;
        const div = document.createElement('div');
        div.className = 'nav-item';
        div.setAttribute('data-filter', 'group:' + grp);
        div.innerHTML = `<span>${{grp}}</span><span class="nav-count">${{count}}</span>`;
        div.onclick = () => applyNavFilter('group:' + grp);
        grpSection.appendChild(div);
    }});

    // Index Groups section
    const idxSection = document.getElementById('nav-index-section');
    Object.keys(INDEX_GROUPS).forEach(idx => {{
        const symbols = INDEX_GROUPS[idx];
        const count = countMatch(s => symbols.includes(symClean(s)));
        if (count === 0) return;
        const div = document.createElement('div');
        div.className = 'nav-item';
        div.setAttribute('data-filter', 'index:' + idx);
        div.innerHTML = `<span>${{idx}}</span><span class="nav-count">${{count}}</span>`;
        div.onclick = () => applyNavFilter('index:' + idx);
        idxSection.appendChild(div);
    }});
}}

function applyNavFilter(filter) {{
    navFilterActive = filter;

    // Update active state in nav
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    if (filter === 'all') {{
        document.querySelector('.nav-item-all').classList.add('active');
    }} else {{
        const target = document.querySelector(`.nav-item[data-filter="${{filter}}"]`);
        if (target) target.classList.add('active');
    }}

    // Reset dropdown filters when changing nav group
    document.getElementById('filter-sector').value = 'all';
    document.getElementById('filter-cap').value = 'all';
    document.getElementById('filter-exchange').value = 'all';
    activeSector = 'all'; activeCap = 'all'; activeExchange = 'all';

    currentPage = 1;
    applyGlobalFilter();
    closeNavMenu();
}}

// ==========================================
// GLOBAL FILTER (sector / cap / exchange)
// Affects: ticker, stats, movers, table
// ==========================================
function onGlobalFilter() {{
    activeSector   = document.getElementById('filter-sector').value;
    activeCap      = document.getElementById('filter-cap').value;
    activeExchange = document.getElementById('filter-exchange').value;
    currentPage = 1;
    applyGlobalFilter();
}}

function resetFilters() {{
    document.getElementById('filter-sector').value   = 'all';
    document.getElementById('filter-cap').value      = 'all';
    document.getElementById('filter-exchange').value  = 'all';
    document.getElementById('search').value = '';
    priceFilter = 'all';
    activeSector = 'all'; activeCap = 'all'; activeExchange = 'all';
    navFilterActive = null;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector('.nav-item-all').classList.add('active');
    ['btn-all','btn-gainers','btn-losers','btn-volume','btn-value'].forEach(id => document.getElementById(id).classList.remove('active'));
    document.getElementById('btn-all').classList.add('active');
    currentPage = 1;
    applyGlobalFilter();
}}

function applyGlobalFilter() {{
    // Step 0: apply nav menu group filter first
    let base = ALL_STOCKS;
    if (navFilterActive && navFilterActive !== 'all') {{
        const f = navFilterActive;
        if (f.startsWith('cap:')) {{
            const cap = f.replace('cap:','');
            base = ALL_STOCKS.filter(s => s.market_cap_cat === cap);
        }} else if (f.startsWith('sector:')) {{
            const sec = f.replace('sector:','');
            base = ALL_STOCKS.filter(s => s.sector === sec);
        }} else if (f.startsWith('group:')) {{
            const grp = f.replace('group:','');
            const symbols = BUSINESS_GROUPS[grp] || [];
            base = ALL_STOCKS.filter(s => {{
                const sym = s.symbol.replace('.NS','').replace('.BO','');
                return symbols.includes(sym);
            }});
        }} else if (f.startsWith('index:')) {{
            const idx = f.replace('index:','');
            const symbols = INDEX_GROUPS[idx] || [];
            base = ALL_STOCKS.filter(s => {{
                const sym = s.symbol.replace('.NS','').replace('.BO','');
                return symbols.includes(sym);
            }});
        }}
    }}

    // Step 1: filter by dropdowns
    globalFiltered = base.filter(s => {{
        if (activeSector !== 'all' && s.sector !== activeSector) return false;
        if (activeCap !== 'all' && s.market_cap_cat !== activeCap) return false;
        if (activeExchange !== 'all' && !(s.exchange || '').includes(activeExchange)) return false;
        return true;
    }});

    // Update active tag
    const parts = [];
    if (navFilterActive && navFilterActive !== 'all') {{
        const f = navFilterActive;
        if (f.startsWith('cap:')) parts.push(f.replace('cap:',''));
        else if (f.startsWith('sector:')) parts.push(f.replace('sector:',''));
        else if (f.startsWith('group:')) parts.push(f.replace('group:',''));
        else if (f.startsWith('index:')) parts.push(f.replace('index:',''));
    }}
    if (activeSector !== 'all') parts.push(activeSector);
    if (activeCap !== 'all') parts.push(activeCap);
    if (activeExchange !== 'all') parts.push(activeExchange);
    const tag = document.getElementById('active-tag');
    if (parts.length > 0) {{
        tag.style.display = 'inline-block';
        tag.textContent = parts.join(' + ');
    }} else {{
        tag.style.display = 'none';
    }}

    // Rebuild everything from globalFiltered
    renderTicker(globalFiltered);
    renderStats(globalFiltered);
    renderMovers(globalFiltered);
    applyLocalFilters();
}}

// ==========================================
// LOCAL FILTERS (search + price)
// Applies on top of globalFiltered
// ==========================================
function setPriceFilter(f) {{
    priceFilter = f;
    currentPage = 1;
    ['btn-all','btn-gainers','btn-losers','btn-volume','btn-value'].forEach(id => document.getElementById(id).classList.remove('active'));
    document.getElementById('btn-' + f).classList.add('active');
    applyLocalFilters();
}}

function applyLocalFilters() {{
    const q = document.getElementById('search').value.toLowerCase().trim();
    filteredData = globalFiltered.filter(s => {{
        if (q && !s.symbol.toLowerCase().includes(q) && !(s.name || '').toLowerCase().includes(q)) return false;
        if (priceFilter === 'gainers' && s.change_pct <= 0) return false;
        if (priceFilter === 'losers'  && s.change_pct >= 0) return false;
        return true;
    }});

    // Special sort modes for By Volume and By Value
    if (priceFilter === 'volume') {{
        filteredData.sort((a, b) => (b.volume || 0) - (a.volume || 0));
        renderTable();
        renderPagination();
        return;
    }}
    if (priceFilter === 'value') {{
        filteredData.sort((a, b) => ((b.close || 0) * (b.volume || 0)) - ((a.close || 0) * (a.volume || 0)));
        renderTable();
        renderPagination();
        return;
    }}

    applySort();
}}

// ==========================================
// TICKER TAPE (rebuilt on global filter)
// ==========================================
function renderTicker(data) {{
    const track = document.getElementById('ticker-track');
    if (data.length === 0) {{ track.innerHTML = ''; return; }}
    const items = data.map(s => {{
        const sym = s.symbol.replace('.NS','').replace('.BO','');
        const sign = s.change_pct >= 0 ? '+' : '';
        const cls = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat';
        const escaped = s.symbol.replace(/'/g, "\\\\'");
        return `<div class="ticker-item" data-symbol="${{s.symbol}}" style="cursor:pointer;" onclick="openStockDetail('${{escaped}}')">`
            + `<span class="ticker-symbol">${{sym}}</span>`
            + `<span class="ticker-price">${{fmt(s.close)}}</span>`
            + `<span class="ticker-change ${{cls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span>`
            + `</div>`;
    }}).join('');
    track.innerHTML = items + items;
    const dur = Math.max(30, data.length * 0.8);
    track.parentElement.style.setProperty('--ticker-duration', dur + 's');
}}

// ==========================================
// STATS (recomputed from filtered data)
// ==========================================
function renderStats(data) {{
    document.getElementById('market-date').textContent = ORIG_STATS.date;
    document.getElementById('gen-time').textContent = ORIG_STATS.generated_at;

    const total = data.length;
    const gainers = data.filter(s => s.change_pct > 0).length;
    const losers  = data.filter(s => s.change_pct < 0).length;
    const unchanged = total - gainers - losers;
    const avg = total ? data.reduce((s,x) => s + x.change_pct, 0) / total : 0;

    document.getElementById('stat-total').textContent = total.toLocaleString();
    document.getElementById('stat-gainers').textContent = gainers.toLocaleString();
    document.getElementById('stat-losers').textContent = losers.toLocaleString();
    document.getElementById('stat-unchanged').textContent = unchanged.toLocaleString();

    const avgEl = document.getElementById('stat-avg');
    avgEl.textContent = (avg >= 0 ? '+' : '') + avg.toFixed(2) + '%';
    avgEl.className = 'value ' + (avg >= 0 ? 'green' : 'red');
}}

// ==========================================
// TOP MOVERS (recomputed from filtered data)
// ==========================================
function renderMovers(data) {{
    const sorted = [...data].sort((a,b) => b.change_pct - a.change_pct);
    const topG = sorted.slice(0, 5);
    const topL = sorted.slice(-5).reverse();
    document.getElementById('top-gainers').innerHTML = topG.map(s => moverHTML(s)).join('');
    document.getElementById('top-losers').innerHTML  = topL.map(s => moverHTML(s)).join('');
}}

function moverHTML(s) {{
    const cls = s.change_pct >= 0 ? 'positive' : 'negative';
    const sign = s.change_pct >= 0 ? '+' : '';
    const sym = s.symbol.replace('.NS','').replace('.BO','');
    const name = s.name || sym;
    return `<li class="mover-item">
        <div><span class="mover-symbol">${{sym}}</span><span class="mover-name">${{name}}</span></div>
        <span class="mover-change ${{cls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span>
    </li>`;
}}

// ==========================================
// SORT
// ==========================================
function sortTable(col) {{
    if (sortCol === col) {{ sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }}
    else {{ sortCol = col; sortDir = (col === 'symbol' || col === 'name' || col === 'sector') ? 'asc' : 'desc'; }}
    document.querySelectorAll('thead th').forEach(th => {{
        th.classList.remove('sorted');
        th.querySelector('.sort-arrow').innerHTML = '&#9650;';
    }});
    const activeTh = document.querySelector(`thead th[data-col="${{sortCol}}"]`);
    if (activeTh) {{
        activeTh.classList.add('sorted');
        activeTh.querySelector('.sort-arrow').innerHTML = sortDir === 'asc' ? '&#9650;' : '&#9660;';
    }}
    applySort();
}}

function mobileSort(val) {{
    const [col, dir] = val.split('-');
    sortCol = col;
    sortDir = dir;
    currentPage = 1;
    applySort();
}}

function applySort() {{
    filteredData.sort((a, b) => {{
        let va, vb;
        if (sortCol === 'change_pct_abs') {{
            va = Math.abs(a.change_pct || 0);
            vb = Math.abs(b.change_pct || 0);
        }} else {{
            va = a[sortCol]; vb = b[sortCol];
        }}
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return sortDir === 'asc' ? -1 : 1;
        if (va > vb) return sortDir === 'asc' ? 1 : -1;
        return 0;
    }});
    renderTable();
    renderPagination();
}}

// ==========================================
// TABLE
// ==========================================
function appendTablePage() {{
    const start = (currentPage - 1) * PAGE_SIZE;
    const pageData = filteredData.slice(start, start + PAGE_SIZE);
    const tbody = document.getElementById('stock-table');
    const totalShown = Math.min(currentPage * PAGE_SIZE, filteredData.length);
    document.getElementById('result-count').textContent =
        `Showing 1-${{totalShown}} of ${{filteredData.length.toLocaleString()}}`;
    tbody.insertAdjacentHTML('beforeend', pageData.map(s => rowHTML(s)).join(''));
}}

function renderTable() {{
    const tbody = document.getElementById('stock-table');

    if (isMobile) {{
        // Mobile: render first page, rest loaded via scroll
        currentPage = 1;
        const pageData = filteredData.slice(0, PAGE_SIZE);
        const totalShown = Math.min(PAGE_SIZE, filteredData.length);
        document.getElementById('result-count').textContent =
            `Showing 1-${{totalShown}} of ${{filteredData.length.toLocaleString()}}`;
        if (pageData.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:40px;color:var(--text-muted)">No stocks found</td></tr>';
            return;
        }}
        tbody.innerHTML = pageData.map(s => rowHTML(s)).join('');
        return;
    }}

    // Desktop: paginated
    const start = (currentPage - 1) * PAGE_SIZE;
    const pageData = filteredData.slice(start, start + PAGE_SIZE);

    document.getElementById('result-count').textContent =
        `Showing ${{Math.min(start + 1, filteredData.length)}}-${{Math.min(start + PAGE_SIZE, filteredData.length)}} of ${{filteredData.length.toLocaleString()}}`;

    if (pageData.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:40px;color:var(--text-muted)">No stocks found</td></tr>';
        return;
    }}

    tbody.innerHTML = pageData.map(s => rowHTML(s)).join('');
}}

function rowHTML(s) {{
    const cls = s.change_pct >= 0 ? 'positive' : 'negative';
    const sign = s.change_pct >= 0 ? '+' : '';
    const sym = s.symbol.replace('.NS','').replace('.BO','');
    const exchBadge = s.exchange === 'NSE+BSE'
        ? '<span style="color:var(--blue)">NSE</span>+<span style="color:var(--orange)">BSE</span>'
        : s.exchange === 'NSE' ? '<span style="color:var(--blue)">NSE</span>'
        : '<span style="color:var(--orange)">BSE</span>';
    const capCls = s.market_cap_cat === 'Large Cap' ? 'cap-large'
        : s.market_cap_cat === 'Mid Cap' ? 'cap-mid'
        : s.market_cap_cat === 'Small Cap' ? 'cap-small' : 'cap-micro';
    const capLabel = s.market_cap_cat === 'Unknown' ? '-' : s.market_cap_cat.replace(' Cap','');
    const safeName = (s.name || sym).replace(/'/g, "\\'");
    return `<tr onclick="openStockDetail('${{s.symbol}}')" style="cursor:pointer">
        <td>${{sym}} <span style="font-size:10px;color:var(--text-muted);margin-left:2px">&#128200;</span></td>
        <td><span class="company-name">${{s.name || sym}}</span><span class="mobile-vol">Vol: ${{s.volume ? s.volume.toLocaleString('en-IN') : '0'}}</span></td>
        <td class="sector-cell">${{s.sector === 'Unknown' ? '-' : s.sector}}</td>
        <td style="text-align:center"><span class="cap-badge ${{capCls}}">${{capLabel}}</span></td>
        <td style="text-align:center;font-family:sans-serif;font-size:11px">${{exchBadge}}</td>
        <td>${{fmt(s.open)}}</td>
        <td>${{fmt(s.high)}}</td>
        <td>${{fmt(s.low)}}</td>
        <td>${{fmt(s.close)}}</td>
        <td><span class="mobile-chg-abs ${{cls}}">${{sign}}${{fmt(s.change_abs)}}</span><span class="change-cell ${{cls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span></td>
        <td class="${{cls}}">${{sign}}${{fmt(s.change_abs)}}</td>
        <td>${{s.volume ? s.volume.toLocaleString('en-IN') : '0'}}</td>
    </tr>`;
}}

function fmt(n) {{
    if (n == null) return '-';
    return Number(n).toLocaleString('en-IN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
}}

// ==========================================
// PAGINATION
// ==========================================
function renderPagination() {{
    const totalPages = Math.ceil(filteredData.length / PAGE_SIZE);
    const pag = document.getElementById('pagination');
    if (totalPages <= 1) {{ pag.innerHTML = ''; return; }}

    let html = `<button class="page-btn" onclick="goPage(1)" ${{currentPage === 1 ? 'disabled' : ''}}>&laquo;</button>`;
    html += `<button class="page-btn" onclick="goPage(${{currentPage - 1}})" ${{currentPage === 1 ? 'disabled' : ''}}>&lsaquo;</button>`;

    let startP = Math.max(1, currentPage - 3);
    let endP = Math.min(totalPages, currentPage + 3);
    if (startP > 1) html += `<span class="page-info">...</span>`;
    for (let i = startP; i <= endP; i++) {{
        html += `<button class="page-btn ${{i === currentPage ? 'active' : ''}}" onclick="goPage(${{i}})">${{i}}</button>`;
    }}
    if (endP < totalPages) html += `<span class="page-info">...</span>`;

    html += `<button class="page-btn" onclick="goPage(${{currentPage + 1}})" ${{currentPage === totalPages ? 'disabled' : ''}}>&rsaquo;</button>`;
    html += `<button class="page-btn" onclick="goPage(${{totalPages}})" ${{currentPage === totalPages ? 'disabled' : ''}}>&raquo;</button>`;

    pag.innerHTML = html;
}}

function goPage(p) {{
    const totalPages = Math.ceil(filteredData.length / PAGE_SIZE);
    if (p < 1 || p > totalPages) return;
    currentPage = p;
    renderTable();
    renderPagination();
    window.scrollTo({{ top: document.querySelector('.controls').offsetTop - 80, behavior: 'smooth' }});
}}

// ==========================================
// CHART MODAL
// ==========================================
let chartInstance = null;

function openChart(symbol, name) {{
    const modal = document.getElementById('chart-modal');
    const container = document.getElementById('chart-container');
    const symbolEl = document.getElementById('chart-symbol');
    const nameEl = document.getElementById('chart-name');
    const legendEl = document.getElementById('chart-legend');

    // Show modal with loading state
    modal.style.display = 'flex';
    symbolEl.textContent = symbol.replace('.NS','').replace('.BO','');
    nameEl.textContent = name;
    container.innerHTML = '<div class="chart-loading">Loading chart data...</div>';
    legendEl.textContent = '';
    document.body.style.overflow = 'hidden';

    // Build JSON file path (dots replaced with underscores)
    // Try primary symbol first, then fallback to alternate exchange
    const safeSymbol = symbol.replace(/\\./g, '_');
    const dataUrl = 'data/' + safeSymbol + '.json';

    // Alternate: if .BO fails try .NS, and vice versa
    let altSymbol = symbol.endsWith('.BO') ? symbol.replace('.BO', '.NS') : symbol.replace('.NS', '.BO');
    const altUrl = 'data/' + altSymbol.replace(/\\./g, '_') + '.json';

    fetch(dataUrl)
        .then(r => {{
            if (!r.ok) return fetch(altUrl);
            return r;
        }})
        .then(r => {{
            if (!r.ok) throw new Error('Data not found');
            return r.json();
        }})
        .then(data => {{
            // Handle both old format (array) and new format (object with ohlcv + fundamentals)
            const ohlcv = Array.isArray(data) ? data : (data.ohlcv || []);
            renderChart(ohlcv, container, legendEl);
        }})
        .catch(err => {{
            container.innerHTML = '<div class="chart-loading">Chart data not available for this stock</div>';
        }});
}}

function renderChart(data, container, legendEl) {{
    container.innerHTML = '';

    // Destroy previous chart
    if (chartInstance) {{
        chartInstance.remove();
        chartInstance = null;
    }}

    chartInstance = LightweightCharts.createChart(container, {{
        layout: {{
            background: {{ color: '#161b22' }},
            textColor: '#8b949e',
        }},
        grid: {{
            vertLines: {{ color: '#21262d' }},
            horzLines: {{ color: '#21262d' }},
        }},
        crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
        rightPriceScale: {{ borderColor: '#30363d' }},
        timeScale: {{ borderColor: '#30363d', timeVisible: false }},
        width: container.clientWidth,
        height: container.clientHeight,
    }});

    // Candlestick series
    const candleSeries = chartInstance.addCandlestickSeries({{
        upColor: '#26a641',
        downColor: '#f85149',
        borderUpColor: '#26a641',
        borderDownColor: '#f85149',
        wickUpColor: '#26a641',
        wickDownColor: '#f85149',
    }});

    const candleData = data.map(d => ({{
        time: d[0],
        open: d[1],
        high: d[2],
        low: d[3],
        close: d[4],
    }}));
    candleSeries.setData(candleData);

    // Volume histogram
    const volumeSeries = chartInstance.addHistogramSeries({{
        priceFormat: {{ type: 'volume' }},
        priceScaleId: '',
    }});
    volumeSeries.priceScale().applyOptions({{
        scaleMargins: {{ top: 0.8, bottom: 0 }},
    }});
    const volData = data.map(d => ({{
        time: d[0],
        value: d[5],
        color: d[4] >= d[1] ? 'rgba(38,166,65,0.3)' : 'rgba(248,81,73,0.3)',
    }}));
    volumeSeries.setData(volData);

    // Fit full range
    chartInstance.timeScale().fitContent();

    // Crosshair hover legend
    chartInstance.subscribeCrosshairMove(param => {{
        if (!param || !param.time) {{
            legendEl.textContent = '';
            return;
        }}
        const candle = param.seriesData.get(candleSeries);
        if (candle) {{
            const chg = candle.close - candle.open;
            const chgPct = ((chg / candle.open) * 100).toFixed(2);
            const sign = chg >= 0 ? '+' : '';
            legendEl.textContent = 'O: ' + candle.open.toFixed(2) +
                '  H: ' + candle.high.toFixed(2) +
                '  L: ' + candle.low.toFixed(2) +
                '  C: ' + candle.close.toFixed(2) +
                '  ' + sign + chgPct + '%';
        }}
    }});

    // Responsive resize
    const ro = new ResizeObserver(() => {{
        if (chartInstance) {{
            chartInstance.applyOptions({{
                width: container.clientWidth,
                height: container.clientHeight,
            }});
        }}
    }});
    ro.observe(container);
}}

function closeChart() {{
    document.getElementById('chart-modal').style.display = 'none';
    document.body.style.overflow = '';
    if (chartInstance) {{
        chartInstance.remove();
        chartInstance = null;
    }}
}}

// Close on backdrop click or Escape
document.getElementById('chart-modal').addEventListener('click', e => {{
    if (e.target.id === 'chart-modal') closeChart();
}});

// ==========================================
// TICKER FULLSCREEN OVERLAY
// ==========================================
let tickerOverlayOpen = false;
let tickerPaused = false;

function openTickerOverlay() {{
    const overlay = document.getElementById('ticker-overlay');
    const fsTrack = document.getElementById('fs-ticker-track');

    // Build fullscreen ticker items from currently filtered data
    const data = filteredData.length > 0 ? filteredData : ALL_STOCKS;
    if (data.length === 0) return;

    const items = data.map(s => {{
        const sym = s.symbol.replace('.NS','').replace('.BO','');
        const sign = s.change_pct >= 0 ? '+' : '';
        const cls = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat';
        const escaped = s.symbol.replace(/'/g, "\\'");
        return `<div class="fs-ticker-item" data-symbol="${{s.symbol}}" style="cursor:pointer;" onclick="openStockDetail('${{escaped}}')">`
            + `<span class="fs-ticker-symbol">${{sym}}</span>`
            + `<span class="fs-ticker-price">${{fmt(s.close)}}</span>`
            + `<span class="fs-ticker-change ${{cls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span>`
            + `</div>`;
    }}).join('');
    fsTrack.innerHTML = items + items;

    baseDuration = Math.max(60, data.length * 1.2);
    const dur = baseDuration / SPEED_LEVELS[speedIndex];
    fsTrack.parentElement.style.setProperty('--fs-ticker-duration', dur + 's');

    // Reset controls
    speedIndex = 3; fontIndex = 2;
    document.getElementById('fs-speed-val').textContent = '1x';
    document.getElementById('fs-font-val').textContent = 'M';

    tickerPaused = false;
    fsTrack.classList.remove('paused');
    document.getElementById('fs-paused-label').classList.remove('visible');

    overlay.classList.add('active');
    tickerOverlayOpen = true;
}}

function closeTickerOverlay() {{
    document.getElementById('ticker-overlay').classList.remove('active');
    tickerOverlayOpen = false;
    tickerPaused = false;
    // Exit browser fullscreen if active
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {{}});
}}

function toggleTickerPause() {{
    if (!tickerOverlayOpen) return;
    tickerPaused = !tickerPaused;
    const fsTrack = document.getElementById('fs-ticker-track');
    const label = document.getElementById('fs-paused-label');
    if (tickerPaused) {{
        fsTrack.classList.add('paused');
        label.classList.add('visible');
    }} else {{
        fsTrack.classList.remove('paused');
        label.classList.remove('visible');
    }}
}}

// Speed & Font Size controls
const SPEED_LEVELS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3];
const SPEED_LABELS = ['0.25x','0.5x','0.75x','1x','1.5x','2x','3x'];
let speedIndex = 3; // default 1x
let baseDuration = 180;

const FONT_SIZES = [14, 18, 22, 28, 36];
const FONT_LABELS = ['XS', 'S', 'M', 'L', 'XL'];
let fontIndex = 2; // default M (22px)

function changeTickerSpeed(dir) {{
    speedIndex = Math.max(0, Math.min(SPEED_LEVELS.length - 1, speedIndex + dir));
    const speed = SPEED_LEVELS[speedIndex];
    const newDur = baseDuration / speed;
    const fsTrack = document.getElementById('fs-ticker-track');
    fsTrack.style.setProperty('--fs-ticker-duration', newDur + 's');
    // Reset animation to apply new duration smoothly
    fsTrack.style.animation = 'none';
    fsTrack.offsetHeight; // trigger reflow
    fsTrack.style.animation = '';
    fsTrack.style.animationDuration = newDur + 's';
    document.getElementById('fs-speed-val').textContent = SPEED_LABELS[speedIndex];
}}

function changeTickerFontSize(dir) {{
    fontIndex = Math.max(0, Math.min(FONT_SIZES.length - 1, fontIndex + dir));
    const size = FONT_SIZES[fontIndex];
    document.querySelectorAll('.fs-ticker-item').forEach(el => {{
        el.style.fontSize = size + 'px';
        el.style.height = (size + 38) + 'px';
    }});
    document.getElementById('fs-font-val').textContent = FONT_LABELS[fontIndex];
}}

function toggleTickerFullscreen() {{
    if (!tickerOverlayOpen) return;
    const overlay = document.getElementById('ticker-overlay');
    if (!document.fullscreenElement) {{
        overlay.requestFullscreen().catch(() => {{}});
    }} else {{
        document.exitFullscreen().catch(() => {{}});
    }}
}}

// ==========================================
// FULLSCREEN STOCK DETAIL PANEL
// ==========================================
let fsPanelChart = null;
let fsPanelOpen = false;

function openFsStockPanel(symbol) {{
    // Find stock data
    const stock = ALL_STOCKS.find(s => s.symbol === symbol);
    if (!stock) return;

    const sym = symbol.replace('.NS','').replace('.BO','');

    // Fill header
    document.getElementById('fs-panel-sym').textContent = sym;
    document.getElementById('fs-panel-name').textContent = stock.name || sym;

    // Show basic price info initially (will be enriched by fundamentals when loaded)
    const sign = stock.change_pct >= 0 ? '+' : '';
    const chgCls = stock.change_pct > 0 ? 'green' : stock.change_pct < 0 ? 'red' : '';
    const change = stock.close - stock.open;
    const changSign = change >= 0 ? '+' : '';

    const infoHtml = [
        ['Open', fmt(stock.open)],
        ['High', fmt(stock.high)],
        ['Low', fmt(stock.low)],
        ['Close', fmt(stock.close)],
        ['Change', `${{changSign}}${{change.toFixed(2)}}`, change >= 0 ? 'green' : 'red'],
        ['Change %', `${{sign}}${{stock.change_pct.toFixed(2)}}%`, chgCls],
        ['Volume', stock.volume ? stock.volume.toLocaleString() : '-'],
        ['Exchange', stock.exchange || '-'],
    ].map(([label, val, cls]) =>
        `<div class="info-cell"><div class="info-label">${{label}}</div><div class="info-val ${{cls || ''}}">${{val}}</div></div>`
    ).join('');
    document.getElementById('fs-panel-info').innerHTML = infoHtml;

    // Basic tags (will be enriched by fundamentals)
    const tags = [stock.sector, stock.market_cap_cat, stock.industry].filter(t => t && t !== 'Unknown');
    document.getElementById('fs-panel-tags').innerHTML = tags.map(t => `<span class="fs-panel-tag">${{t}}</span>`).join('');

    // Remove old about section
    const oldAbout = document.getElementById('fs-panel-about');
    if (oldAbout) oldAbout.remove();

    // Show panel
    document.getElementById('fs-stock-backdrop').classList.add('active');
    document.getElementById('fs-stock-panel').classList.add('active');
    fsPanelOpen = true;

    // Load chart
    const chartDiv = document.getElementById('fs-panel-chart');
    chartDiv.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#555;">Loading chart...</div>';
    document.getElementById('fs-panel-legend').textContent = '';

    const safeName = symbol.replace('.', '_');
    fetch(`data/${{safeName}}.json`)
        .then(r => r.ok ? r.json() : Promise.reject('Not found'))
        .then(fileData => {{
            // Handle both old (array) and new (object with ohlcv + fundamentals) formats
            const rawData = Array.isArray(fileData) ? fileData : (fileData.ohlcv || []);
            const fund = Array.isArray(fileData) ? {{}} : (fileData.fundamentals || {{}});

            // Render chart
            chartDiv.innerHTML = '';
            if (fsPanelChart) {{ fsPanelChart.remove(); fsPanelChart = null; }}

            const chart = LightweightCharts.createChart(chartDiv, {{
                width: chartDiv.clientWidth,
                height: chartDiv.clientHeight,
                layout: {{ background: {{ type: 'solid', color: '#161b22' }}, textColor: '#8b949e' }},
                grid: {{ vertLines: {{ color: '#21262d' }}, horzLines: {{ color: '#21262d' }} }},
                crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                timeScale: {{ borderColor: '#30363d', timeVisible: false }},
                rightPriceScale: {{ borderColor: '#30363d' }},
            }});
            fsPanelChart = chart;

            const candleData = rawData.map(d => ({{ time: d[0], open: d[1], high: d[2], low: d[3], close: d[4] }}));
            const volData = rawData.map(d => ({{
                time: d[0], value: d[5],
                color: d[4] >= d[1] ? 'rgba(38,166,65,0.3)' : 'rgba(248,81,73,0.3)'
            }}));

            const candleSeries = chart.addCandlestickSeries({{
                upColor: '#26a641', downColor: '#f85149',
                borderUpColor: '#26a641', borderDownColor: '#f85149',
                wickUpColor: '#26a641', wickDownColor: '#f85149',
            }});
            candleSeries.setData(candleData);

            const volSeries = chart.addHistogramSeries({{
                priceFormat: {{ type: 'volume' }},
                priceScaleId: 'vol',
            }});
            chart.priceScale('vol').applyOptions({{
                scaleMargins: {{ top: 0.85, bottom: 0 }},
            }});
            volSeries.setData(volData);
            chart.timeScale().fitContent();

            chart.subscribeCrosshairMove(param => {{
                const legend = document.getElementById('fs-panel-legend');
                if (!param || !param.time) {{ legend.textContent = ''; return; }}
                const d = param.seriesData?.get(candleSeries);
                if (d) {{
                    const chg = ((d.close - d.open) / d.open * 100).toFixed(2);
                    legend.textContent = `O: ${{d.open}}  H: ${{d.high}}  L: ${{d.low}}  C: ${{d.close}}  ${{chg}}%`;
                }}
            }});

            new ResizeObserver(() => {{
                if (fsPanelChart) chart.applyOptions({{ width: chartDiv.clientWidth }});
            }}).observe(chartDiv);

            // Render fundamentals if available
            if (Object.keys(fund).length > 0) {{
                renderFundamentals(fund, stock);
            }}
        }})
        .catch(() => {{
            chartDiv.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#555;">Chart data not available</div>';
        }});
}}

function fmtCr(val) {{
    if (val == null) return '-';
    const cr = val / 1e7;
    if (cr >= 100) return cr.toFixed(0).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',') + ' Cr';
    return cr.toFixed(2) + ' Cr';
}}
function fmtPct(val) {{
    if (val == null) return '-';
    return (val * 100).toFixed(2) + '%';
}}
function fmtNum(val, dec) {{
    if (val == null) return '-';
    return Number(val).toFixed(dec || 2);
}}

function renderFundamentals(fund, stock) {{
    // Helper to build a card
    function card(title, rows) {{
        const validRows = rows.filter(r => r[1] !== '-' && r[1] != null);
        if (validRows.length === 0) return '';
        const body = validRows.map(([label, val, cls, isKey]) => {{
            const rowCls = isKey ? ' key-metric' : '';
            return `<div class="fund-row${{rowCls}}"><span class="f-label">${{label}}</span><span class="f-val ${{cls || ''}}">${{val}}</span></div>`;
        }}).join('');
        return `<div class="fund-card"><div class="fund-card-title">${{title}}</div><div class="fund-card-body">${{body}}</div></div>`;
    }}

    // Color helper for percentage values
    function pctCls(val) {{
        if (val == null) return '';
        const n = typeof val === 'string' ? parseFloat(val) : val;
        return n > 0 ? 'green' : n < 0 ? 'red' : '';
    }}

    // Recommendation badge
    function recBadge(rec) {{
        if (!rec) return '-';
        const r = rec.toUpperCase();
        let cls = 'rec-hold';
        if (r.includes('BUY') || r === 'STRONG_BUY') cls = 'rec-buy';
        else if (r.includes('SELL') || r === 'STRONG_SELL') cls = 'rec-sell';
        return `<span class="rec-badge ${{cls}}">${{r.replace('_',' ')}}</span>`;
    }}

    // Build cards
    let html = '';

    // Row 1: Valuation | Margins | Income
    html += card('VALUATION', [
        ['P/E (TTM)', fmtNum(fund.trailing_pe), '', true],
        ['P/E (Fwd)', fmtNum(fund.forward_pe)],
        ['P/B Ratio', fmtNum(fund.price_to_book)],
        ['EPS (TTM)', '₹' + fmtNum(fund.eps_trailing), 'blue'],
        ['EPS (Fwd)', '₹' + fmtNum(fund.eps_forward)],
        ['Book Value', '₹' + fmtNum(fund.book_value)],
    ]);

    html += card('MARGINS', [
        ['Operating', fund.operating_margins != null ? fmtPct(fund.operating_margins) : '-', pctCls(fund.operating_margins), true],
        ['Profit', fund.profit_margins != null ? fmtPct(fund.profit_margins) : '-', pctCls(fund.profit_margins)],
        ['Gross', fund.gross_margins != null ? fmtPct(fund.gross_margins) : '-', pctCls(fund.gross_margins)],
        ['EBITDA', fund.ebitda_margins != null ? fmtPct(fund.ebitda_margins) : '-', pctCls(fund.ebitda_margins)],
        ['ROE', fund.return_on_equity != null ? fmtPct(fund.return_on_equity) : '-', pctCls(fund.return_on_equity), true],
    ]);

    html += card('INCOME', [
        ['Revenue', fund.revenue ? fmtCr(fund.revenue) : '-', 'blue', true],
        ['Rev Growth', fund.revenue_growth != null ? fmtPct(fund.revenue_growth) : '-', pctCls(fund.revenue_growth), true],
        ['EBITDA', fund.ebitda ? fmtCr(fund.ebitda) : '-'],
        ['Net Income', fund.net_income ? fmtCr(fund.net_income) : '-', fund.net_income > 0 ? 'green' : fund.net_income < 0 ? 'red' : ''],
        ['Earn Growth', fund.earnings_growth != null ? fmtPct(fund.earnings_growth) : '-', pctCls(fund.earnings_growth)],
    ]);

    // Row 2: Balance Sheet | Dividends | Holdings
    html += card('BALANCE SHEET', [
        ['Total Debt', fund.total_debt ? fmtCr(fund.total_debt) : '-', fund.total_debt > 0 ? 'red' : ''],
        ['Total Cash', fund.total_cash ? fmtCr(fund.total_cash) : '-', 'green'],
        ['Debt/Equity', fmtNum(fund.debt_to_equity), '', true],
        ['Current Ratio', fmtNum(fund.current_ratio)],
        ['Free Cash Flow', fund.free_cashflow ? fmtCr(fund.free_cashflow) : '-', fund.free_cashflow > 0 ? 'green' : 'red'],
    ]);

    html += card('DIVIDENDS', [
        ['Div Yield', fund.dividend_yield != null ? fmtPct(fund.dividend_yield) : '-', 'gold', true],
        ['Div Rate', fund.dividend_rate != null ? '₹' + fmtNum(fund.dividend_rate) : '-'],
        ['Payout Ratio', fund.payout_ratio != null ? fmtPct(fund.payout_ratio) : '-'],
        ['5Y Avg Yield', fund.five_yr_avg_div_yield != null ? fmtNum(fund.five_yr_avg_div_yield) + '%' : '-'],
    ]);

    html += card('HOLDINGS', [
        ['Insider Hold', fund.held_pct_insiders != null ? fmtPct(fund.held_pct_insiders) : '-', fund.held_pct_insiders > 0.5 ? 'green' : ''],
        ['Inst Hold', fund.held_pct_institutions != null ? fmtPct(fund.held_pct_institutions) : '-', 'blue'],
        ['Shares Out', fund.shares_outstanding ? (fund.shares_outstanding / 1e7).toFixed(2) + ' Cr' : '-'],
        ['Float Shares', fund.float_shares ? (fund.float_shares / 1e7).toFixed(2) + ' Cr' : '-'],
        ['Employees', fund.full_time_employees ? fund.full_time_employees.toLocaleString() : '-'],
    ]);

    // Row 3: 52W Range (visual) | Targets
    // 52W Range with visual bar
    if (fund.fifty_two_week_high && fund.fifty_two_week_low) {{
        const low = fund.fifty_two_week_low;
        const high = fund.fifty_two_week_high;
        const current = stock.close;
        const pct = Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100));
        html += `<div class="fund-card">
            <div class="fund-card-title">52 WEEK RANGE</div>
            <div class="range-bar-container">
                <div class="range-current">₹${{current.toFixed(2)}}</div>
                <div class="range-bar"><div class="range-dot" style="left:${{pct}}%"></div></div>
                <div class="range-labels"><span>₹${{low.toFixed(2)}}</span><span>₹${{high.toFixed(2)}}</span></div>
            </div>
            <div class="fund-card-body">
                <div class="fund-row"><span class="f-label">50D Avg</span><span class="f-val">₹${{fmtNum(fund.fifty_day_average)}}</span></div>
                <div class="fund-row"><span class="f-label">200D Avg</span><span class="f-val">₹${{fmtNum(fund.two_hundred_day_avg)}}</span></div>
                <div class="fund-row"><span class="f-label">Beta</span><span class="f-val">${{fmtNum(fund.beta)}}</span></div>
            </div>
        </div>`;
    }}

    // Targets with recommendation badge
    const hasTargets = fund.target_mean_price || fund.recommendation;
    if (hasTargets) {{
        html += `<div class="fund-card">
            <div class="fund-card-title">ANALYST TARGETS</div>
            <div class="fund-card-body">
                ${{fund.recommendation ? `<div class="fund-row key-metric"><span class="f-label">Recommendation</span><span class="f-val">${{recBadge(fund.recommendation)}}</span></div>` : ''}}
                ${{fund.num_analyst_opinions ? `<div class="fund-row"><span class="f-label">Analysts</span><span class="f-val blue">${{fund.num_analyst_opinions}}</span></div>` : ''}}
                ${{fund.target_high_price ? `<div class="fund-row"><span class="f-label">Target High</span><span class="f-val green">₹${{fmtNum(fund.target_high_price)}}</span></div>` : ''}}
                ${{fund.target_mean_price ? `<div class="fund-row"><span class="f-label">Target Mean</span><span class="f-val blue">₹${{fmtNum(fund.target_mean_price)}}</span></div>` : ''}}
                ${{fund.target_low_price ? `<div class="fund-row"><span class="f-label">Target Low</span><span class="f-val red">₹${{fmtNum(fund.target_low_price)}}</span></div>` : ''}}
            </div>
        </div>`;
    }}

    document.getElementById('fs-panel-info').innerHTML = html;

    // Tags with colored categories
    let tagsHtml = '';
    if (stock.sector && stock.sector !== 'Unknown') tagsHtml += `<span class="fs-panel-tag sector">${{stock.sector}}</span>`;
    if (stock.market_cap_cat && stock.market_cap_cat !== 'Unknown') tagsHtml += `<span class="fs-panel-tag cap">${{stock.market_cap_cat}}</span>`;
    if (stock.industry && stock.industry !== 'Unknown') tagsHtml += `<span class="fs-panel-tag">${{stock.industry}}</span>`;
    if (stock.exchange) tagsHtml += `<span class="fs-panel-tag exchange">${{stock.exchange}}</span>`;
    if (fund.website) tagsHtml += `<span class="fs-panel-tag">${{fund.website.replace('https://','').replace('http://','')}}</span>`;
    if (fund.city) tagsHtml += `<span class="fs-panel-tag">${{fund.city}}</span>`;
    document.getElementById('fs-panel-tags').innerHTML = tagsHtml;

    // Update header with long name
    if (fund.long_name) {{
        document.getElementById('fs-panel-name').textContent = fund.long_name;
    }}

    // About section inside the last card
    const existing = document.getElementById('fs-panel-about');
    if (existing) existing.remove();
    if (fund.long_business_summary) {{
        const aboutDiv = document.createElement('div');
        aboutDiv.id = 'fs-panel-about';
        aboutDiv.className = 'fund-card';
        const text = fund.long_business_summary;
        const shortText = text.length > 250 ? text.substring(0, 250) + '...' : text;
        aboutDiv.innerHTML = `<div class="fund-card-title">ABOUT</div><div class="fund-about">${{shortText}}</div>`;
        document.getElementById('fs-panel-info').appendChild(aboutDiv);
    }}
}}

function closeFsStockPanel() {{
    document.getElementById('fs-stock-backdrop').classList.remove('active');
    document.getElementById('fs-stock-panel').classList.remove('active');
    fsPanelOpen = false;
    if (fsPanelChart) {{ fsPanelChart.remove(); fsPanelChart = null; }}
}}

// ==========================================
// STOCK DETAIL SPLIT-PANEL VIEW
// ==========================================
let detailViewOpen = false;
let detailEntryPoint = null;   // 'ticker' | 'main'
let detailFsMode = null;       // null | 'chart' | 'data'
let detailChartInstance = null;

function openStockDetail(symbol) {{
    const stock = ALL_STOCKS.find(s => s.symbol === symbol);
    if (!stock) return;

    const sym = symbol.replace('.NS','').replace('.BO','');

    // Remember where we came from
    detailEntryPoint = tickerOverlayOpen ? 'ticker' : 'main';

    // If from ticker overlay, hide it (we'll show it again on back)
    if (tickerOverlayOpen) {{
        document.getElementById('ticker-overlay').classList.remove('active');
        tickerOverlayOpen = false;
    }}

    // Populate toolbar
    document.getElementById('detail-symbol').textContent = sym;
    document.getElementById('detail-name').textContent = stock.name || sym;

    // Build detail ticker
    buildDetailTicker();

    // Show initial OHLC price bar
    const sign = stock.change_pct >= 0 ? '+' : '';
    const chgCls = stock.change_pct > 0 ? 'green' : stock.change_pct < 0 ? 'red' : '';
    const change = stock.close - stock.open;
    const changSign = change >= 0 ? '+' : '';

    const priceBarItems = [
        ['Open', fmt(stock.open), ''],
        ['High', fmt(stock.high), ''],
        ['Low', fmt(stock.low), ''],
        ['Close', fmt(stock.close), ''],
        ['Change', `${{changSign}}${{change.toFixed(2)}}`, change >= 0 ? 'green' : 'red'],
        ['Chg %', `${{sign}}${{stock.change_pct.toFixed(2)}}%`, chgCls],
        ['Volume', stock.volume ? stock.volume.toLocaleString() : '-', ''],
    ];
    document.getElementById('detail-price-bar').innerHTML = priceBarItems.map(([lbl, val, cls]) =>
        `<div class="detail-price-item"><span class="detail-price-label">${{lbl}}</span><span class="detail-price-val ${{cls}}">${{val}}</span></div>`
    ).join('');
    document.getElementById('detail-cards').innerHTML = '<div style="padding:20px;color:var(--text-muted);text-align:center;grid-column:1/-1;">Loading fundamentals...</div>';

    // Initial tags
    const tags = [stock.sector, stock.market_cap_cat, stock.industry].filter(t => t && t !== 'Unknown');
    document.getElementById('detail-tags').innerHTML = tags.map(t => `<span class="fs-panel-tag">${{t}}</span>`).join('');
    document.getElementById('detail-about').textContent = '';

    // Reset fullscreen mode
    detailFsMode = null;
    document.getElementById('detail-split').className = 'detail-split';

    // Show the view
    document.getElementById('stock-detail-view').classList.add('active');
    document.body.style.overflow = 'hidden';
    detailViewOpen = true;

    // Chart loading placeholder
    const chartContainer = document.getElementById('detail-chart-container');
    chartContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">Loading chart...</div>';
    document.getElementById('detail-chart-legend').textContent = '';

    // Destroy old chart
    if (detailChartInstance) {{ detailChartInstance.remove(); detailChartInstance = null; }}

    // Fetch chart data
    const safeName = symbol.replace(/\\./g, '_');
    const dataUrl = 'data/' + safeName + '.json';
    let altSymbol = symbol.endsWith('.BO') ? symbol.replace('.BO', '.NS') : symbol.replace('.NS', '.BO');
    const altUrl = 'data/' + altSymbol.replace(/\\./g, '_') + '.json';

    fetch(dataUrl)
        .then(r => {{
            if (!r.ok) return fetch(altUrl);
            return r;
        }})
        .then(r => {{
            if (!r.ok) throw new Error('Data not found');
            return r.json();
        }})
        .then(fileData => {{
            const ohlcv = Array.isArray(fileData) ? fileData : (fileData.ohlcv || []);
            const fund = Array.isArray(fileData) ? {{}} : (fileData.fundamentals || {{}});

            // Render chart into detail container
            chartContainer.innerHTML = '';
            const legendEl = document.getElementById('detail-chart-legend');
            renderDetailChart(ohlcv, chartContainer, legendEl);

            // Render fundamentals if available
            if (Object.keys(fund).length > 0) {{
                renderDetailFundamentals(fund, stock);
            }}
        }})
        .catch(() => {{
            chartContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">Chart data not available</div>';
        }});
}}

function renderDetailChart(data, container, legendEl) {{
    container.innerHTML = '';
    if (detailChartInstance) {{ detailChartInstance.remove(); detailChartInstance = null; }}

    detailChartInstance = LightweightCharts.createChart(container, {{
        layout: {{
            background: {{ color: '#0d1117' }},
            textColor: '#8b949e',
        }},
        grid: {{
            vertLines: {{ color: '#21262d' }},
            horzLines: {{ color: '#21262d' }},
        }},
        crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
        rightPriceScale: {{ borderColor: '#30363d' }},
        timeScale: {{ borderColor: '#30363d', timeVisible: false }},
        width: container.clientWidth,
        height: container.clientHeight,
    }});

    const candleSeries = detailChartInstance.addCandlestickSeries({{
        upColor: '#26a641', downColor: '#f85149',
        borderUpColor: '#26a641', borderDownColor: '#f85149',
        wickUpColor: '#26a641', wickDownColor: '#f85149',
    }});
    const candleData = data.map(d => ({{ time: d[0], open: d[1], high: d[2], low: d[3], close: d[4] }}));
    candleSeries.setData(candleData);

    const volumeSeries = detailChartInstance.addHistogramSeries({{
        priceFormat: {{ type: 'volume' }},
        priceScaleId: 'vol',
    }});
    detailChartInstance.priceScale('vol').applyOptions({{
        scaleMargins: {{ top: 0.8, bottom: 0 }},
    }});
    const volData = data.map(d => ({{
        time: d[0], value: d[5],
        color: d[4] >= d[1] ? 'rgba(38,166,65,0.3)' : 'rgba(248,81,73,0.3)',
    }}));
    volumeSeries.setData(volData);
    detailChartInstance.timeScale().fitContent();

    detailChartInstance.subscribeCrosshairMove(param => {{
        if (!param || !param.time) {{ legendEl.textContent = ''; return; }}
        const candle = param.seriesData.get(candleSeries);
        if (candle) {{
            const chg = candle.close - candle.open;
            const chgPct = ((chg / candle.open) * 100).toFixed(2);
            const s = chg >= 0 ? '+' : '';
            legendEl.textContent = 'O: ' + candle.open.toFixed(2) +
                '  H: ' + candle.high.toFixed(2) +
                '  L: ' + candle.low.toFixed(2) +
                '  C: ' + candle.close.toFixed(2) +
                '  ' + s + chgPct + '%';
        }}
    }});

    new ResizeObserver(() => {{
        if (detailChartInstance) {{
            detailChartInstance.applyOptions({{
                width: container.clientWidth,
                height: container.clientHeight,
            }});
        }}
    }}).observe(container);
}}

function closeStockDetail() {{
    document.getElementById('stock-detail-view').classList.remove('active');
    document.body.style.overflow = '';
    detailViewOpen = false;

    if (detailChartInstance) {{ detailChartInstance.remove(); detailChartInstance = null; }}

    // If we came from ticker overlay, show it again
    if (detailEntryPoint === 'ticker') {{
        document.getElementById('ticker-overlay').classList.add('active');
        tickerOverlayOpen = true;
    }}

    // Exit browser fullscreen if active
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {{}});

    detailEntryPoint = null;
    detailFsMode = null;
}}

// Detail ticker state
let detailSpeedIndex = 3;
const DETAIL_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3];
const DETAIL_SPEED_LABELS = ['0.25x','0.5x','0.75x','1x','1.5x','2x','3x'];
let detailBaseDuration = 120;

function buildDetailTicker() {{
    const track = document.getElementById('detail-ticker-track');
    const data = globalFiltered.length > 0 ? globalFiltered : ALL_STOCKS;
    if (data.length === 0) {{ track.innerHTML = ''; return; }}

    const items = data.map(s => {{
        const sym = s.symbol.replace('.NS','').replace('.BO','');
        const sign = s.change_pct >= 0 ? '+' : '';
        const cls = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : 'flat';
        const escaped = s.symbol.replace(/'/g, "\\'");
        return `<div class="detail-ticker-item" data-symbol="${{s.symbol}}" onclick="openStockDetail('${{escaped}}')">`
            + `<span class="detail-ticker-sym">${{sym}}</span>`
            + `<span class="detail-ticker-price">${{fmt(s.close)}}</span>`
            + `<span class="detail-ticker-chg ${{cls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span>`
            + `</div>`;
    }}).join('');
    track.innerHTML = items + items;
    detailBaseDuration = Math.max(30, data.length * 0.8);
    const dur = detailBaseDuration / DETAIL_SPEEDS[detailSpeedIndex];
    track.parentElement.style.setProperty('--detail-ticker-duration', dur + 's');
    // Reset speed label
    detailSpeedIndex = 3;
    document.getElementById('detail-speed-label').textContent = '1x';
}}

function changeDetailSpeed(dir) {{
    detailSpeedIndex = Math.max(0, Math.min(DETAIL_SPEEDS.length - 1, detailSpeedIndex + dir));
    const track = document.getElementById('detail-ticker-track');
    // Get current animation progress to avoid restart
    const computed = getComputedStyle(track);
    const currentDur = parseFloat(computed.animationDuration) || detailBaseDuration;

    const newDur = detailBaseDuration / DETAIL_SPEEDS[detailSpeedIndex];
    track.parentElement.style.setProperty('--detail-ticker-duration', newDur + 's');

    // Preserve position: briefly pause, update duration, resume
    track.style.animationPlayState = 'paused';
    void track.offsetWidth; // force reflow
    track.style.animationDuration = newDur + 's';
    track.style.animationPlayState = '';

    document.getElementById('detail-speed-label').textContent = DETAIL_SPEED_LABELS[detailSpeedIndex];
}}

// Universal ticker search — works on main, fullscreen, and detail tickers
function tickerSearch(query, context) {{
    // Map context to IDs
    const resultsId = context === 'main' ? 'main-ticker-results'
                    : context === 'fs' ? 'fs-ticker-results'
                    : 'detail-ticker-results';
    const resultsDiv = document.getElementById(resultsId);
    if (!resultsDiv) return;

    if (!query || query.length < 1) {{
        resultsDiv.classList.remove('active');
        return;
    }}

    // Split query into words for fuzzy matching
    const words = query.toLowerCase().split(/\s+/).filter(w => w.length > 0);
    const matches = ALL_STOCKS.filter(s => {{
        const sym = s.symbol.replace('.NS','').replace('.BO','').toLowerCase();
        const name = (s.name || '').toLowerCase();
        const combined = sym + ' ' + name;
        return words.every(w => combined.includes(w));
    }}).slice(0, 15);

    if (matches.length === 0) {{
        resultsDiv.innerHTML = '<div style="padding:14px;color:var(--text-muted);font-size:12px;text-align:center;">No stocks found</div>';
        resultsDiv.classList.add('active');
        return;
    }}

    resultsDiv.innerHTML = matches.map(s => {{
        const sym = s.symbol.replace('.NS','').replace('.BO','');
        const escaped = s.symbol.replace(/'/g, "\\'");
        const sign = s.change_pct >= 0 ? '+' : '';
        const chgCls = s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : '';
        return `<div class="ticker-search-result" onclick="tickerSearchSelect('${{escaped}}', '${{context}}')">`
            + `<span class="tsr-sym">${{sym}}</span>`
            + `<span class="tsr-name">${{s.name || ''}}</span>`
            + `<span class="tsr-price">${{fmt(s.close)}}</span>`
            + `<span class="tsr-chg ${{chgCls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span>`
            + `</div>`;
    }}).join('');
    resultsDiv.classList.add('active');
}}

// Handle selection from ticker search
function tickerSearchSelect(symbol, context) {{
    // Close all search results and clear inputs
    document.querySelectorAll('.ticker-search-results').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.ticker-search-box input').forEach(el => el.value = '');

    // Determine which track to scroll to
    let trackId, containerId;
    if (context === 'main') {{
        trackId = 'ticker-track';
        containerId = null;
    }} else if (context === 'fs') {{
        trackId = 'fs-ticker-track';
        containerId = null;
    }} else {{
        trackId = 'detail-ticker-track';
        containerId = 'detail-ticker-bar';
    }}

    const track = document.getElementById(trackId);
    if (!track) return;

    // Find the item in the ticker
    const item = track.querySelector(`[data-symbol="${{symbol}}"]`);
    if (item) {{
        // Pause, scroll to center, highlight
        track.style.animationPlayState = 'paused';

        const parent = track.parentElement;
        const parentWidth = parent.clientWidth;
        const itemLeft = item.offsetLeft;
        const itemWidth = item.offsetWidth;
        const offset = Math.max(0, itemLeft - (parentWidth / 2) + (itemWidth / 2));

        track.style.animation = 'none';
        track.style.transform = `translateX(-${{offset}}px)`;

        // Highlight
        track.querySelectorAll('.highlight').forEach(el => el.classList.remove('highlight'));
        item.classList.add('highlight');

        // Resume after 3 seconds
        setTimeout(() => {{
            item.classList.remove('highlight');
            track.style.transform = '';
            track.style.animation = '';
            track.style.animationPlayState = '';
        }}, 3000);
    }} else {{
        // Stock not in current ticker — open its details instead
        openStockDetail(symbol);
    }}
}}

// Close all search results when clicking outside
document.addEventListener('click', e => {{
    if (!e.target.closest('.ticker-search-box')) {{
        document.querySelectorAll('.ticker-search-results').forEach(el => el.classList.remove('active'));
    }}
}});

function renderDetailFundamentals(fund, stock) {{
    // --- Price bar update with OHLC + Change + Volume ---
    const sign = stock.change_pct >= 0 ? '+' : '';
    const chgCls = stock.change_pct > 0 ? 'green' : stock.change_pct < 0 ? 'red' : '';
    const change = stock.close - stock.open;
    const changSign = change >= 0 ? '+' : '';
    const priceBarItems = [
        ['Open', fmt(stock.open), ''],
        ['High', fmt(stock.high), ''],
        ['Low', fmt(stock.low), ''],
        ['Close', fmt(stock.close), ''],
        ['Change', `${{changSign}}${{change.toFixed(2)}}`, change >= 0 ? 'green' : 'red'],
        ['Chg %', `${{sign}}${{stock.change_pct.toFixed(2)}}%`, chgCls],
        ['Volume', stock.volume ? stock.volume.toLocaleString() : '-', ''],
    ];
    document.getElementById('detail-price-bar').innerHTML = priceBarItems.map(([lbl, val, cls]) =>
        `<div class="detail-price-item"><span class="detail-price-label">${{lbl}}</span><span class="detail-price-val ${{cls}}">${{val}}</span></div>`
    ).join('');

    // --- Helper to get a value or null ---
    function gv(key) {{ return fund[key] != null ? fund[key] : null; }}

    // --- Helper to build a card row with optional color class ---
    function cardRow(label, val) {{
        if (val == null || val === '-') return null;
        let cls = '';
        if (typeof val === 'string' && val.includes('%')) {{
            const num = parseFloat(val);
            if (!isNaN(num)) cls = num > 0 ? 'green' : num < 0 ? 'red' : '';
        }}
        return `<div class="detail-card-row"><span class="detail-card-label">${{label}}</span><span class="detail-card-val ${{cls}}">${{val}}</span></div>`;
    }}

    // --- Helper to build a card from title + rows array ---
    function buildCard(title, rows) {{
        const validRows = rows.filter(r => r != null);
        if (validRows.length === 0) return '';
        return `<div class="detail-card"><div class="detail-card-header">${{title}}</div>${{validRows.join('')}}</div>`;
    }}

    // --- Card definitions ---
    const cards = [];

    // VALUATION
    cards.push(buildCard('Valuation', [
        cardRow('P/E (TTM)', fmtNum(fund.trailing_pe)),
        cardRow('P/E (Fwd)', fmtNum(fund.forward_pe)),
        cardRow('P/B Ratio', fmtNum(fund.price_to_book)),
        cardRow('EPS (TTM)', fmtNum(fund.eps_trailing)),
        cardRow('EPS (Fwd)', fmtNum(fund.eps_forward)),
        cardRow('Book Value', fmtNum(fund.book_value)),
    ]));

    // MARGINS
    cards.push(buildCard('Margins', [
        cardRow('Operating', gv('operating_margins') != null ? fmtPct(fund.operating_margins) : null),
        cardRow('Profit', gv('profit_margins') != null ? fmtPct(fund.profit_margins) : null),
        cardRow('Gross', gv('gross_margins') != null ? fmtPct(fund.gross_margins) : null),
        cardRow('EBITDA', gv('ebitda_margins') != null ? fmtPct(fund.ebitda_margins) : null),
    ]));

    // INCOME
    cards.push(buildCard('Income', [
        cardRow('Revenue', fund.revenue ? fmtCr(fund.revenue) : null),
        cardRow('Rev Growth', gv('revenue_growth') != null ? fmtPct(fund.revenue_growth) : null),
        cardRow('EBITDA', fund.ebitda ? fmtCr(fund.ebitda) : null),
        cardRow('Net Income', fund.net_income ? fmtCr(fund.net_income) : null),
        cardRow('Earn Growth', gv('earnings_growth') != null ? fmtPct(fund.earnings_growth) : null),
    ]));

    // BALANCE SHEET
    cards.push(buildCard('Balance Sheet', [
        cardRow('Total Debt', fund.total_debt ? fmtCr(fund.total_debt) : null),
        cardRow('Total Cash', fund.total_cash ? fmtCr(fund.total_cash) : null),
        cardRow('Debt/Equity', fmtNum(fund.debt_to_equity)),
        cardRow('Current Ratio', fmtNum(fund.current_ratio)),
        cardRow('Free Cash Flow', fund.free_cashflow ? fmtCr(fund.free_cashflow) : null),
    ]));

    // DIVIDENDS
    cards.push(buildCard('Dividends', [
        cardRow('Div Rate', gv('dividend_rate') != null ? '\\u20b9' + fmtNum(fund.dividend_rate) : null),
        cardRow('Div Yield', gv('dividend_yield') != null ? fmtPct(fund.dividend_yield) : null),
        cardRow('Payout Ratio', gv('payout_ratio') != null ? fmtPct(fund.payout_ratio) : null),
        cardRow('5Y Avg Yield', gv('five_yr_avg_div_yield') != null ? fund.five_yr_avg_div_yield.toFixed(2) + '%' : null),
    ]));

    // HOLDINGS
    cards.push(buildCard('Holdings', [
        cardRow('Insider Hold', gv('held_pct_insiders') != null ? fmtPct(fund.held_pct_insiders) : null),
        cardRow('Inst Hold', gv('held_pct_institutions') != null ? fmtPct(fund.held_pct_institutions) : null),
        cardRow('Shares Out', fund.shares_outstanding ? (fund.shares_outstanding / 1e7).toFixed(2) + ' Cr' : null),
        cardRow('Float Shares', fund.float_shares ? (fund.float_shares / 1e7).toFixed(2) + ' Cr' : null),
        cardRow('Employees', fund.full_time_employees ? fund.full_time_employees.toLocaleString() : null),
    ]));

    // 52W RANGE - special card with visual bar
    if (fund.fifty_two_week_high != null && fund.fifty_two_week_low != null) {{
        const low52 = fund.fifty_two_week_low;
        const high52 = fund.fifty_two_week_high;
        const curPrice = stock.close;
        const range = high52 - low52;
        const pct = range > 0 ? Math.max(0, Math.min(100, ((curPrice - low52) / range) * 100)) : 50;
        const rangeCard = `<div class="detail-card"><div class="detail-card-header">52W Range</div>`
            + `<div class="detail-range-bar"><div class="detail-range-marker" style="left:calc(${{pct.toFixed(1)}}% - 4px)"></div></div>`
            + `<div class="detail-range-labels"><span>\\u20b9${{fmtNum(low52)}}</span><span style="color:var(--text-primary);font-weight:600;">\\u20b9${{fmtNum(curPrice)}}</span><span>\\u20b9${{fmtNum(high52)}}</span></div>`
            + cardRow('50D Avg', fund.fifty_day_average ? '\\u20b9' + fmtNum(fund.fifty_day_average) : null)
            + cardRow('200D Avg', fund.two_hundred_day_avg ? '\\u20b9' + fmtNum(fund.two_hundred_day_avg) : null)
            + cardRow('Beta', fmtNum(fund.beta))
            + `</div>`;
        cards.push(rangeCard);
    }}

    // TARGETS
    cards.push(buildCard('Targets', [
        cardRow('Target High', gv('target_high_price') != null ? '\\u20b9' + fmtNum(fund.target_high_price) : null),
        cardRow('Target Low', gv('target_low_price') != null ? '\\u20b9' + fmtNum(fund.target_low_price) : null),
        cardRow('Target Mean', gv('target_mean_price') != null ? '\\u20b9' + fmtNum(fund.target_mean_price) : null),
        cardRow('Recommendation', fund.recommendation ? fund.recommendation.toUpperCase() : null),
        cardRow('Analysts', fund.num_analyst_opinions || null),
    ]));

    // Render all non-empty cards
    document.getElementById('detail-cards').innerHTML = cards.filter(c => c !== '').join('');

    // Tags
    const tags = [stock.sector, stock.market_cap_cat, stock.industry, stock.exchange].filter(t => t && t !== 'Unknown');
    if (fund.website) tags.push(fund.website.replace('https://','').replace('http://',''));
    if (fund.city) tags.push(fund.city);
    document.getElementById('detail-tags').innerHTML = tags.map(t => `<span class="fs-panel-tag">${{t}}</span>`).join('');

    // Update header with long name
    if (fund.long_name) {{
        document.getElementById('detail-name').textContent = fund.long_name;
    }}

    // About section
    const aboutEl = document.getElementById('detail-about');
    if (fund.long_business_summary) {{
        const text = fund.long_business_summary;
        aboutEl.textContent = text.length > 500 ? text.substring(0, 500) + '...' : text;
    }} else {{
        aboutEl.textContent = '';
    }}
}}

function detailFullscreen(mode) {{
    const splitEl = document.getElementById('detail-split');
    const viewEl = document.getElementById('stock-detail-view');

    // Reset classes
    splitEl.classList.remove('fs-chart', 'fs-data');

    if (mode === 'chart') {{
        splitEl.classList.add('fs-chart');
        detailFsMode = 'chart';
    }} else if (mode === 'data') {{
        splitEl.classList.add('fs-data');
        detailFsMode = 'data';
    }} else {{
        detailFsMode = null;
    }}

    // Request browser fullscreen on the detail view
    if (!document.fullscreenElement) {{
        viewEl.requestFullscreen().catch(() => {{}});
    }}

    // Re-fit chart after layout change
    setTimeout(() => {{
        if (detailChartInstance) {{
            const container = document.getElementById('detail-chart-container');
            detailChartInstance.applyOptions({{
                width: container.clientWidth,
                height: container.clientHeight,
            }});
            detailChartInstance.timeScale().fitContent();
        }}
    }}, 100);
}}

// Restore detail split when exiting fullscreen
document.addEventListener('fullscreenchange', () => {{
    if (!document.fullscreenElement && detailViewOpen) {{
        const splitEl = document.getElementById('detail-split');
        splitEl.classList.remove('fs-chart', 'fs-data');
        detailFsMode = null;
        // Re-fit chart
        setTimeout(() => {{
            if (detailChartInstance) {{
                const container = document.getElementById('detail-chart-container');
                detailChartInstance.applyOptions({{
                    width: container.clientWidth,
                    height: container.clientHeight,
                }});
                detailChartInstance.timeScale().fitContent();
            }}
        }}, 100);
    }}
}});

// Keyboard shortcuts
document.addEventListener('keydown', e => {{
    // Stock detail view takes priority
    if (detailViewOpen) {{
        if (e.key === 'Escape') {{ closeStockDetail(); e.preventDefault(); return; }}
    }}
    if (tickerOverlayOpen) {{
        if (fsPanelOpen) {{
            if (e.key === 'Escape') {{ closeFsStockPanel(); e.preventDefault(); return; }}
        }} else {{
            if (e.key === 'Escape') {{ closeTickerOverlay(); e.preventDefault(); return; }}
        }}
        if (e.key === ' ' || e.code === 'Space') {{ toggleTickerPause(); e.preventDefault(); return; }}
        if (e.key === 'f' || e.key === 'F') {{ toggleTickerFullscreen(); e.preventDefault(); return; }}
    }} else {{
        if (e.key === 'Escape') closeChart();
    }}
}});
// ==========================================
// INDICES PANEL
// ==========================================
function openIndicesPanel() {{
    closeNavMenu();
    const overlay = document.getElementById('indices-overlay');
    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Load indices data
    fetch('data/indices.json')
        .then(r => r.ok ? r.json() : Promise.reject('Not found'))
        .then(data => renderIndicesPanel(data))
        .catch(() => {{
            document.getElementById('indices-content').innerHTML =
                '<div style="text-align:center;color:#8b949e;padding:40px;">Indices data not available. Run python main.py to fetch.</div>';
        }});
}}

function closeIndicesPanel() {{
    document.getElementById('indices-overlay').style.display = 'none';
    document.body.style.overflow = '';
}}

let indicesData = null;

function renderIndicesPanel(data) {{
    indicesData = data;
    const regions = Object.keys(data);

    // Build tabs
    const tabsContainer = document.getElementById('indices-tabs');
    tabsContainer.innerHTML = regions.map((region, i) => {{
        const short = region.replace('India - ', '').replace('United States', 'US').replace('Asia Pacific', 'Asia');
        return `<button class="idx-tab ${{i === 0 ? 'active' : ''}}" onclick="switchIndicesTab('${{region}}', this)">${{short}}</button>`;
    }}).join('');

    // Show first tab
    showIndicesRegion(regions[0]);
}}

function switchIndicesTab(region, btn) {{
    document.querySelectorAll('.idx-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    showIndicesRegion(region);
}}

function showIndicesRegion(region) {{
    const container = document.getElementById('indices-content');
    const indices = indicesData[region] || [];

    let html = '<div class="idx-grid">';
    for (const idx of indices) {{
        const isUp = idx.change_pct >= 0;
        const arrow = isUp ? '\u25b2' : '\u25bc';
        const cls = isUp ? 'green' : 'red';
        const sign = isUp ? '+' : '';

        html += `<div class="idx-card">
            <div class="idx-name">${{idx.name}}</div>
            <div class="idx-price">${{idx.close.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</div>
            <div class="idx-change ${{cls}}">
                ${{arrow}} ${{sign}}${{idx.change.toFixed(2)}}
                <span class="idx-pct ${{cls}}">${{sign}}${{idx.change_pct.toFixed(2)}}%</span>
            </div>
            <div class="idx-meta">
                <span>O: ${{idx.open.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</span>
                <span>H: ${{idx.high.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</span>
                <span>L: ${{idx.low.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</span>
            </div>
            <div class="idx-date">${{idx.date}}</div>
        </div>`;
    }}
    html += '</div>';
    container.innerHTML = html;
}}
</script>

<!-- Indices Overlay Panel -->
<div id="indices-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:#0d1117;z-index:10002;flex-direction:column;">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 24px;border-bottom:1px solid #30363d;">
        <div style="display:flex;align-items:center;gap:16px;">
            <button onclick="closeIndicesPanel()" style="background:none;border:1px solid #30363d;color:#e6edf3;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;">&larr; Back</button>
            <h2 style="margin:0;color:#58a6ff;font-size:20px;font-weight:700;">Market Indices</h2>
        </div>
    </div>
    <div id="indices-tabs" style="display:flex;gap:8px;padding:12px 24px;border-bottom:1px solid #21262d;flex-wrap:wrap;"></div>
    <div id="indices-content" style="flex:1;overflow-y:auto;padding:20px 24px;">
        <div style="text-align:center;color:#8b949e;padding:40px;">Loading indices...</div>
    </div>
</div>

<style>
.idx-tab {{
    background: none; border: 1px solid #30363d; color: #8b949e;
    padding: 8px 18px; border-radius: 20px; cursor: pointer;
    font-size: 13px; font-weight: 600; transition: all 0.2s;
}}
.idx-tab:hover {{ border-color: #58a6ff; color: #e6edf3; }}
.idx-tab.active {{ background: #58a6ff; color: #fff; border-color: #58a6ff; }}
.idx-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
}}
.idx-card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 16px; transition: all 0.2s;
}}
.idx-card:hover {{ border-color: #58a6ff; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
.idx-name {{ font-size: 13px; color: #8b949e; font-weight: 600; margin-bottom: 6px; }}
.idx-price {{ font-size: 22px; font-weight: 700; color: #e6edf3; margin-bottom: 4px; }}
.idx-change {{ font-size: 14px; font-weight: 600; margin-bottom: 8px; }}
.idx-change.green {{ color: #26a641; }}
.idx-change.red {{ color: #f85149; }}
.idx-pct {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 12px; font-weight: 700; margin-left: 6px;
}}
.idx-pct.green {{ background: rgba(38,166,65,0.15); }}
.idx-pct.red {{ background: rgba(248,81,73,0.15); }}
.idx-meta {{ font-size: 11px; color: #484f58; display: flex; gap: 8px; margin-bottom: 4px; }}
.idx-date {{ font-size: 10px; color: #30363d; }}

@media (max-width: 768px) {{
    .idx-grid {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
    .idx-card {{ padding: 12px; }}
    .idx-price {{ font-size: 18px; }}
}}
</style>
</body>
</html>"""
