from finance.moving_averages.main import StockAnalyzer
import pandas_ta as ta


class TradingStrategy:
    def __init__(self, data, risk_percentage=0.05, reward_risk_ratio=2):
        self.data = data
        self.risk_percentage = risk_percentage
        self.reward_risk_ratio = reward_risk_ratio

    def get_next_signal(self):
        # Calculate the moving averages
        ma5 = self.data["Close"].rolling(window=5).mean()
        ma10 = self.data["Close"].rolling(window=10).mean()

        # Calculate the MACD
        self.data.ta.macd(close="close", fast=12, slow=26, append=True)
        print(self.data)

        # Generate a buy signal if the MACD crosses above the signal line and the moving averages are diverging
        if macd[0] > macd[1] and ma5 > ma10:
            return "buy"

        # Generate a sell signal if the MACD crosses below the signal line and the moving averages are converging
        elif macd[0] < macd[1] and ma5 < ma10:
            return "sell"
        else:
            return None


if __name__ == "__main__":
    data = StockAnalyzer(stock="AMZN").get_historical_yf(
        start="2021-01-01", end="2022-12-31"
    )
    strat = TradingStrategy(data=data)
    data["Signal"] = strat.get_next_signal()
