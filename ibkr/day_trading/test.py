import yfinance as yf
import pandas as pd


def filter_stocks(stocks, min_volume, min_liquidity, min_volatility):
    filtered_stocks = []
    for stock in stocks:
        print(stock)
        volume = yf.Ticker(stock).info.get("averageVolume10days", 0)
        liquidity = stock.info.get("averageDailyVolume10Day", 0)
        volatility = (
            stock.info.get("regularMarketDayLow", 0)
            - stock.info.get("regularMarketDayHigh", 0)
        ) / stock.info.get("regularMarketDayLow", 1)

        if (
            volume >= min_volume
            and liquidity >= min_liquidity
            and volatility >= min_volatility
        ):
            filtered_stocks.append(stock)
    return filtered_stocks


def get_best_day_trading_stocks():
    # btc_data = yf.download('BTC-USD')
    # all_stocks = btc_data.index.tolist()
    df = pd.read_csv(
        filepath_or_buffer="/home/khaled/Downloads/bats_symbols.csv", header=0
    )
    btc_symbols = df.Name.tolist()
    all_tickers = yf.Tickers(" ".join(btc_symbols))
    all_stocks = all_tickers.tickers

    min_volume = 2000000  # Minimum volume threshold
    min_liquidity = 2000000  # Minimum liquidity threshold
    min_volatility = 0.05  # Minimum volatility threshold

    filtered_stocks = filter_stocks(
        all_stocks, min_volume, min_liquidity, min_volatility
    )
    return filtered_stocks


if __name__ == "__main__":
    best_stocks = get_best_day_trading_stocks()
    print("Best stocks for day trading:")
    for stock in best_stocks:
        print(stock)
