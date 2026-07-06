"""
US stock symbols — S&P 500 + NASDAQ 100 combined.
Downloads the S&P 500 list from Wikipedia and NASDAQ 100 constituents,
caches them locally, and returns the merged list.

For yfinance, US tickers have NO suffix (e.g. AAPL, MSFT, GOOGL).
"""
import os
import csv
from datetime import datetime, timedelta
from config import BASE_DIR

US_SYMBOLS_CACHE = os.path.join(BASE_DIR, "us_symbols_cache.csv")


# Fallback list of top US stocks (used if online fetch fails).
# Covers S&P 500 large caps + NASDAQ 100. Curated ~500 tickers.
US_FALLBACK = [
    # Mega-cap tech
    ("AAPL", "Apple Inc.", "NASDAQ"),
    ("MSFT", "Microsoft Corporation", "NASDAQ"),
    ("GOOGL", "Alphabet Inc. Class A", "NASDAQ"),
    ("GOOG", "Alphabet Inc. Class C", "NASDAQ"),
    ("AMZN", "Amazon.com Inc.", "NASDAQ"),
    ("META", "Meta Platforms Inc.", "NASDAQ"),
    ("NVDA", "NVIDIA Corporation", "NASDAQ"),
    ("TSLA", "Tesla Inc.", "NASDAQ"),
    ("AVGO", "Broadcom Inc.", "NASDAQ"),
    ("BRK-B", "Berkshire Hathaway Inc. Class B", "NYSE"),
    # Financials
    ("JPM", "JPMorgan Chase & Co.", "NYSE"),
    ("V", "Visa Inc.", "NYSE"),
    ("MA", "Mastercard Incorporated", "NYSE"),
    ("BAC", "Bank of America Corporation", "NYSE"),
    ("WFC", "Wells Fargo & Company", "NYSE"),
    ("GS", "The Goldman Sachs Group Inc.", "NYSE"),
    ("MS", "Morgan Stanley", "NYSE"),
    ("C", "Citigroup Inc.", "NYSE"),
    ("AXP", "American Express Company", "NYSE"),
    ("BLK", "BlackRock Inc.", "NYSE"),
    ("SCHW", "The Charles Schwab Corporation", "NYSE"),
    ("SPGI", "S&P Global Inc.", "NYSE"),
    ("CB", "Chubb Limited", "NYSE"),
    ("PGR", "The Progressive Corporation", "NYSE"),
    ("MMC", "Marsh & McLennan Companies Inc.", "NYSE"),
    ("CME", "CME Group Inc.", "NASDAQ"),
    ("ICE", "Intercontinental Exchange Inc.", "NYSE"),
    ("USB", "U.S. Bancorp", "NYSE"),
    ("PNC", "The PNC Financial Services Group Inc.", "NYSE"),
    ("TFC", "Truist Financial Corporation", "NYSE"),
    ("COF", "Capital One Financial Corporation", "NYSE"),
    ("AIG", "American International Group Inc.", "NYSE"),
    ("MET", "MetLife Inc.", "NYSE"),
    ("PRU", "Prudential Financial Inc.", "NYSE"),
    ("AON", "Aon plc", "NYSE"),
    ("TRV", "The Travelers Companies Inc.", "NYSE"),
    ("ALL", "The Allstate Corporation", "NYSE"),
    # Healthcare & Pharma
    ("LLY", "Eli Lilly and Company", "NYSE"),
    ("UNH", "UnitedHealth Group Incorporated", "NYSE"),
    ("JNJ", "Johnson & Johnson", "NYSE"),
    ("MRK", "Merck & Co. Inc.", "NYSE"),
    ("ABBV", "AbbVie Inc.", "NYSE"),
    ("TMO", "Thermo Fisher Scientific Inc.", "NYSE"),
    ("ABT", "Abbott Laboratories", "NYSE"),
    ("DHR", "Danaher Corporation", "NYSE"),
    ("PFE", "Pfizer Inc.", "NYSE"),
    ("AMGN", "Amgen Inc.", "NASDAQ"),
    ("BMY", "Bristol-Myers Squibb Company", "NYSE"),
    ("GILD", "Gilead Sciences Inc.", "NASDAQ"),
    ("CVS", "CVS Health Corporation", "NYSE"),
    ("CI", "The Cigna Group", "NYSE"),
    ("HUM", "Humana Inc.", "NYSE"),
    ("ELV", "Elevance Health Inc.", "NYSE"),
    ("MDT", "Medtronic plc", "NYSE"),
    ("SYK", "Stryker Corporation", "NYSE"),
    ("BSX", "Boston Scientific Corporation", "NYSE"),
    ("REGN", "Regeneron Pharmaceuticals Inc.", "NASDAQ"),
    ("VRTX", "Vertex Pharmaceuticals Incorporated", "NASDAQ"),
    ("ISRG", "Intuitive Surgical Inc.", "NASDAQ"),
    ("BIIB", "Biogen Inc.", "NASDAQ"),
    ("MRNA", "Moderna Inc.", "NASDAQ"),
    ("ZTS", "Zoetis Inc.", "NYSE"),
    ("MCK", "McKesson Corporation", "NYSE"),
    ("COR", "Cencora Inc.", "NYSE"),
    ("HCA", "HCA Healthcare Inc.", "NYSE"),
    ("ILMN", "Illumina Inc.", "NASDAQ"),
    ("IDXX", "IDEXX Laboratories Inc.", "NASDAQ"),
    ("A", "Agilent Technologies Inc.", "NYSE"),
    ("EW", "Edwards Lifesciences Corporation", "NYSE"),
    ("IQV", "IQVIA Holdings Inc.", "NYSE"),
    ("RMD", "ResMed Inc.", "NYSE"),
    ("DXCM", "DexCom Inc.", "NASDAQ"),
    # Consumer & Retail
    ("WMT", "Walmart Inc.", "NYSE"),
    ("HD", "The Home Depot Inc.", "NYSE"),
    ("COST", "Costco Wholesale Corporation", "NASDAQ"),
    ("PG", "The Procter & Gamble Company", "NYSE"),
    ("KO", "The Coca-Cola Company", "NYSE"),
    ("PEP", "PepsiCo Inc.", "NASDAQ"),
    ("MCD", "McDonald's Corporation", "NYSE"),
    ("NKE", "NIKE Inc.", "NYSE"),
    ("SBUX", "Starbucks Corporation", "NASDAQ"),
    ("TGT", "Target Corporation", "NYSE"),
    ("LOW", "Lowe's Companies Inc.", "NYSE"),
    ("PM", "Philip Morris International Inc.", "NYSE"),
    ("MO", "Altria Group Inc.", "NYSE"),
    ("MDLZ", "Mondelez International Inc.", "NASDAQ"),
    ("CL", "Colgate-Palmolive Company", "NYSE"),
    ("EL", "The Estee Lauder Companies Inc.", "NYSE"),
    ("KMB", "Kimberly-Clark Corporation", "NYSE"),
    ("GIS", "General Mills Inc.", "NYSE"),
    ("K", "Kellanova", "NYSE"),
    ("HSY", "The Hershey Company", "NYSE"),
    ("STZ", "Constellation Brands Inc.", "NYSE"),
    ("KHC", "The Kraft Heinz Company", "NASDAQ"),
    ("KDP", "Keurig Dr Pepper Inc.", "NASDAQ"),
    ("MNST", "Monster Beverage Corporation", "NASDAQ"),
    ("SYY", "Sysco Corporation", "NYSE"),
    ("KR", "The Kroger Co.", "NYSE"),
    ("WBA", "Walgreens Boots Alliance Inc.", "NASDAQ"),
    ("DG", "Dollar General Corporation", "NYSE"),
    ("DLTR", "Dollar Tree Inc.", "NASDAQ"),
    ("YUM", "Yum! Brands Inc.", "NYSE"),
    ("CMG", "Chipotle Mexican Grill Inc.", "NYSE"),
    ("BKNG", "Booking Holdings Inc.", "NASDAQ"),
    ("MAR", "Marriott International Inc.", "NASDAQ"),
    ("HLT", "Hilton Worldwide Holdings Inc.", "NYSE"),
    ("F", "Ford Motor Company", "NYSE"),
    ("GM", "General Motors Company", "NYSE"),
    ("ORLY", "O'Reilly Automotive Inc.", "NASDAQ"),
    ("AZO", "AutoZone Inc.", "NYSE"),
    ("ULTA", "Ulta Beauty Inc.", "NASDAQ"),
    ("ROST", "Ross Stores Inc.", "NASDAQ"),
    ("TJX", "The TJX Companies Inc.", "NYSE"),
    ("BBY", "Best Buy Co. Inc.", "NYSE"),
    ("EBAY", "eBay Inc.", "NASDAQ"),
    ("ETSY", "Etsy Inc.", "NASDAQ"),
    ("W", "Wayfair Inc.", "NYSE"),
    ("CROX", "Crocs Inc.", "NASDAQ"),
    ("LULU", "Lululemon Athletica Inc.", "NASDAQ"),
    # Tech beyond mega-cap
    ("ORCL", "Oracle Corporation", "NYSE"),
    ("CRM", "Salesforce Inc.", "NYSE"),
    ("ADBE", "Adobe Inc.", "NASDAQ"),
    ("NFLX", "Netflix Inc.", "NASDAQ"),
    ("AMD", "Advanced Micro Devices Inc.", "NASDAQ"),
    ("INTC", "Intel Corporation", "NASDAQ"),
    ("QCOM", "QUALCOMM Incorporated", "NASDAQ"),
    ("TXN", "Texas Instruments Incorporated", "NASDAQ"),
    ("MU", "Micron Technology Inc.", "NASDAQ"),
    ("AMAT", "Applied Materials Inc.", "NASDAQ"),
    ("LRCX", "Lam Research Corporation", "NASDAQ"),
    ("KLAC", "KLA Corporation", "NASDAQ"),
    ("ADI", "Analog Devices Inc.", "NASDAQ"),
    ("MRVL", "Marvell Technology Inc.", "NASDAQ"),
    ("SNPS", "Synopsys Inc.", "NASDAQ"),
    ("CDNS", "Cadence Design Systems Inc.", "NASDAQ"),
    ("PANW", "Palo Alto Networks Inc.", "NASDAQ"),
    ("CRWD", "CrowdStrike Holdings Inc.", "NASDAQ"),
    ("FTNT", "Fortinet Inc.", "NASDAQ"),
    ("NOW", "ServiceNow Inc.", "NYSE"),
    ("INTU", "Intuit Inc.", "NASDAQ"),
    ("IBM", "International Business Machines Corporation", "NYSE"),
    ("ACN", "Accenture plc", "NYSE"),
    ("CSCO", "Cisco Systems Inc.", "NASDAQ"),
    ("UBER", "Uber Technologies Inc.", "NYSE"),
    ("LYFT", "Lyft Inc.", "NASDAQ"),
    ("SQ", "Block Inc.", "NYSE"),
    ("PYPL", "PayPal Holdings Inc.", "NASDAQ"),
    ("SHOP", "Shopify Inc.", "NASDAQ"),
    ("SNAP", "Snap Inc.", "NYSE"),
    ("PINS", "Pinterest Inc.", "NYSE"),
    ("SPOT", "Spotify Technology S.A.", "NYSE"),
    ("ZM", "Zoom Communications Inc.", "NASDAQ"),
    ("DDOG", "Datadog Inc.", "NASDAQ"),
    ("SNOW", "Snowflake Inc.", "NYSE"),
    ("PLTR", "Palantir Technologies Inc.", "NASDAQ"),
    ("NET", "Cloudflare Inc.", "NYSE"),
    ("MDB", "MongoDB Inc.", "NASDAQ"),
    ("OKTA", "Okta Inc.", "NASDAQ"),
    ("ZS", "Zscaler Inc.", "NASDAQ"),
    ("TEAM", "Atlassian Corporation", "NASDAQ"),
    ("HUBS", "HubSpot Inc.", "NYSE"),
    ("WDAY", "Workday Inc.", "NASDAQ"),
    ("ROKU", "Roku Inc.", "NASDAQ"),
    ("ABNB", "Airbnb Inc.", "NASDAQ"),
    ("COIN", "Coinbase Global Inc.", "NASDAQ"),
    ("HOOD", "Robinhood Markets Inc.", "NASDAQ"),
    ("RBLX", "Roblox Corporation", "NYSE"),
    ("U", "Unity Software Inc.", "NYSE"),
    ("DASH", "DoorDash Inc.", "NASDAQ"),
    ("RIVN", "Rivian Automotive Inc.", "NASDAQ"),
    ("LCID", "Lucid Group Inc.", "NASDAQ"),
    ("NIO", "NIO Inc.", "NYSE"),
    ("XPEV", "XPeng Inc.", "NYSE"),
    ("LI", "Li Auto Inc.", "NASDAQ"),
    ("BABA", "Alibaba Group Holding Limited", "NYSE"),
    ("JD", "JD.com Inc.", "NASDAQ"),
    ("PDD", "PDD Holdings Inc.", "NASDAQ"),
    ("BIDU", "Baidu Inc.", "NASDAQ"),
    # Communications & Media
    ("DIS", "The Walt Disney Company", "NYSE"),
    ("CMCSA", "Comcast Corporation", "NASDAQ"),
    ("T", "AT&T Inc.", "NYSE"),
    ("VZ", "Verizon Communications Inc.", "NYSE"),
    ("TMUS", "T-Mobile US Inc.", "NASDAQ"),
    ("CHTR", "Charter Communications Inc.", "NASDAQ"),
    ("PARA", "Paramount Global", "NASDAQ"),
    ("WBD", "Warner Bros. Discovery Inc.", "NASDAQ"),
    ("FOXA", "Fox Corporation", "NASDAQ"),
    ("EA", "Electronic Arts Inc.", "NASDAQ"),
    ("TTWO", "Take-Two Interactive Software Inc.", "NASDAQ"),
    ("NWSA", "News Corporation", "NASDAQ"),
    # Industrial & Manufacturing
    ("CAT", "Caterpillar Inc.", "NYSE"),
    ("BA", "The Boeing Company", "NYSE"),
    ("HON", "Honeywell International Inc.", "NASDAQ"),
    ("UPS", "United Parcel Service Inc.", "NYSE"),
    ("RTX", "RTX Corporation", "NYSE"),
    ("LMT", "Lockheed Martin Corporation", "NYSE"),
    ("GE", "GE Aerospace", "NYSE"),
    ("DE", "Deere & Company", "NYSE"),
    ("MMM", "3M Company", "NYSE"),
    ("EMR", "Emerson Electric Co.", "NYSE"),
    ("ETN", "Eaton Corporation plc", "NYSE"),
    ("PH", "Parker-Hannifin Corporation", "NYSE"),
    ("ITW", "Illinois Tool Works Inc.", "NYSE"),
    ("CSX", "CSX Corporation", "NASDAQ"),
    ("UNP", "Union Pacific Corporation", "NYSE"),
    ("NSC", "Norfolk Southern Corporation", "NYSE"),
    ("FDX", "FedEx Corporation", "NYSE"),
    ("WM", "Waste Management Inc.", "NYSE"),
    ("NOC", "Northrop Grumman Corporation", "NYSE"),
    ("GD", "General Dynamics Corporation", "NYSE"),
    ("PCAR", "PACCAR Inc", "NASDAQ"),
    ("CMI", "Cummins Inc.", "NYSE"),
    ("ROP", "Roper Technologies Inc.", "NASDAQ"),
    ("PWR", "Quanta Services Inc.", "NYSE"),
    ("URI", "United Rentals Inc.", "NYSE"),
    ("FAST", "Fastenal Company", "NASDAQ"),
    ("PAYX", "Paychex Inc.", "NASDAQ"),
    ("ADP", "Automatic Data Processing Inc.", "NASDAQ"),
    ("VRSK", "Verisk Analytics Inc.", "NASDAQ"),
    ("MSCI", "MSCI Inc.", "NYSE"),
    ("MCO", "Moody's Corporation", "NYSE"),
    ("FICO", "Fair Isaac Corporation", "NYSE"),
    # Energy
    ("XOM", "Exxon Mobil Corporation", "NYSE"),
    ("CVX", "Chevron Corporation", "NYSE"),
    ("COP", "ConocoPhillips", "NYSE"),
    ("SLB", "Schlumberger Limited", "NYSE"),
    ("EOG", "EOG Resources Inc.", "NYSE"),
    ("PXD", "Pioneer Natural Resources Company", "NYSE"),
    ("MPC", "Marathon Petroleum Corporation", "NYSE"),
    ("PSX", "Phillips 66", "NYSE"),
    ("VLO", "Valero Energy Corporation", "NYSE"),
    ("OXY", "Occidental Petroleum Corporation", "NYSE"),
    ("HAL", "Halliburton Company", "NYSE"),
    ("BKR", "Baker Hughes Company", "NASDAQ"),
    ("DVN", "Devon Energy Corporation", "NYSE"),
    ("FANG", "Diamondback Energy Inc.", "NASDAQ"),
    ("HES", "Hess Corporation", "NYSE"),
    ("KMI", "Kinder Morgan Inc.", "NYSE"),
    ("WMB", "The Williams Companies Inc.", "NYSE"),
    ("OKE", "ONEOK Inc.", "NYSE"),
    # Materials
    ("LIN", "Linde plc", "NYSE"),
    ("APD", "Air Products and Chemicals Inc.", "NYSE"),
    ("SHW", "The Sherwin-Williams Company", "NYSE"),
    ("ECL", "Ecolab Inc.", "NYSE"),
    ("FCX", "Freeport-McMoRan Inc.", "NYSE"),
    ("NEM", "Newmont Corporation", "NYSE"),
    ("DOW", "Dow Inc.", "NYSE"),
    ("DD", "DuPont de Nemours Inc.", "NYSE"),
    ("PPG", "PPG Industries Inc.", "NYSE"),
    ("NUE", "Nucor Corporation", "NYSE"),
    ("STLD", "Steel Dynamics Inc.", "NASDAQ"),
    ("VMC", "Vulcan Materials Company", "NYSE"),
    ("MLM", "Martin Marietta Materials Inc.", "NYSE"),
    # Utilities
    ("NEE", "NextEra Energy Inc.", "NYSE"),
    ("DUK", "Duke Energy Corporation", "NYSE"),
    ("SO", "The Southern Company", "NYSE"),
    ("D", "Dominion Energy Inc.", "NYSE"),
    ("SRE", "Sempra", "NYSE"),
    ("AEP", "American Electric Power Company Inc.", "NASDAQ"),
    ("EXC", "Exelon Corporation", "NASDAQ"),
    ("XEL", "Xcel Energy Inc.", "NASDAQ"),
    ("ED", "Consolidated Edison Inc.", "NYSE"),
    ("PEG", "Public Service Enterprise Group Incorporated", "NYSE"),
    ("PCG", "PG&E Corporation", "NYSE"),
    ("VST", "Vistra Corp.", "NYSE"),
    ("CEG", "Constellation Energy Corporation", "NASDAQ"),
    # Real Estate (REITs)
    ("PLD", "Prologis Inc.", "NYSE"),
    ("AMT", "American Tower Corporation", "NYSE"),
    ("EQIX", "Equinix Inc.", "NASDAQ"),
    ("PSA", "Public Storage", "NYSE"),
    ("CCI", "Crown Castle Inc.", "NYSE"),
    ("SPG", "Simon Property Group Inc.", "NYSE"),
    ("O", "Realty Income Corporation", "NYSE"),
    ("WELL", "Welltower Inc.", "NYSE"),
    ("DLR", "Digital Realty Trust Inc.", "NYSE"),
    ("VICI", "VICI Properties Inc.", "NYSE"),
    ("AVB", "AvalonBay Communities Inc.", "NYSE"),
    ("EQR", "Equity Residential", "NYSE"),
    ("EXR", "Extra Space Storage Inc.", "NYSE"),
    ("SBAC", "SBA Communications Corporation", "NASDAQ"),
    # Aerospace & Defense (additional)
    ("TDG", "TransDigm Group Incorporated", "NYSE"),
    ("LDOS", "Leidos Holdings Inc.", "NYSE"),
    ("LHX", "L3Harris Technologies Inc.", "NYSE"),
    # ETFs — most popular
    ("SPY", "SPDR S&P 500 ETF Trust", "NYSE"),
    ("QQQ", "Invesco QQQ Trust", "NASDAQ"),
    ("VOO", "Vanguard S&P 500 ETF", "NYSE"),
    ("IVV", "iShares Core S&P 500 ETF", "NYSE"),
    ("VTI", "Vanguard Total Stock Market ETF", "NYSE"),
    ("DIA", "SPDR Dow Jones Industrial Average ETF", "NYSE"),
    ("IWM", "iShares Russell 2000 ETF", "NYSE"),
    ("EFA", "iShares MSCI EAFE ETF", "NYSE"),
    ("EEM", "iShares MSCI Emerging Markets ETF", "NYSE"),
    ("VEA", "Vanguard FTSE Developed Markets ETF", "NYSE"),
    ("AGG", "iShares Core U.S. Aggregate Bond ETF", "NYSE"),
    ("BND", "Vanguard Total Bond Market ETF", "NASDAQ"),
    ("TLT", "iShares 20+ Year Treasury Bond ETF", "NASDAQ"),
    ("GLD", "SPDR Gold Shares", "NYSE"),
    ("SLV", "iShares Silver Trust", "NYSE"),
    ("XLE", "Energy Select Sector SPDR Fund", "NYSE"),
    ("XLF", "Financial Select Sector SPDR Fund", "NYSE"),
    ("XLK", "Technology Select Sector SPDR Fund", "NYSE"),
    ("XLV", "Health Care Select Sector SPDR Fund", "NYSE"),
    ("XLI", "Industrial Select Sector SPDR Fund", "NYSE"),
    ("XLP", "Consumer Staples Select Sector SPDR Fund", "NYSE"),
    ("XLY", "Consumer Discretionary Select Sector SPDR Fund", "NYSE"),
    ("XLU", "Utilities Select Sector SPDR Fund", "NYSE"),
    ("XLB", "Materials Select Sector SPDR Fund", "NYSE"),
    ("XLRE", "Real Estate Select Sector SPDR Fund", "NYSE"),
]


