# IMPORTING PACKAGES
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import yfinance as yf
from matplotlib.dates import MonthLocator, DateFormatter, YearLocator


class StockAnalyzer:
    def __init__(self, stock: str) -> None:
        self.stock = stock

    def plot_price_20_500_avg(self):
        plt.style.use("fivethirtyeight")
        plt.rcParams["figure.figsize"] = (20, 10)

    # EXTRACTING STOCK DATA

    # def get_historical_data(self, symbol, start_date, period):
    #     api_key = "91b69afa6c474612a50e9e707efdd54b"
    #     api_url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={period}&outputsize=5000&apikey={api_key}"
    #     try:
    #         raw_df = requests.get(api_url).json()
    #         df = (
    #             pd.DataFrame(raw_df["values"])
    #             .iloc[::-1]
    #             .set_index("datetime")
    #             .astype(float)
    #         )
    #         df = df[df.index >= start_date]
    #         df.index = pd.to_datetime(df.index)
    #         df = df.iloc[-1200:]
    #         return df
    #     except Exception as e:
    #         return pd.DataFrame.empty

    def get_historical_yf(self, start, end=None, interval="1d"):
        return yf.download(
            tickers=self.stock,
            interval=interval,
            start=start,
            end=end,
            progress=False,
        )

    def plot_moving_averages(
        self,
        start_date,
        sma_period,
        lma_period,
        end_date=None,
    ):
        # df = self.get_historical_data(self.stock, start_date, period)
        df = self.get_historical_yf(start=start_date, end=end_date)
        # 20 days to represent the 22 trading days in a month
        df["Close"] = df["Adj Close"]
        df["SMA"] = df["Close"].rolling(sma_period).mean()
        df["LMA"] = df["Close"].rolling(lma_period).mean()
        # df["50d"] = df["Close"].rolling(20).mean()
        # df["200d"] = df["Close"].rolling(250).mean()
        df["UpperBand"] = df["SMA"] + (2 * df["SMA"].std())
        df["LowerBand"] = df["SMA"] - (2 * df["SMA"].std())

        ax = df[["Close", "SMA", "LMA", "UpperBand", "LowerBand"]].plot(figsize=(20, 8))
        ax.xaxis.set_major_locator(YearLocator())
        ax.xaxis.set_minor_locator(MonthLocator())
        ax.xaxis.set_major_formatter(DateFormatter("%Y"))
        ax.xaxis.set_minor_formatter(DateFormatter("%m"))
        plt.grid(visible=True, axis="x", which="both")
        plt.grid(True)
        plt.title(self.stock + " Moving Averages")
        plt.axis("tight")
        plt.ylabel("Price")
        return None

    def check_last_days_diff_sma_lma(self, start_date, last_date):
        # df = self.get_historical_data(self.stock, "2018-01-01", "1day")
        df = self.get_historical_yf("2018-01-01")
        # try:
        df["SMA"] = df["Close"].rolling(20).mean()
        df["LMA"] = df["Close"].rolling(250).mean()
        df["SMA2"] = df["Close"].rolling(50).mean()
        df["LMA2"] = df["Close"].rolling(200).mean()
        df["Buy"] = df.apply(
            lambda x: 1 if x["SMA"] > x["LMA"] and x["SMA2"] < x["LMA2"] else 0,
            axis=1,
        )
        df["Sell"] = df.apply(
            lambda y: -1 if y["SMA"] < y["LMA"] and y["SMA2"] > y["LMA2"] else 0,
            axis=1,
        )
        signals = df[(df["Buy"] == 1) | (df["Sell"] == 1)]
        # print(signals.tail(5))
        if not signals.empty:
            last = signals.tail(1).index.item()
            if last.date() >= start_date and last.date() <= last_date:
                dc = {
                    "symbol": self.stock,
                    "Buy": signals.loc[last, "Buy"],
                    "Sell": signals.loc[last, "Sell"],
                    "date": last.strftime("%y-%m-%d"),
                }
                return (True, dc)
            else:
                return (False, None)
        # except Exception as e:
        #     print(e)
        #     return None

    def get_all_twelve_data_stocks():
        api_key = "91b69afa6c474612a50e9e707efdd54b"
        api_url = f"https://api.twelvedata.com/stocks?apikey={api_key}"
        print(requests.get(api_url).json())


if __name__ == "__main__":
    df = StockAnalyzer("AAPL").get_historical_yf()
    # api_key = "91b69afa6c474612a50e9e707efdd54b"
    # api_url = f"https://api.twelvedata.com/stocks?apikey={api_key}"
    # stocks = requests.get(api_url).json()["data"]
