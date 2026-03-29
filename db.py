"""
SQLite database layer for storing stock data.
"""
import sqlite3
import pandas as pd
from config import DB_PATH


def get_connection():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eod_prices (
            symbol TEXT NOT NULL,
            date   TEXT NOT NULL,
            open   REAL,
            high   REAL,
            low    REAL,
            close  REAL,
            volume INTEGER,
            PRIMARY KEY (symbol, date),
            FOREIGN KEY (symbol) REFERENCES stocks(symbol)
        )
    """)

    # Stock metadata: sector, industry, market cap
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_info (
            symbol          TEXT PRIMARY KEY,
            sector          TEXT DEFAULT 'Unknown',
            industry        TEXT DEFAULT 'Unknown',
            market_cap      REAL DEFAULT 0,
            market_cap_cat  TEXT DEFAULT 'Unknown',
            updated_at      TEXT,
            FOREIGN KEY (symbol) REFERENCES stocks(symbol)
        )
    """)

    # Stock fundamentals: detailed financial data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_fundamentals (
            symbol                TEXT PRIMARY KEY,
            long_name             TEXT,
            long_business_summary TEXT,
            website               TEXT,
            city                  TEXT,
            full_time_employees   INTEGER,
            trailing_pe           REAL,
            forward_pe            REAL,
            price_to_book         REAL,
            book_value            REAL,
            eps_trailing          REAL,
            eps_forward           REAL,
            dividend_rate         REAL,
            dividend_yield        REAL,
            payout_ratio          REAL,
            five_yr_avg_div_yield REAL,
            revenue               REAL,
            revenue_per_share     REAL,
            revenue_growth        REAL,
            ebitda                REAL,
            ebitda_margins        REAL,
            gross_margins         REAL,
            operating_margins     REAL,
            profit_margins        REAL,
            net_income            REAL,
            total_cash            REAL,
            total_cash_per_share  REAL,
            total_debt            REAL,
            debt_to_equity        REAL,
            current_ratio         REAL,
            free_cashflow         REAL,
            return_on_equity      REAL,
            enterprise_value      REAL,
            enterprise_to_ebitda  REAL,
            enterprise_to_revenue REAL,
            earnings_growth       REAL,
            shares_outstanding    REAL,
            float_shares          REAL,
            held_pct_insiders     REAL,
            held_pct_institutions REAL,
            beta                  REAL,
            fifty_two_week_high   REAL,
            fifty_two_week_low    REAL,
            fifty_day_average     REAL,
            two_hundred_day_avg   REAL,
            target_high_price     REAL,
            target_low_price      REAL,
            target_mean_price     REAL,
            recommendation        TEXT,
            num_analyst_opinions  INTEGER,
            all_time_high         REAL,
            all_time_low          REAL,
            updated_at            TEXT,
            FOREIGN KEY (symbol) REFERENCES stocks(symbol)
        )
    """)

    # Index for faster latest-price lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_eod_symbol_date
        ON eod_prices (symbol, date DESC)
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized.")


def upsert_stock(symbol: str):
    """Insert a stock symbol if it doesn't already exist."""
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO stocks (symbol) VALUES (?)", (symbol,))
    conn.commit()
    conn.close()


