from position import Position
from finance.moving_averages.main import StockAnalyzer


class AlgorithmicTrading:
    def __init__(self, data, strategy):
        self.data = data
        self.strategy = strategy
        self.positions = []

    def trade(self):
        # Get the next signal from the strategy
        signal = self.strategy.get_next_signal()

        # If a buy signal is generated, open a long position
        if signal == "buy":
            self.positions.append(Position(self.data["Close"].iloc[-1], "long"))

        # If a sell signal is generated, close the open long position
        elif signal == "sell":
            if len(self.positions) > 0 and self.positions[-1].type == "long":
                self.positions[-1].close_at(self.data["Close"].iloc[-1])

    def get_performance(self):
        # Calculate the total profit/loss
        total_profit_loss = 0
        for position in self.positions:
            total_profit_loss += position.profit_loss()

        # Calculate the return on investment (ROI)
        roi = total_profit_loss / self.data["Close"].iloc[0] * 100

        return roi
