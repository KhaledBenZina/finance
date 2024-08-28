import yfinance as yf
import time
from datetime import datetime
import os


def send_notification(stock, current_price, prev_close):
    title = "Stock Alert"
    message = f"Stock {stock} is trading near the previous close price: {current_price} (Previous Close: {prev_close})"
    os.system(f'notify-send "{title}" "{message}"')


def check_stock_price(stock):
    try:
        stock_info = yf.Ticker(stock)
        data = stock_info.history(period="2d")
        if len(data) < 2:
            return  # Not enough data to compare

        prev_close = data["Close"].iloc[-2]

        # Fetch 1-minute interval data
        live_data = yf.download(tickers=stock, period="1d", interval="1m")
        if live_data.empty:
            return

        current_price = live_data["Close"].iloc[-1]

        # Check if current price is within +/- $0.5 of previous close
        if abs(current_price - prev_close) / prev_close <= 0.01:
            send_notification(stock, current_price, prev_close)
        else:
            print(f"{stock} is not near PDC")
    except Exception as e:
        print(f"Error checking stock {stock}: {e}")


def main(stocks):
    while True:
        print(f"Checking stocks at {datetime.now()}...")
        for stock in stocks:
            check_stock_price(stock)
        time.sleep(60)  # Check every 60 seconds


if __name__ == "__main__":
    stocks = [
        "AAPL",  # Apple Inc.
        "MSFT",  # Microsoft Corporation
        "AMZN",  # Amazon.com Inc.
        "GOOGL",  # Alphabet Inc. (Class A)
        "GOOG",  # Alphabet Inc. (Class C)
        "FB",  # Meta Platforms Inc.
        "TSLA",  # Tesla Inc.
        "BRK.B",  # Berkshire Hathaway Inc. (Class B)
        "NVDA",  # NVIDIA Corporation
        "JPM",  # JPMorgan Chase & Co.
        "JNJ",  # Johnson & Johnson
        "V",  # Visa Inc.
        "PG",  # Procter & Gamble Co.
        "UNH",  # UnitedHealth Group Incorporated
        "HD",  # The Home Depot Inc.
        "MA",  # Mastercard Incorporated
        "DIS",  # The Walt Disney Company
        "PYPL",  # PayPal Holdings Inc.
        "NFLX",  # Netflix Inc.
        "INTC",  # Intel Corporation
        "VZ",  # Verizon Communications Inc.
        "KO",  # The Coca-Cola Company
        "PFE",  # Pfizer Inc.
        "MRK",  # Merck & Co. Inc.
        "CSCO",  # Cisco Systems Inc.
        "PEP",  # PepsiCo Inc.
        "ABT",  # Abbott Laboratories
        "COST",  # Costco Wholesale Corporation
        "CMCSA",  # Comcast Corporation
        "XOM",  # Exxon Mobil Corporation
        "BAC",  # Bank of America Corporation
        "WMT",  # Walmart Inc.
        "ADBE",  # Adobe Inc.
        "NKE",  # NIKE Inc.
        "T",  # AT&T Inc.
        "CRM",  # Salesforce.com Inc.
        "MCD",  # McDonald's Corporation
        "QCOM",  # Qualcomm Incorporated
        "MDT",  # Medtronic plc
        "LLY",  # Eli Lilly and Company
        "ORCL",  # Oracle Corporation
        "NEE",  # NextEra Energy Inc.
        "UPS",  # United Parcel Service Inc.
        "IBM",  # International Business Machines Corporation
        "TXN",  # Texas Instruments Incorporated
        "HON",  # Honeywell International Inc.
        "CVX",  # Chevron Corporation
        "BA",  # The Boeing Company
        "WFC",  # Wells Fargo & Company
    ]

    main(stocks)
