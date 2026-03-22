"""
Configuration for EOD Stock Analysis System.
"""
import os

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "eod_stocks.db")
STOCKS_FILE = os.path.join(BASE_DIR, "stocks.txt")
REPORT_JSON = os.path.join(BASE_DIR, "report.json")
REPORT_CSV = os.path.join(BASE_DIR, "report.csv")
CHART_DIR = os.path.join(BASE_DIR, "charts")
SITE_OUTPUT = os.path.join(BASE_DIR, "index.html")
NSE_SYMBOLS_CACHE = os.path.join(BASE_DIR, "nse_symbols_cache.csv")

# Data settings
HISTORY_PERIOD = "6mo"  # Last 6 months of data
BATCH_SIZE = 50  # Number of tickers per yfinance batch download

# Indicator settings
RSI_PERIOD = 14
SMA_SHORT = 50
SMA_LONG = 200

# Analysis thresholds
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
TOP_N = 5  # Number of top gainers/losers to show
