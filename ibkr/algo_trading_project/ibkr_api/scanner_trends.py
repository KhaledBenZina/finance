# File: big_cap_2min_trend_analysis.py

import yfinance as yf


def analyze_trend(ticker: str, period: str, n_bars: int, interval: str = "2m") -> str:
    """
    Analyzes a stock's price trend based on its high, low, and volume data.
    Args:
        ticker (str): Stock ticker symbol.
        period (str): Lookback period for the analysis (e.g., '1d', '5d', '1mo').
        n_bars (int): Number of bars to analyze for the trend.
        interval (str): Data interval (e.g., '1m', '2m', '5m').
    Returns:
        str: "trending UP", "trending DOWN", or "not trending" based on the trend analysis.
    """
    # Download historical data
    data = yf.download(ticker, period=period, interval=interval, progress=False)

    if data.empty:
        return f"No data available for {ticker}."

    # Filter last n_bars of data
    recent_data = data.tail(n_bars)
    # Extract required columns
    highs = recent_data["High"]
    lows = recent_data["Low"]
    volumes = recent_data["Volume"]

    # Check conditions for trending UP
    uptrend = (
        all(highs.iloc[i] > highs.iloc[i - 1] for i in range(1, len(highs)))
        and all(lows.iloc[i] > lows.iloc[i - 1] for i in range(1, len(lows)))
        and all(volumes.iloc[i] >= volumes.iloc[i - 1] for i in range(1, len(volumes)))
    )

    # Check conditions for trending DOWN
    downtrend = (
        all(highs.iloc[i] < highs.iloc[i - 1] for i in range(1, len(highs)))
        and all(lows.iloc[i] < lows.iloc[i - 1] for i in range(1, len(lows)))
        and all(volumes.iloc[i] >= volumes.iloc[i - 1] for i in range(1, len(volumes)))
    )

    # Return result based on trend analysis
    if uptrend:
        return "trending UP"
    elif downtrend:
        return "trending DOWN"
    else:
        return None


if __name__ == "__main__":
    # List of big-cap US stocks
    big_cap_stocks = [
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOGL",
        "GOOG",
        "FB",
        "TSLA",
        "BRK.B",
        "NVDA",
        "JPM",
        "JNJ",
        "V",
        "PG",
        "UNH",
        "HD",
        "MA",
        "DIS",
        "PYPL",
        "NFLX",
        "INTC",
        "VZ",
        "KO",
        "PFE",
        "MRK",
        "CSCO",
        "PEP",
        "ABT",
        "COST",
        "CMCSA",
        "XOM",
        "BAC",
        "WMT",
        "ADBE",
        "NKE",
        "T",
        "CRM",
        "MCD",
        "QCOM",
        "MDT",
        "LLY",
        "ORCL",
        "NEE",
        "UPS",
        "IBM",
        "TXN",
        "HON",
        "CVX",
        "BA",
        "WFC",
    ]

    period = "1d"  # Lookback period
    n_bars = 3  # Number of bars to analyze (for 2m interval, this is 30 mins of data)
    interval = "2m"  # 2-minute interval

    print("Trend Analysis for Big-Cap US Stocks (2-Minute Interval):")
    for stock in big_cap_stocks:
        try:
            trend = analyze_trend(stock, period, n_bars, interval)
            if trend != None:
                print(f"{stock}: {trend}")
        except Exception as e:
            print(f"{stock}: Error - {str(e)}")
