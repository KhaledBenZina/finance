from ib_insync import *
import logging
import math
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Global variables
R = 0.5  # Risk amount


class TradeManager:
    def __init__(self, ib):
        self.ib = ib
        self.active_trades = {}

    def create_trailing_stop_order(self, action, quantity, trail_amount):
        """Creates a trailing stop order"""
        trailing_stop_order = Order(
            action=action,
            orderType="TRAIL",
            totalQuantity=quantity,
            auxPrice=trail_amount,  # This sets the trailing amount
        )
        return trailing_stop_order

    async def enter_trade(self, stock, direction, share_size):
        logging.info(
            f"Entering {direction} trade for {stock.symbol} with {share_size} shares..."
        )

        # Place initial market order
        initial_action = "BUY" if direction == "long" else "SELL"
        initial_order = MarketOrder(initial_action, share_size)
        trade = self.ib.placeOrder(stock, initial_order)

        # Wait for the trade to fill using event-driven approach
        fill_future = asyncio.Future()

        def on_execution(trade, fill):
            if not fill_future.done() and trade.orderStatus.status == "Filled":
                fill_future.set_result((trade, fill))

        # Register temporary callback for this specific trade
        self.ib.execDetailsEvent += on_execution

        try:
            # Wait for order to fill with timeout
            trade, fill = await asyncio.wait_for(fill_future, timeout=30)
            entry_price = fill.execution.price
            logging.info(f"Entry order filled at {entry_price}")

            # Setup stop loss
            stop_price = entry_price - R if direction == "long" else entry_price + R
            stop_action = "SELL" if direction == "long" else "BUY"
            stop_loss_order = StopOrder(stop_action, share_size, stop_price)
            stop_trade = self.ib.placeOrder(stock, stop_loss_order)

            logging.info(f"Stop loss order placed at {stop_price}")

            # Store active trade info for management
            self.active_trades[stock.symbol] = {
                "entry_price": entry_price,
                "direction": direction,
                "share_size": share_size,
                "remaining_shares": share_size,
                "stop_trade": stop_trade,
                "first_partial_taken": False,
                "second_partial_taken": False,
                "partial_size": math.ceil(share_size / 3),
            }

            # Start price monitoring for this trade
            await self.setup_price_monitoring(stock)

        except asyncio.TimeoutError:
            logging.error("Timeout waiting for order to fill")
            self.ib.cancelOrder(trade.order)
            return None
        finally:
            # Remove temporary callback
            self.ib.execDetailsEvent -= on_execution

        return trade

    async def setup_price_monitoring(self, stock):
        """Set up real-time price monitoring for a stock"""
        symbol = stock.symbol

        # Request real-time market data if not already requested
        self.ib.reqMktData(stock)

        # Create ticker
        ticker = self.ib.ticker(stock)

        # Periodic check for price changes instead of direct event binding
        # which can be more complex to implement correctly
        while symbol in self.active_trades:
            current_price = ticker.last if ticker.last else ticker.close

            # Skip if no valid price
            if not current_price or current_price <= 0:
                await asyncio.sleep(0.2)  # Much shorter sleep than original code
                continue

            trade_info = self.active_trades[symbol]
            direction = trade_info["direction"]
            entry_price = trade_info["entry_price"]
            remaining_shares = trade_info["remaining_shares"]

            # First partial take profit
            partial1_target = (
                entry_price + R if direction == "long" else entry_price - R
            )
            if (
                not trade_info["first_partial_taken"]
                and remaining_shares > 0
                and (
                    (current_price >= partial1_target and direction == "long")
                    or (current_price <= partial1_target and direction == "short")
                )
            ):

                await self.take_first_partial(stock, trade_info)

            # Second partial take profit
            partial2_target = (
                entry_price + 2 * R if direction == "long" else entry_price - 2 * R
            )
            if (
                trade_info["first_partial_taken"]
                and not trade_info["second_partial_taken"]
                and remaining_shares > trade_info["partial_size"]
                and (
                    (current_price >= partial2_target and direction == "long")
                    or (current_price <= partial2_target and direction == "short")
                )
            ):

                await self.take_second_partial(stock, trade_info)

            # Check if position is still open
            portfolio = self.ib.portfolio()
            position_found = False
            for item in portfolio:
                if item.contract.symbol == symbol:
                    if abs(item.position) > 0:
                        position_found = True
                    break

            if not position_found:
                logging.info(f"Position for {symbol} closed, stopping price monitoring")
                if symbol in self.active_trades:
                    del self.active_trades[symbol]
                break

            # Short sleep between checks - much faster than original code
            await asyncio.sleep(0.2)  # 200ms check interval

    async def take_first_partial(self, stock, trade_info):
        """Execute first partial profit target"""
        partial_size = trade_info["partial_size"]
        direction = trade_info["direction"]

        logging.info(f"First partial take profit target hit for {stock.symbol}")

        # Take partial profit
        partial_action = "SELL" if direction == "long" else "BUY"
        partial_order = MarketOrder(partial_action, partial_size)
        self.ib.placeOrder(stock, partial_order)

        # Cancel initial stop loss
        self.ib.cancelOrder(trade_info["stop_trade"].order)

        # Move stop to break-even
        new_stop_price = trade_info["entry_price"]
        stop_action = "SELL" if direction == "long" else "BUY"
        remaining = trade_info["remaining_shares"] - partial_size
        break_even_stop = StopOrder(stop_action, remaining, new_stop_price)
        break_even_trade = self.ib.placeOrder(stock, break_even_stop)

        # Update trade info
        trade_info["remaining_shares"] -= partial_size
        trade_info["stop_trade"] = break_even_trade
        trade_info["first_partial_taken"] = True

        logging.info(
            f"Partial order of {partial_size} shares placed, "
            f"remaining: {trade_info['remaining_shares']}. "
            f"Stop moved to break-even at {new_stop_price}"
        )

    async def take_second_partial(self, stock, trade_info):
        """Execute second partial profit target"""
        partial_size = trade_info["partial_size"]
        direction = trade_info["direction"]

        logging.info(f"Second partial take profit target hit for {stock.symbol}")

        # Take second partial
        partial_action = "SELL" if direction == "long" else "BUY"
        partial_order = MarketOrder(partial_action, partial_size)
        self.ib.placeOrder(stock, partial_order)

        # Cancel break-even stop
        self.ib.cancelOrder(trade_info["stop_trade"].order)

        # Set trailing stop for remainder
        trail_amount = 2 * R
        trailing_action = "SELL" if direction == "long" else "BUY"
        remaining = trade_info["remaining_shares"] - partial_size

        trailing_stop = self.create_trailing_stop_order(
            trailing_action, remaining, trail_amount
        )
        trailing_trade = self.ib.placeOrder(stock, trailing_stop)

        # Update trade info
        trade_info["remaining_shares"] -= partial_size
        trade_info["stop_trade"] = trailing_trade
        trade_info["second_partial_taken"] = True

        logging.info(
            f"Second partial of {partial_size} shares taken, "
            f"remaining: {trade_info['remaining_shares']}. "
            f"Trailing stop of {trail_amount} set for remaining shares."
        )


async def main():
    # Set up IB connection
    ib = IB()
    await ib.connectAsync("127.0.0.1", 7497, clientId=1)

    # Create trade manager
    manager = TradeManager(ib)

    # Example trade setup
    stock = Stock("NVDA", "SMART", "USD")
    direction = "long"
    share_size = 100

    # Enter trade
    trade = await manager.enter_trade(stock, direction, share_size)

    if trade:
        logging.info("Trade successfully entered, monitoring for exit conditions")
    else:
        logging.error("Failed to enter trade")

    # Keep the program running
    try:
        # Run until all positions are closed
        while manager.active_trades:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
