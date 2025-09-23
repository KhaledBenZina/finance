from ib_insync import IB, Stock, util
import time


def fetch_and_store_data(ticker, duration="2 M", bar_size="1 min"):
    contract = Stock(ticker, "SMART", "USD")

    # Request historical data
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="20250422 00:00:00",
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


def fetch_and_store_data_improved(ticker, months_back=12, bar_size="1 min"):
    import pandas as pd
    from sqlalchemy import create_engine, MetaData, Table
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import datetime

    """
    Fetch intraday historical data from IBKR in chunks and store in PostgreSQL.
    
    Args:
        ticker (str): Stock symbol (e.g., "AAPL")
        months_back (int): How many months of history to fetch
        bar_size (str): Bar size (default "1 min")
    """

    # Define contract
    print(f"Starting data fetch for {ticker}")
    contract = Stock(ticker, "SMART", "USD")
    end = datetime.datetime.now()

    # Database connection details
    db_name = "stockdata"
    db_user = "khaled"
    db_password = "Arsenal4th-"
    db_host = "localhost"
    db_port = "5432"

    engine = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    # Load table metadata
    metadata = MetaData()
    stock_data_table = Table("stock_data", metadata, autoload_with=engine)

    total_inserted = 0

    # Loop month by month
    for i in range(months_back):
        end_date = (end - pd.DateOffset(months=i)).strftime("%Y%m%d %H:%M:%S")
        print(f"Fetching {ticker} - Month {i+1}/{months_back}, end={end_date}")

        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date,
            durationStr="1 M",  # IBKR limit for 1-min bars
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,  # Only regular trading hours
            formatDate=1,
            keepUpToDate=False,
        )

        if not bars:
            print(f"No data returned for {ticker} (month {i+1})")
            continue

        df = util.df(bars)
        df["ticker"] = ticker

        # Standardize schema
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
        df = df[["datetime", "ticker", "open", "high", "low", "close", "volume"]]

        # Drop duplicates inside each chunk
        df.drop_duplicates(subset=["datetime", "ticker"], inplace=True)

        if df.empty:
            continue

        # Convert DataFrame to list of dictionaries
        data_dict = df.to_dict(orient="records")

        # Insert with upsert (ignore duplicates)
        stmt = pg_insert(stock_data_table).values(data_dict)
        pk_columns = ["datetime", "ticker"]
        upsert_stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)

        with engine.begin() as conn:
            conn.execute(upsert_stmt)

        print(f"Inserted {len(df)} rows for {ticker} (month {i+1}) into PostgreSQL.")
        total_inserted += len(df)

    if total_inserted == 0:
        print(f"No data collected for {ticker}")
    else:
        print(f"Inserted {total_inserted} rows for {ticker} into PostgreSQL.")


if __name__ == "__main__":
    # List of tickers
    # tickers = ["AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "NVDA"]
    tickers = [
        # ETFs (benchmarks, huge liquidity)
        "SPY",
        "QQQ",
        "IWM",
        # Mega-cap tech
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOGL",
        "TSLA",
        "NVDA",
        "AMD",
        "META",
        # Financials
        "JPM",
        "BAC",
        "GS",
        # Energy
        "XOM",
        "CVX",
        # Healthcare
        "PFE",
        "JNJ",
        "MRNA",
        # Industrials
        "CAT",
        "BA",
        "GE",
        # Consumer & retail
        "WMT",
        "HD",
        "DIS",
        # Volatile mid/small-cap plays
        "PLTR",
        "NIO",
        "SNAP",
        "CCL",
        "AAL",
        # Speculative/AI/quantum (keep for fun)
        "RGTI",
        "QUBT",
        "QBTS",
    ]

    # Connect to IBKR
    ib = IB()
    ib.disconnect()
    time.sleep(10)
    ib.connect("127.0.0.1", 7497, clientId=1)

    # Fetch and store data for each ticker
    for ticker in tickers:
        fetch_and_store_data_improved(ticker)

    # Disconnect from IBKR
    ib.disconnect()
