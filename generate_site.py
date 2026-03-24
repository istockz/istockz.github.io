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
from db import get_latest_prices, get_stock_count, get_stock_info_map
from nse_symbols import get_symbol_name_map, get_symbol_exchange_map


def generate_chart_data():
    """Generate individual JSON files with OHLCV data for each stock's chart."""
    from db import get_connection

    os.makedirs(DATA_DIR, exist_ok=True)

    conn = get_connection()
    cursor = conn.execute(
        "SELECT symbol, date, open, high, low, close, volume "
        "FROM eod_prices ORDER BY symbol, date"
    )

    current_symbol = None
    current_data = []
    file_count = 0

    for row in cursor:
        symbol, date, o, h, l, c, v = row
        if symbol != current_symbol:
            # Write previous symbol's data
            if current_symbol and current_data:
                safe_name = current_symbol.replace(".", "_")
                filepath = os.path.join(DATA_DIR, f"{safe_name}.json")
                with open(filepath, "w") as f:
                    json.dump(current_data, f, separators=(",", ":"))
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
        safe_name = current_symbol.replace(".", "_")
        filepath = os.path.join(DATA_DIR, f"{safe_name}.json")
        with open(filepath, "w") as f:
            json.dump(current_data, f, separators=(",", ":"))
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
.logo {{ font-size: 22px; font-weight: 700; color: var(--blue); letter-spacing: -0.5px; }}
.logo span {{ color: var(--text-muted); font-weight: 400; font-size: 13px; margin-left: 8px; }}
.header-meta {{ color: var(--text-secondary); font-size: 13px; text-align: right; }}

/* Ticker Tape */
.ticker-wrap {{
    background: #010409; border-bottom: 1px solid var(--border);
    overflow: hidden; position: relative; height: 40px;
}}
.ticker-track {{
    display: flex; width: max-content;
    animation: ticker-scroll var(--ticker-duration, 120s) linear infinite;
}}
.ticker-track:hover {{ animation-play-state: paused; }}
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

/* Responsive */
@media (max-width: 768px) {{
    .movers-section {{ grid-template-columns: 1fr; }}
    .header-content {{ flex-direction: column; text-align: center; }}
    .stats-grid {{ flex-direction: column; }}
    .controls {{ flex-direction: column; }}
    .search-box {{ min-width: 100%; }}
    .filter-bar {{ flex-direction: column; align-items: stretch; }}
    .filter-group {{ flex-wrap: wrap; }}
    .filter-divider {{ display: none; }}
    .pagination {{ display: none; }}

    /* Table: show only Symbol, Company, Close, Chg% on mobile */
    table {{ table-layout: auto; }}
    colgroup {{ display: none; }}
    /* Hide: Sector(3), Cap(4), Exch(5), Open(6), High(7), Low(8), Change(11), Volume(12) */
    thead th:nth-child(3),
    thead th:nth-child(4),
    thead th:nth-child(5),
    thead th:nth-child(6),
    thead th:nth-child(7),
    thead th:nth-child(8),
    thead th:nth-child(11),
    thead th:nth-child(12),
    tbody td:nth-child(3),
    tbody td:nth-child(4),
    tbody td:nth-child(5),
    tbody td:nth-child(6),
    tbody td:nth-child(7),
    tbody td:nth-child(8),
    tbody td:nth-child(11),
    tbody td:nth-child(12) {{
        display: none !important;
    }}
    thead th {{ font-size: 11px; padding: 10px 8px; }}
    tbody td {{ padding: 10px 8px; font-size: 13px; }}
    tbody td:nth-child(2) {{ max-width: 120px; }}
    .table-container {{ padding: 0 12px; }}
    .controls {{ padding: 0 12px; }}
    .global-filters {{ padding: 0 12px; }}
    .stats-bar {{ padding: 12px; }}
    .movers-section {{ padding: 0 12px; }}
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
</style>
<script src="https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>

<!-- Header -->
<header class="header">
    <div class="header-content">
        <div class="logo">
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
    <div class="ticker-track" id="ticker-track"></div>
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
    <button class="filter-btn active" id="btn-all" onclick="setPriceFilter('all')">All</button>
    <button class="filter-btn" id="btn-gainers" onclick="setPriceFilter('gainers')">Gainers</button>
    <button class="filter-btn" id="btn-losers" onclick="setPriceFilter('losers')">Losers</button>
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

<script>
// ==========================================
// EMBEDDED DATA
// ==========================================
const ALL_STOCKS   = {prices_json};
const ORIG_STATS   = {stats_json};
const SECTORS_LIST = {sectors_json};
const CAPS_LIST    = {caps_json};

// ==========================================
// STATE
// ==========================================
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
    ['btn-all','btn-gainers','btn-losers'].forEach(id => document.getElementById(id).classList.remove('active'));
    document.getElementById('btn-all').classList.add('active');
    currentPage = 1;
    applyGlobalFilter();
}}

function applyGlobalFilter() {{
    // Step 1: filter by dropdowns
    globalFiltered = ALL_STOCKS.filter(s => {{
        if (activeSector !== 'all' && s.sector !== activeSector) return false;
        if (activeCap !== 'all' && s.market_cap_cat !== activeCap) return false;
        if (activeExchange !== 'all' && !(s.exchange || '').includes(activeExchange)) return false;
        return true;
    }});

    // Update active tag
    const parts = [];
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
    ['btn-all','btn-gainers','btn-losers'].forEach(id => document.getElementById(id).classList.remove('active'));
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
        return `<div class="ticker-item">`
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

function applySort() {{
    filteredData.sort((a, b) => {{
        let va = a[sortCol], vb = b[sortCol];
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
    return `<tr>
        <td style="cursor:pointer" onclick="openChart('${{s.symbol}}','${{safeName}}')">${{sym}} <span style="font-size:10px;color:var(--text-muted);margin-left:2px">&#128200;</span></td>
        <td>${{s.name || sym}}</td>
        <td class="sector-cell">${{s.sector === 'Unknown' ? '-' : s.sector}}</td>
        <td style="text-align:center"><span class="cap-badge ${{capCls}}">${{capLabel}}</span></td>
        <td style="text-align:center;font-family:sans-serif;font-size:11px">${{exchBadge}}</td>
        <td>${{fmt(s.open)}}</td>
        <td>${{fmt(s.high)}}</td>
        <td>${{fmt(s.low)}}</td>
        <td>${{fmt(s.close)}}</td>
        <td><span class="change-cell ${{cls}}">${{sign}}${{s.change_pct.toFixed(2)}}%</span></td>
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
        .then(data => renderChart(data, container, legendEl))
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
document.addEventListener('keydown', e => {{
    if (e.key === 'Escape') closeChart();
}});
</script>
</body>
</html>"""
