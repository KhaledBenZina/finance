import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import pytz

# PostgreSQL database connection parameters
DATABASE_URI = "postgresql+psycopg2://khaled:Arsenal4th-@localhost:5432/stockdata"

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URI)
new_york_tz = pytz.timezone("America/New_York")


def fetch_and_store_data(tickers):
    """Fetches live 1-minute data for a list of tickers and stores it in the PostgreSQL database."""

    for ticker in tickers:
        table_name = f"{ticker.replace('.', '_')}"

        # Get current time in New York
        now = datetime.now()

        # Calculate yesterday's date
        yesterday = now - timedelta(days=1)

        # Set the market open and close times
        market_open_time = datetime(
            yesterday.year, yesterday.month, yesterday.day, 9, 30
        )
        market_close_time = datetime(
            yesterday.year, yesterday.month, yesterday.day, 16, 0
        )

        try:
            # Fetch live data
            df = yf.download(
                ticker,
                start=market_open_time,
                end=market_close_time,
                interval="1m",
            )

            if df.empty:
                print(f"No data fetched for {ticker}")
                continue

            # Add a column for the ticker
            df["Ticker"] = ticker
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            print(df)
            # Store data in PostgreSQL
            df.to_sql(table_name, engine, if_exists="append", index=True)

            print(f"Data for {ticker} stored successfully")

        except Exception as e:
            print(f"Error occurred for {ticker}: {e}")


# List of tickers
tickers = [
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

fetch_and_store_data(tickers)
