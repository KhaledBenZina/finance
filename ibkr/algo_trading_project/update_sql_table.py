import yfinance as yf
import psycopg2
from psycopg2 import sql
from datetime import datetime

# Define your PostgreSQL database connection parameters
db_params = {
    "database": "financial_markets",
    "user": "yourusername",
    "password": "yourpassword",
    "host": "localhost",
    "port": "5432",
}

# Ticker symbol for the stock (e.g., Amazon)
symbol = "AMZN"

# Connect to the PostgreSQL database
conn = psycopg2.connect(**db_params)
cur = conn.cursor()


# Define a function to insert or update stock price data
def insert_or_update_stock_data(symbol, date, open_price, high, low, close, volume):
    query = sql.SQL(
        """
        INSERT INTO stock_prices (symbol, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    )
    cur.execute(query, (symbol, date, open_price, high, low, close, volume))
    conn.commit()


# Fetch historical stock price data using yfinance
start_date = "2022-01-01"
end_date = "2021-12-31"
stock_data = yf.download(symbol, start=start_date, end=end_date, interval="1h")

# Iterate through the stock data and update the PostgreSQL table
for index, row in stock_data.iterrows():
    date = index
    open_price = row["Open"]
    high = row["High"]
    low = row["Low"]
    close = row["Close"]
    volume = row["Volume"]

    insert_or_update_stock_data(symbol, date, open_price, high, low, close, volume)
    print(f"Updated {symbol} data for {date}")

# Close the database connection
cur.close()
conn.close()
