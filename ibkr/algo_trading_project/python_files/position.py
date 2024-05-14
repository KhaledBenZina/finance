class Position:
    def __init__(self, entry_price, type):
        self.entry_price = entry_price
        self.type = type
        self.exit_price = None

    def close_at(self, exit_price):
        self.exit_price = exit_price

    def profit_loss(self):
        if self.exit_price is None:
            return 0
        else:
            if self.type == "long":
                return self.exit_price - self.entry_price
            else:
                return self.entry_price - self.exit_price
