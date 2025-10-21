import pandas as pd
import datetime
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import MetaData, Table
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from ib_insync import IB, Stock, util
from fetch_ibkr import TICKERS


# PostgreSQL connection
POSTGRES_URI = "postgresql+psycopg2://khaled:Arsenal4th-@localhost:5432/stockdata"
engine = create_engine(POSTGRES_URI)

# Snowflake connection parameters
SNOWFLAKE_USER = "khaled"
SNOWFLAKE_PASSWORD = "Arsenal4th1886"
SNOWFLAKE_ACCOUNT = "FFAJGHR-RRB95344"
SNOWFLAKE_DATABASE = "FINANCE"
SNOWFLAKE_SCHEMA = "PUBLIC"
SNOWFLAKE_WAREHOUSE = "COMPUTE_WH"
SNOWFLAKE_TABLE = "STOCK_DATA"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


def get_postgres_max_dt_per_ticker() -> dict:
    logger.info("Fetching latest datetimes per ticker from Postgres")
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT ticker, MAX(datetime) AS max_dt
                FROM stock_data
                GROUP BY ticker
                """
            )
        )
        rows = result.fetchall()
        logger.info("Retrieved max datetimes for %d tickers from Postgres", len(rows))
        return {row.ticker: row.max_dt for row in rows}


def upsert_postgres(df: pd.DataFrame) -> int:
    if df.empty:
        logger.info("No new rows to upsert into Postgres")
        return 0
    metadata = MetaData()
    stock_data_table = Table("stock_data", metadata, autoload_with=engine)
    data_dict = df.to_dict(orient="records")
    stmt = pg_insert(stock_data_table).values(data_dict)
    pk_columns = ["datetime", "ticker"]
    upsert_stmt = stmt.on_conflict_do_nothing(index_elements=pk_columns)
    with engine.begin() as conn:
        conn.execute(upsert_stmt)
    logger.info("Upserted %d rows into Postgres (duplicates ignored)", len(df))
    return len(df)


def fetch_missing_from_ibkr(
    ib: IB, ticker: str, start_dt: datetime.datetime
) -> pd.DataFrame:
    # Normalize start time and now to UTC-aware pandas Timestamps
    start_ts = pd.Timestamp(start_dt)
    if start_ts.tzinfo is None or start_ts.tz is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")
    now_ts = pd.Timestamp.now(tz="UTC")

    logger.info(
        "Fetching missing data from IBKR for %s starting after %s", ticker, start_ts
    )
    contract = Stock(ticker, "SMART", "USD")

    # IBKR allows up to 1 month of 1-min bars per request. We'll step monthly.
    collected = []
    cursor_ts = start_ts
    while cursor_ts < now_ts:
        end_ts = min(cursor_ts + pd.DateOffset(months=1), now_ts)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_ts.tz_convert("UTC").strftime("%Y%m%d %H:%M:%S"),
            durationStr="1 M",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
            keepUpToDate=False,
        )
        if bars:
            df = util.df(bars)
            df.rename(columns={"date": "datetime"}, inplace=True)
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
            # Filter strictly after start_dt to avoid duplicates
            df = df[df["datetime"] > start_ts]
            df["ticker"] = ticker
            df = df[["datetime", "ticker", "open", "high", "low", "close", "volume"]]
            df.drop_duplicates(subset=["datetime", "ticker"], inplace=True)
            collected.append(df)
            logger.info(
                "Fetched %d rows for %s in window ending %s", len(df), ticker, end_ts
            )
        # advance
        cursor_ts = end_ts + pd.Timedelta(minutes=1)

    if not collected:
        logger.info("No new data returned from IBKR for %s", ticker)
        return pd.DataFrame(
            columns=["datetime", "ticker", "open", "high", "low", "close", "volume"]
        )
    return pd.concat(collected, ignore_index=True)


def get_snowflake_max_dt_per_ticker(ctx) -> dict:
    sql = f"SELECT TICKER, MAX(DATETIME) AS MAX_DT FROM {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE} GROUP BY TICKER"
    try:
        logger.info("Fetching latest datetimes per ticker from Snowflake")
        cur = ctx.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        logger.info("Retrieved max datetimes for %d tickers from Snowflake", len(rows))
        return {row[0]: row[1] for row in rows}
    except snowflake.connector.errors.ProgrammingError:
        # Table might not exist yet
        logger.warning(
            "Snowflake table %s not found or query failed; assuming empty",
            SNOWFLAKE_TABLE,
        )
        return {}
    finally:
        try:
            cur.close()
        except Exception:
            pass


def push_incremental_to_snowflake(ctx, df: pd.DataFrame) -> int:
    if df.empty:
        logger.info("No new rows to push to Snowflake")
        return 0
    # Snowflake expects uppercase columns for consistency with prior design
    df_to_push = df.copy()
    df_to_push.columns = [c.upper() for c in df_to_push.columns]
    success, nchunks, nrows, _ = write_pandas(
        ctx, df_to_push, SNOWFLAKE_TABLE, use_logical_type=True
    )
    if not success:
        logger.error("write_pandas reported failure when pushing to Snowflake")
        raise RuntimeError("Failed to push data to Snowflake")
    logger.info("Pushed %d rows to Snowflake in %d chunks", nrows, nchunks)
    return nrows


def main():
    logger.info("Starting incremental backfill and Snowflake sync")
    # Step 1: Read latest timestamps from Postgres
    pg_max_by_ticker = get_postgres_max_dt_per_ticker()

    # Step 2: Connect IBKR
    ib = IB()
    ib.disconnect()
    time_sleep_seconds = 5
    import time

    logger.info("Connecting to IBKR TWS in %d seconds...", time_sleep_seconds)
    time.sleep(time_sleep_seconds)
    ib.connect("127.0.0.1", 7497, clientId=42)
    logger.info("Connected to IBKR")

    # Step 3: For each ticker, fetch missing data and upsert into Postgres
    total_new_rows_pg = 0
    for ticker in TICKERS:
        start_dt = pg_max_by_ticker.get(ticker)
        if start_dt is None:
            # Default to last 1 month if nothing exists yet
            start_dt = (
                pd.Timestamp.now(tz="UTC") - pd.DateOffset(months=1)
            ).to_pydatetime()
        missing_df = fetch_missing_from_ibkr(ib, ticker, start_dt)
        inserted = upsert_postgres(missing_df)
        total_new_rows_pg += inserted
        logger.info("%s: inserted %d new rows into Postgres", ticker, inserted)

    ib.disconnect()
    logger.info("Disconnected from IBKR")

    # Recompute Postgres max after backfill
    pg_max_by_ticker = get_postgres_max_dt_per_ticker()

    # Step 4: Connect to Snowflake and compare
    logger.info("Connecting to Snowflake")
    ctx = snowflake.connector.connect(
        user=SNOWFLAKE_USER,
        password=SNOWFLAKE_PASSWORD,
        account=SNOWFLAKE_ACCOUNT,
        warehouse=SNOWFLAKE_WAREHOUSE,
        database=SNOWFLAKE_DATABASE,
        schema=SNOWFLAKE_SCHEMA,
    )
    logger.info("Connected to Snowflake")

    sf_max_by_ticker = get_snowflake_max_dt_per_ticker(ctx)

    # Step 5: For each ticker, decide push or error
    total_pushed = 0
    with engine.connect() as conn:
        for ticker in TICKERS:
            pg_max = pg_max_by_ticker.get(ticker)
            sf_max = sf_max_by_ticker.get(ticker)

            if pg_max is None:
                # Nothing in Postgres; nothing to push
                continue

            if sf_max is not None and sf_max > pg_max:
                logger.error(
                    "Snowflake ahead of Postgres for %s: SF=%s PG=%s",
                    ticker,
                    sf_max,
                    pg_max,
                )
                ctx.close()
                raise RuntimeError(
                    f"Snowflake has newer data than Postgres for {ticker}: SF={sf_max}, PG={pg_max}"
                )

            # Fetch only new rows beyond Snowflake's max
            if sf_max is None:
                sql = text(
                    "SELECT datetime, ticker, open, high, low, close, volume FROM stock_data WHERE ticker = :t"
                )
                logger.info(
                    "%s: pushing full history to Snowflake (no existing rows)", ticker
                )
                df = pd.read_sql(sql, conn, params={"t": ticker})
            elif sf_max < pg_max:
                sql = text(
                    "SELECT datetime, ticker, open, high, low, close, volume FROM stock_data WHERE ticker = :t AND datetime > :sfmax"
                )
                logger.info(
                    "%s: pushing rows newer than %s to Snowflake", ticker, sf_max
                )
                df = pd.read_sql(sql, conn, params={"t": ticker, "sfmax": sf_max})
            else:
                # sf_max == pg_max: already in sync for this ticker
                logger.info(
                    "%s: already in sync between Postgres and Snowflake", ticker
                )
                continue

            pushed = push_incremental_to_snowflake(ctx, df)
            total_pushed += pushed
            logger.info("%s: pushed %d new rows to Snowflake", ticker, pushed)

    ctx.close()
    logger.info(
        "Backfill complete. Inserted %d new rows into Postgres and pushed %d rows to Snowflake.",
        total_new_rows_pg,
        total_pushed,
    )


if __name__ == "__main__":
    main()
