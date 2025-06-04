from ib_insync import IB, Stock, util
import time


def fetch_and_store_data(ticker, duration="2 M", bar_size="1 min"):
    contract = Stock(ticker, "SMART", "USD")

    # Request historical data
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="20250222 00:00:00",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=False,
    )
    # Convert to DataFrame
    df = util.df(bars)
    print(ticker + ": " + duration + " data")
    print(df)
    # Add the ticker symbol
    df["ticker"] = ticker

    # Rename columns to match your database schema
    df.rename(
        columns={
            "date": "datetime",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        },
        inplace=True,
    )

    # Select relevant columns
    df = df[["datetime", "ticker", "open", "high", "low", "close", "volume"]]

    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import MetaData, Table

    # Database connection details
    db_name = "stockdata"
    db_user = "khaled"
    db_password = "Arsenal4th-"
    db_host = "localhost"
    db_port = "5432"

    # Create a connection engine
    engine = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    # Drop duplicates
    df.drop_duplicates(subset=["datetime", "ticker"], inplace=True)

    # Convert DataFrame to list of dictionaries
    data_dict = df.to_dict(orient="records")

    # Set up the database table
    metadata = MetaData()
    stock_data_table = Table("stock_data", metadata, autoload_with=engine)

    # Build insert statement with upsert
    stmt = pg_insert(stock_data_table).values(data_dict)
    pk_columns = ["datetime", "ticker"]

    upsert_stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)

    # Execute the statement
    with engine.connect() as conn:
        conn.execute(upsert_stmt)
        conn.commit()

    print(f"Data for {ticker} inserted successfully.")


if __name__ == "__main__":
    # List of tickers
    # tickers = ["AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA"]
    tickers = [
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOGL",
        "TSLA",
        "NVDA",
        "AMD",
        "BAC",
        "F",
        "GE",
        "T",
        "CCL",
        "AAL",
        "NIO",
        "PLTR",
        "MU",
        "SNAP",
        "XOM",
        "PFE",
        "INTC",
        "RGTI",
        "QUBT",
        "QBTS",
    ]
    # Connect to IBKR
    ib = IB()
    ib.disconnect()
    ib.connect("127.0.0.1", 7497, clientId=1)

    # Fetch and store data for each ticker
    for ticker in tickers:
        fetch_and_store_data(ticker)
        # Be mindful of pacing limits
        time.sleep(10)  # Adjust sleep time as necessary

    # Disconnect from IBKR
    ib.disconnect()
