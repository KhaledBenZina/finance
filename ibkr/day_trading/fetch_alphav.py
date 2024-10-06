import requests
import pandas as pd
import time
from sqlalchemy import create_engine
import datetime


# Get the current month and year to determine the correct slice
def get_latest_slice():
    now = datetime.datetime.now()
    year = 1
    month = now.month
    slice_str = f"year{year}month{month}"
    return slice_str


def fetch_alpha_vantage_intraday(ticker, interval, slice, api_key):
    """
    Fetch intraday extended data from Alpha Vantage.
    """
    base_url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_INTRADAY_EXTENDED",
        "symbol": ticker,
        "interval": interval,
        "slice": slice,
        "apikey": api_key,
        "adjusted": "false",
        "datatype": "csv",
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        if "Note" in response.text:
            print("API call frequency limit reached. Waiting for 60 seconds.")
            time.sleep(60)
            response = requests.get(base_url, params=params)
            response.raise_for_status()
        data = pd.read_csv(pd.compat.StringIO(response.text))
        return data
    except Exception as e:
        print(f"Error fetching data for {ticker}, slice {slice}: {e}")
        return pd.DataFrame()


# Database connection details
db_name = "stockdata"
db_user = "khaled"
db_password = "Arsenal4th-"  # Replace with your actual password
db_host = "localhost"
db_port = "5432"

# Create a connection engine
engine = create_engine(
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
)


def insert_alpha_vantage_data(ticker, api_key):
    interval = "1min"
    slice = get_latest_slice()

    # Fetch data
    data = fetch_alpha_vantage_intraday(ticker, interval, slice, api_key)

    if data.empty:
        print(f"No data fetched for {ticker}.")
        return

    # Prepare data
    data.rename(
        columns={
            "time": "datetime",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        },
        inplace=True,
    )

    data["datetime"] = pd.to_datetime(data["datetime"])
    data["ticker"] = ticker

    # Reorder columns to match your database schema
    data = data[["datetime", "ticker", "open", "high", "low", "close", "volume"]]

    # Drop duplicates and NaN values
    data = data.dropna()
    data.drop_duplicates(subset=["datetime", "ticker"], inplace=True)

    # Insert data into the database
    try:
        data.to_sql(
            "stock_data", engine, if_exists="append", index=False, method="multi"
        )
        print(f"Data for {ticker} inserted successfully.")
    except Exception as e:
        print(f"Error inserting data for {ticker}: {e}")


if __name__ == "__main__":
    # Your Alpha Vantage API Key
    API_KEY = "ZHZHSTUIU98FIX43"  # Replace with your actual API key

    # List of tickers
    tickers = ["AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA"]

    for ticker in tickers:
        insert_alpha_vantage_data(ticker, API_KEY)
        time.sleep(12)  # Respect the rate limit of 5 requests per minute
