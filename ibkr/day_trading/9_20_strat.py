import pandas as pd
import yfinance as yf
import ta
import time


# Function to fetch stock data using yfinance
def fetch_stock_data(symbol, interval, period="1d"):
    df = yf.download(tickers=symbol, period=period, interval=interval)
    df.reset_index(inplace=True)
    df.columns = ["datetime", "open", "high", "low", "close", "adj close", "volume"]
    return df[["datetime", "open", "high", "low", "close", "volume"]]


def check_stock_trend(df):
    # Ensure data is sorted by datetime
    df = df.sort_values(by="datetime")

    # Calculate the 20 EMA
    df["EMA_20"] = ta.trend.ema_indicator(df["close"], window=20)

    # Filter the first 45 minutes of trading (from 9:30 to 10:15)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    first_45_min = df.between_time("09:30", "10:00")

    # Check for higher highs and higher lows in the first 45 minutes
    higher_highs = all(first_45_min["close"].diff().dropna() > 0)
    higher_lows = all(first_45_min["open"].diff().dropna() > 0)
    return higher_highs and higher_lows


def check_uptrend_ma(df, short_window=20, long_window=50):
    df["SMA_20"] = df["close"].rolling(window=short_window).mean()
    df["SMA_50"] = df["close"].rolling(window=long_window).mean()

    # Ensure data is sorted by datetime
    df = df.sort_values(by="datetime")

    # Check if short-term MA is above long-term MA
    return df["SMA_20"].iloc[-1] > df["SMA_50"].iloc[-1]


def fetch_historical_data(symbol, period="5y"):
    df = yf.download(tickers=symbol, period=period, interval="1d")
    return df


def is_near_all_time_high(df, threshold=0.05):
    all_time_high = df["High"].max()
    current_price = df["Close"].iloc[-1]
    return current_price >= (1 - threshold) * all_time_high


def monitor_stocks(stock_list):
    stocks_to_watch = []
    for stock in stock_list:
        print(stock)
        historical_df = fetch_historical_data(stock, period="5y")
        try:
            df = fetch_stock_data(symbol=stock, interval="5m")

            if check_uptrend_ma(df) and is_near_all_time_high(historical_df):
                print(f"UPTREND AND NEAR ALL-TIME HIGH DETECTED: {stock}")
                stocks_to_watch.append(stock)
        except Exception as e:
            continue

    print(stocks_to_watch)
    # Monitor from 10:00 to 10:30 for price approaching 20 EMA
    # monitoring_period = df.between_time("10:00", "10:30")
    # for index, row in monitoring_period.iterrows():
    #     if row["close"] < row["EMA_20"]:
    #         print(f"THIS STOCK IS INTERESTING {stock}")
    #         break
    # Wait for a specific interval before checking again (e.g., 2 minutes)
    # time.sleep(120)


if __name__ == "__main__":
    stock_list = [
        "AAPL",  # Apple Inc.
        "MSFT",  # Microsoft Corporation
        "GOOGL",  # Alphabet Inc. (Google)
        "AMZN",  # Amazon.com Inc.
        "TSLA",  # Tesla Inc.
        "FB",  # Meta Platforms Inc. (Facebook)
        "NVDA",  # NVIDIA Corporation
        "JPM",  # JPMorgan Chase & Co.
        "BAC",  # Bank of America Corporation
        "V",  # Visa Inc.
        "DIS",  # The Walt Disney Company
        "NFLX",  # Netflix Inc.
        "AMD",  # Advanced Micro Devices Inc.
        "INTC",  # Intel Corporation
        "PYPL",  # PayPal Holdings Inc.
        "CSCO",  # Cisco Systems Inc.
        "XOM",  # Exxon Mobil Corporation
        "PFE",  # Pfizer Inc.
        "KO",  # The Coca-Cola Company
        "PEP",  # PepsiCo Inc.
        "WMT",  # Walmart Inc.
        "T",  # AT&T Inc.
        "NKE",  # Nike Inc.
        "MRNA",  # Moderna Inc.
        "BA",  # The Boeing Company
        "SPY",  # SPDR S&P 500 ETF Trust
        "QQQ",  # Invesco QQQ Trust
        "TLT",  # iShares 20+ Year Treasury Bond ETF
        "BABA",  # Alibaba Group Holding Limited
        "VZ",  # Verizon Communications Inc.
    ]  # Add the list of stocks you want to monitor
    monitor_stocks(stock_list)
