import pandas as pd
from sqlalchemy import create_engine
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

# PostgreSQL connection
POSTGRES_URI = "postgresql+psycopg2://khaled:Arsenal4th-@localhost:5432/stockdata"
engine = create_engine(POSTGRES_URI)

# Snowflake connection parameters (replace with your credentials)
SNOWFLAKE_USER = "khaled"
SNOWFLAKE_PASSWORD = "Arsenal4th1886"
SNOWFLAKE_ACCOUNT = "FFAJGHR-RRB95344"
SNOWFLAKE_DATABASE = "FINANCE"
SNOWFLAKE_SCHEMA = "PUBLIC"
SNOWFLAKE_WAREHOUSE = "COMPUTE_WH"
SNOWFLAKE_TABLE = "STOCK_DATA"

# Fetch data from PostgreSQL
df = pd.read_sql_table("stock_data", engine)
df.columns = map(str.upper, df.columns)
print(f"Fetched {len(df)} rows from PostgreSQL.")

# Connect to Snowflake
ctx = snowflake.connector.connect(
    user=SNOWFLAKE_USER,
    password=SNOWFLAKE_PASSWORD,
    account=SNOWFLAKE_ACCOUNT,
    warehouse=SNOWFLAKE_WAREHOUSE,
    database=SNOWFLAKE_DATABASE,
    schema=SNOWFLAKE_SCHEMA,
)


# Write data to Snowflake with use_logical_type=True to handle timezone-aware datetimes
success, nchunks, nrows, _ = write_pandas(
    ctx, df, SNOWFLAKE_TABLE, use_logical_type=True
)
if success:
    print(f"Successfully pushed {nrows} rows to Snowflake table '{SNOWFLAKE_TABLE}'.")
else:
    print("Failed to push data to Snowflake.")

ctx.close()
