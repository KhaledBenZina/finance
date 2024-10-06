import requests
import pandas as pd
import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    MetaData,
    Table,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import nltk
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Define date range
to_date = datetime.datetime(year=2024, month=9, day=5)
from_date = datetime.datetime(year=2024, month=9, day=28)
nltk.download("vader_lexicon")
analyzer = SentimentIntensityAnalyzer()

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
    "KO",
    "INTC",
]

tickers = ["NVDA", "TSLA"]


def fetch_news_articles(symbol, from_date, to_date, api_key):
    url = "https://newsapi.org/v2/everything"
    query = f'"{symbol}" AND (stocks OR shares OR market)'
    params = {
        "q": query,
        "from": from_date,
        "to": to_date,
        "language": "en",
        "sortBy": "publishedAt",
        "apiKey": api_key,
        "pageSize": 100,
    }
    response = requests.get(url, params=params)
    data = response.json()
    if data.get("status") != "ok":
        print(f"Error fetching news for {symbol}: {data.get('message')}")
        return []
    articles = data.get("articles", [])
    for article in articles:
        article["symbol"] = symbol
    return articles


def compute_sentiment(text):
    if not text:
        return 0
    score = analyzer.polarity_scores(text)
    return score["compound"]  # Range from -1 (negative) to 1 (positive)


NEWS_API_KEY = "d243aae7a4c348b58f8df18be92a6c77"  # Replace with your actual API key


# Format dates
to_date_str = to_date.strftime("%Y-%m-%dT%H:%M:%SZ")
from_date_str = from_date.strftime("%Y-%m-%dT%H:%M:%SZ")

all_articles = []

for symbol in tickers:
    print(f"Fetching news for {symbol}")
    articles = fetch_news_articles(symbol, from_date_str, to_date_str, NEWS_API_KEY)
    all_articles.extend(articles)


news_df = pd.DataFrame(all_articles)

# Keep only necessary columns
news_df = news_df[["publishedAt", "symbol", "title", "description", "content", "url"]]


# Convert 'publishedAt' to datetime
news_df["publishedAt"] = pd.to_datetime(news_df["publishedAt"])

# Remove duplicates based on URL
news_df.drop_duplicates(subset=["url"], inplace=True)

# Combine title and description for sentiment analysis
news_df["text"] = news_df["title"].fillna("") + " " + news_df["description"].fillna("")

# Compute sentiment score
news_df["sentiment"] = news_df["text"].apply(compute_sentiment)


# # %%
Base = declarative_base()


class NewsArticle(Base):
    __tablename__ = "news_articles"
    id = Column(Integer, primary_key=True)
    published_at = Column(DateTime)
    symbol = Column(String(10))
    title = Column(Text)
    description = Column(Text)
    content = Column(Text)
    url = Column(Text, unique=True)
    sentiment = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.now)


# # %%
# Base.metadata.create_all(engine)

# %%
Session = sessionmaker(bind=engine)
session = Session()


# %%
from sqlalchemy.exc import IntegrityError

for index, row in news_df.iterrows():
    article = NewsArticle(
        published_at=row["publishedAt"],
        symbol=row["symbol"],
        title=row["title"],
        description=row["description"],
        content=row["content"],
        url=row["url"],
        sentiment=row["sentiment"],
    )
    try:
        session.add(article)
        session.commit()
        print(f"Inserted article: {row['title']}")
    except IntegrityError:
        session.rollback()
        print(f"Duplicate article found, skipping: {row['url']}")
    except Exception as e:
        session.rollback()
        print(f"Error inserting article: {e}")


# %%