def upsert_eod_prices(symbol: str, df: pd.DataFrame):
    """
    Insert or replace EOD price rows for a given symbol.
    Expects df with columns: Open, High, Low, Close, Volume and a DatetimeIndex.
    """
    conn = get_connection()
    rows = []
    for date, row in df.iterrows():
        rows.append((
            symbol,
            date.strftime("%Y-%m-%d"),
            round(float(row["Open"]), 2),
            round(float(row["High"]), 2),
            round(float(row["Low"]), 2),
            round(float(row["Close"]), 2),
            int(row["Volume"]),
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO eod_prices (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()


def load_eod_prices(symbol: str) -> pd.DataFrame:
    """Load all EOD price data for a symbol from the database."""
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM eod_prices "
        "WHERE symbol = ? ORDER BY date",
        conn,
        params=(symbol,),
        parse_dates=["date"],
        index_col="date",
    )
    conn.close()
    return df


def get_all_symbols() -> list[str]:
    """Return all tracked stock symbols."""
    conn = get_connection()
    rows = conn.execute("SELECT symbol FROM stocks ORDER BY symbol").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_latest_prices() -> list[dict]:
    """
    Get the latest EOD price row for every symbol in the database.
    Also computes daily % change vs previous close.
    Uses window functions for much faster performance on large datasets.
    """
    conn = get_connection()
    query = """
        WITH ranked AS (
            SELECT symbol, date, open, high, low, close, volume,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn,
                   LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
            FROM eod_prices
        )
        SELECT symbol, date, open, high, low, close, volume,
               COALESCE(prev_close, open) as prev_close
        FROM ranked
        WHERE rn = 1
        ORDER BY symbol
    """
    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    # Calculate daily % change
    for row in rows:
        if row["prev_close"] and row["prev_close"] != 0:
            row["change_pct"] = round(
                ((row["close"] - row["prev_close"]) / row["prev_close"]) * 100, 2
            )
        else:
            row["change_pct"] = 0.0
        row["change_abs"] = round(row["close"] - row["prev_close"], 2)

    return rows


def upsert_stock_info(symbol: str, sector: str, industry: str,
                      market_cap: float, market_cap_cat: str):
    """Insert or update stock metadata (sector, industry, market cap)."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO stock_info
            (symbol, sector, industry, market_cap, market_cap_cat, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (symbol, sector, industry, market_cap, market_cap_cat))
    conn.commit()
    conn.close()


def get_stock_info_map() -> dict[str, dict]:
    """Return a map of symbol -> {sector, industry, market_cap_cat}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT symbol, sector, industry, market_cap_cat FROM stock_info"
    ).fetchall()
    conn.close()
    return {
        r[0]: {"sector": r[1], "industry": r[2], "market_cap_cat": r[3]}
        for r in rows
    }


def upsert_stock_fundamentals(symbol: str, data: dict):
    """Insert or update stock fundamentals from yfinance .info."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO stock_fundamentals (
            symbol, long_name, long_business_summary, website, city,
            full_time_employees, trailing_pe, forward_pe, price_to_book,
            book_value, eps_trailing, eps_forward, dividend_rate,
            dividend_yield, payout_ratio, five_yr_avg_div_yield,
            revenue, revenue_per_share, revenue_growth, ebitda,
            ebitda_margins, gross_margins, operating_margins,
            profit_margins, net_income, total_cash, total_cash_per_share,
            total_debt, debt_to_equity, current_ratio, free_cashflow,
            return_on_equity, enterprise_value, enterprise_to_ebitda,
            enterprise_to_revenue, earnings_growth, shares_outstanding,
            float_shares, held_pct_insiders, held_pct_institutions,
            beta, fifty_two_week_high, fifty_two_week_low,
            fifty_day_average, two_hundred_day_avg, target_high_price,
            target_low_price, target_mean_price, recommendation,
            num_analyst_opinions, all_time_high, all_time_low, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')
        )
    """, (
        symbol,
        data.get('longName'),
        data.get('longBusinessSummary'),
        data.get('website'),
        data.get('city'),
        data.get('fullTimeEmployees'),
        data.get('trailingPE'),
        data.get('forwardPE'),
        data.get('priceToBook'),
        data.get('bookValue'),
        data.get('trailingEps'),
        data.get('forwardEps'),
        data.get('dividendRate'),
        data.get('dividendYield'),
        data.get('payoutRatio'),
        data.get('fiveYearAvgDividendYield'),
        data.get('totalRevenue'),
        data.get('revenuePerShare'),
        data.get('revenueGrowth'),
        data.get('ebitda'),
        data.get('ebitdaMargins'),
        data.get('grossMargins'),
        data.get('operatingMargins'),
        data.get('profitMargins'),
        data.get('netIncomeToCommon'),
        data.get('totalCash'),
        data.get('totalCashPerShare'),
        data.get('totalDebt'),
        data.get('debtToEquity'),
        data.get('currentRatio'),
        data.get('freeCashflow'),
        data.get('returnOnEquity'),
        data.get('enterpriseValue'),
        data.get('enterpriseToEbitda'),
        data.get('enterpriseToRevenue'),
        data.get('earningsGrowth'),
        data.get('sharesOutstanding'),
        data.get('floatShares'),
        data.get('heldPercentInsiders'),
        data.get('heldPercentInstitutions'),
        data.get('beta'),
        data.get('fiftyTwoWeekHigh'),
        data.get('fiftyTwoWeekLow'),
        data.get('fiftyDayAverage'),
        data.get('twoHundredDayAverage'),
        data.get('targetHighPrice'),
        data.get('targetLowPrice'),
        data.get('targetMeanPrice'),
        data.get('recommendationKey'),
        data.get('numberOfAnalystOpinions'),
        data.get('allTimeHigh'),
        data.get('allTimeLow'),
    ))
    conn.commit()
    conn.close()


def get_stock_fundamentals(symbol: str) -> dict:
    """Return fundamentals for a single stock."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM stock_fundamentals WHERE symbol = ?", (symbol,)
    )
    cols = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(zip(cols, row))
    return {}


def get_all_fundamentals_map() -> dict:
    """Return a map of symbol -> fundamentals dict for all stocks."""
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM stock_fundamentals")
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: dict(zip(cols, row)) for row in rows}


def get_stocks_without_fundamentals() -> list[str]:
    """Return symbols that have price data but no fundamentals."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.symbol FROM stocks s
        LEFT JOIN stock_fundamentals sf ON s.symbol = sf.symbol
        WHERE sf.symbol IS NULL
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_stocks_without_info() -> list[str]:
    """Return symbols that have price data but no stock_info row."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.symbol FROM stocks s
        LEFT JOIN stock_info si ON s.symbol = si.symbol
        WHERE si.symbol IS NULL
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_stock_count() -> int:
    """Return total number of tracked stocks."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    conn.close()
    return count
