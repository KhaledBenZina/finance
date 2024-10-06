import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert

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


def insert_stock_data(ticker, interval, period):
    # Determine the target table based on the interval
    if interval == "1m":
        table_name = "stock_data"
        time_column = "datetime"
        time_format = "Datetime"
    elif interval == "1d":
        table_name = "daily_stock_data"
        time_column = "date"
        time_format = "Date"
    else:
        raise ValueError(
            "Unsupported interval. Use '1m' for minute data or '1d' for daily data."
        )

    # Fetch data using yfinance
    try:
        data = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            threads=True,
        )
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return

    if data.empty:
        print(
            f"No data fetched for {ticker} with interval {interval} and period {period}."
        )
        return

    # Reset index to get the time column
    data.reset_index(inplace=True)

    # Prepare data according to the target table schema
    if interval == "1m":
        data[time_column] = pd.to_datetime(data[time_format])
    elif interval == "1d":
        data[time_column] = pd.to_datetime(data[time_format]).dt.date

    data["ticker"] = ticker
    data.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adjusted_close",
            "Volume": "volume",
        },
        inplace=True,
    )

    # Select relevant columns based on the interval
    if interval == "1m":
        data = data[[time_column, "ticker", "open", "high", "low", "close", "volume"]]
    elif interval == "1d":
        data = data[
            [
                time_column,
                "ticker",
                "open",
                "high",
                "low",
                "close",
                "adjusted_close",
                "volume",
            ]
        ]

    # Drop rows with missing data
    data = data.dropna()

    if data.empty:
        print(
            f"All data for {ticker} with interval {interval} contains NaN values after dropping. No data to insert."
        )
        return

    # Convert DataFrame to list of dictionaries
    data_dict = data.to_dict(orient="records")

    # Set up the database connection
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)

    # Build insert statement with upsert (ON CONFLICT DO NOTHING)
    stmt = pg_insert(table).values(data_dict)

    # Define the primary key columns for conflict resolution
    if interval == "1m":
        pk_columns = ["datetime", "ticker"]
    elif interval == "1d":
        pk_columns = ["date", "ticker"]

    # Perform upsert
    upsert_stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)

    # Execute the statement
    try:
        with engine.connect() as conn:
            conn.execute(upsert_stmt)
            conn.commit()
        print(
            f"Data for {ticker} with interval {interval} inserted into {table_name} successfully."
        )
    except Exception as e:
        print(f"Error inserting data for {ticker}: {e}")




if __name__ == "__main__":
    # List of tickers to process
    tickers = ["AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA"]

    # Periods for data fetching
    minute_data_period = "7d"  # For minute-level data
    daily_data_period = "1y"  # For daily data

    # Loop over each ticker
    for ticker in tickers:
        # Insert 1-minute data
        try:
            insert_stock_data(ticker, "1m", minute_data_period)
        except Exception as e:
            print(f"Error inserting minute data for {ticker}: {e}")

        # Insert daily data
        try:
            insert_stock_data(ticker, "1d", daily_data_period)
        except Exception as e:
            print(f"Error inserting daily data for {ticker}: {e}")