def _save_cache(stocks: list[dict]):
    """Save US stock list to local cache."""
    with open(US_SYMBOLS_CACHE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "name", "exchange", "yf_symbol"])
        writer.writeheader()
        writer.writerows(stocks)
    print(f"[US CACHE] Saved {len(stocks)} symbols to {US_SYMBOLS_CACHE}")


def _load_cache() -> list[dict]:
    """Load US stock list from local cache."""
    if not os.path.exists(US_SYMBOLS_CACHE):
        return []
    with open(US_SYMBOLS_CACHE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _cache_is_fresh(max_age_days: int = 30) -> bool:
    """US list changes rarely — check if cache is less than 30 days old."""
    if not os.path.exists(US_SYMBOLS_CACHE):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(US_SYMBOLS_CACHE))
    return (datetime.now() - mtime) < timedelta(days=max_age_days)


def get_us_symbols(force_refresh: bool = False) -> list[dict]:
    """
    Get US stock symbols (S&P 500 + NASDAQ 100 top names + top ETFs).
    Returns list of dicts: [{"symbol", "name", "exchange", "yf_symbol"}, ...]
    """
    if not force_refresh and _cache_is_fresh():
        stocks = _load_cache()
        print(f"[US SYMBOLS] Using cached list ({len(stocks)} stocks)")
        return stocks

    # Build from curated fallback list (reliable, no external dependency)
    stocks = [
        {
            "symbol": ticker,
            "name": name,
            "exchange": exch,
            "yf_symbol": ticker,  # US tickers have no suffix in yfinance
        }
        for ticker, name, exch in US_FALLBACK
    ]

    _save_cache(stocks)
    print(f"[US SYMBOLS] Built list with {len(stocks)} US stocks")
    return stocks


if __name__ == "__main__":
    stocks = get_us_symbols()
    print(f"\nTotal US stocks: {len(stocks)}")
    print(f"First 5: {stocks[:5]}")
