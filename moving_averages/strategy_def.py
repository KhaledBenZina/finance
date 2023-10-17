import bs4 as bs
import requests
import pandas as pd
from main import StockAnalyzer
from datetime import date

resp = requests.get("http://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
soup = bs.BeautifulSoup(resp.text, "lxml")
table = soup.find("table", {"class": "wikitable sortable"})
tickers = []

for row in table.findAll("tr")[1:]:
    ticker = row.findAll("td")[0].text
    tickers.append(ticker)
tickers = [s.replace("\n", "") for s in tickers]
ls = []
for ticker in tickers:
    # ticker = element["symbol"]
    try:
        bo, dc = StockAnalyzer(stock=ticker).check_last_days_diff_sma_lma(
            date(2023, 10, 1), date(2023, 10, 11)
        )
        if bo == True:
            ls.append(dc)
    except Exception:
        continue
results = pd.DataFrame.from_records(ls)
print(results)
results.to_csv("/tmp/results.csv", index=False)
