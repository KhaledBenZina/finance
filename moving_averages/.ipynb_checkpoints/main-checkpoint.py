# IMPORTING PACKAGES
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
from math import floor
from termcolor import colored as cl
from datetime import datetime, timedelta, date
import yfinance as yf
from matplotlib.dates import MonthLocator, DateFormatter, YearLocator


class StockAnalyzer:
    def __init__(self, stock: str) -> None:
        self.stock = stock

    def plot_price_20_500_avg(self):
        plt.style.use("fivethirtyeight")
        plt.rcParams["figure.figsize"] = (20, 10)

    # EXTRACTING STOCK DATA

    def get_historical_data(self, symbol, start_date, period):
        api_key = "91b69afa6c474612a50e9e707efdd54b"
        api_url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={period}&outputsize=5000&apikey={api_key}"
        try:
            raw_df = requests.get(api_url).json()
            df = (
                pd.DataFrame(raw_df["values"])
                .iloc[::-1]
                .set_index("datetime")
                .astype(float)
            )
            df = df[df.index >= start_date]
            df.index = pd.to_datetime(df.index)
            df = df.iloc[-1200:]
            print(df)
            return df
        except Exception as e:
            return pd.DataFrame.empty

    def get_historical_yf(self, start):
        return yf.download(tickers=self.stock, interval="1d", start=start)

    def plot_moving_averages(self, start_date, period):
        # df = self.get_historical_data(self.stock, start_date, period)
        df = self.get_historical_yf(start_date)
        print(df.head())
        # 20 days to represent the 22 trading days in a month
        df["20d"] = df["Close"].rolling(20).mean()
        df["250d"] = df["Close"].rolling(250).mean()
        df["50d"] = df["Close"].rolling(20).mean()
        df["200d"] = df["Close"].rolling(250).mean()
        ax = df[["Close", "20d", "250d"]].plot(figsize=(20, 8))
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
                print(dc)
                # if signals.loc[last, "Sell"] == 1:
                #     print(self.stock + "-->SELL")
                # elif signals.loc[last, "Buy"] == 1:
                #     print(self.stock + "-->BUY")
                return True
            else:
                return False
        # except Exception as e:
        #     print(e)
        #     return None

    def get_all_twelve_data_stocks():
        api_key = "91b69afa6c474612a50e9e707efdd54b"
        api_url = f"https://api.twelvedata.com/stocks?apikey={api_key}"
        print(requests.get(api_url).json())


if __name__ == "__main__":
    # api_key = "91b69afa6c474612a50e9e707efdd54b"
    # api_url = f"https://api.twelvedata.com/stocks?apikey={api_key}"
    # stocks = requests.get(api_url).json()["data"]
    import bs4 as bs
    import requests

    resp = requests.get("http://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    soup = bs.BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"class": "wikitable sortable"})
    tickers = []

    for row in table.findAll("tr")[1:]:
        ticker = row.findAll("td")[0].text
        tickers.append(ticker)
    tickers = [s.replace("\n", "") for s in tickers]
    for ticker in tickers:
        # ticker = element["symbol"]
        try:
            StockAnalyzer(stock=ticker).check_last_days_diff_sma_lma(
                date(2023, 9, 20), date(2023, 9, 22)
            )
            # print("interesting ticker: " + ticker)
        except Exception:
            continue
