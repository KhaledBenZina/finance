from ib_insync import IB, Stock, util
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
import pandas as pd
import datetime


def fetch_and_store_yesterday(ticker):
    ib = IB()
    ib.connect("127.0.0.1", 7497, clientId=2)
    contract = Stock(ticker, "SMART", "USD")

    # Calculate yesterday's date
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = yesterday.replace(hour=23, minute=59, second=59, microsecond=0)

    # IBKR expects endDateTime in format 'YYYYMMDD HH:MM:SS'
    endDateTime = end.strftime("%Y%m%d %H:%M:%S")

    bars = ib.reqHistoricalData(
        contract,
        endDateTime=endDateTime,
        durationStr="1 D",
        barSizeSetting="1 min",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=False,
    )
    if not bars:
        print(f"No data for {ticker} on {yesterday.date()}")
        ib.disconnect()
        return

    df = util.df(bars)
    df["ticker"] = ticker
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
    df.drop_duplicates(subset=["datetime", "ticker"], inplace=True)

    # Database connection details
    db_name = "stockdata"
    db_user = "khaled"
    db_password = "Arsenal4th-"
    db_host = "localhost"
    db_port = "5432"
    engine = create_engine(
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    metadata = MetaData()
    stock_data_table = Table("stock_data", metadata, autoload_with=engine)
    data_dict = df.to_dict(orient="records")
    stmt = pg_insert(stock_data_table).values(data_dict)
    pk_columns = ["datetime", "ticker"]
    upsert_stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)
    with engine.begin() as conn:
        conn.execute(upsert_stmt)
    print(f"Inserted {len(df)} rows for {ticker} on {yesterday.date()}")
    ib.disconnect()


if __name__ == "__main__":
    tickers = [
        "SPY",
        "QQQ",
        "IWM",
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOGL",
        "TSLA",
        "NVDA",
        "AMD",
        "META",
        "JPM",
        "BAC",
        "GS",
        "XOM",
        "CVX",
        "PFE",
        "JNJ",
        "MRNA",
        "CAT",
        "BA",
        "GE",
        "WMT",
        "HD",
        "DIS",
        "PLTR",
        "NIO",
        "SNAP",
        "CCL",
        "AAL",
        "RGTI",
        "QUBT",
        "QBTS",
    ]
    for ticker in tickers:
        fetch_and_store_yesterday(ticker)
