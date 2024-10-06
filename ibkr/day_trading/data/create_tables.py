import psycopg2
from sqlalchemy import create_engine, text

# PostgreSQL database connection parameters
DATABASE_URI = "postgresql+psycopg2://khaled:Arsenal4th-@localhost:5432/stockdata"

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URI)


def create_table_for_tickers(tickers):
    """Create a table for each ticker in the PostgreSQL database."""

    # Connect to PostgreSQL
    conn = engine.connect()
    # cur = conn.cursor()

    for ticker in tickers:
        table_name = f"{ticker.replace('.', '_')}"

        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name.upper()} (
            DateTime TIMESTAMP WITHOUT TIMEZONE PRIMARY KEY,
            Open FLOAT,
            High FLOAT,
            Low FLOAT,
            Close FLOAT,
            Volume INTEGER
        );
        """
        conn.execute(text(create_table_sql))

    # Commit changes and close the connection
    conn.commit()
    conn.close()

    print("Tables created successfully")


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

create_table_for_tickers(tickers)
