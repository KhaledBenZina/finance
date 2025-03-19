from ib_insync import *
import time
import logging
import math
import numpy as np
import pandas as pd

# Connect to TWS API
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def calculate_volatility_based_risk(symbol, timeframe=5, lookback=20):
    """
    Calculate risk (R) based on recent volatility.

    Parameters:
    - symbol: Stock symbol
    - timeframe: Chart timeframe in minutes (1 or 5)
    - lookback: Number of bars to look back for volatility calculation

    Returns:
    - R: Risk value in dollars
    """
    logging.info(
        f"Calculating volatility-based risk for {symbol} on {timeframe}-min chart..."
    )

    # Convert lookback periods to seconds for proper duration format
    # For 1-min chart with 20 bars, we need 20 minutes = 1200 seconds
    # For 5-min chart with 20 bars, we need 100 minutes = 6000 seconds
    seconds_needed = lookback * timeframe * 60

    # Use proper duration format: integer + space + unit (S|D|W|M|Y)
    duration = f"{seconds_needed} S"

    # For longer periods, convert to days to avoid potential issues
    if seconds_needed > 86400:  # More than 1 day in seconds
        days_needed = math.ceil(seconds_needed / 86400)
        duration = f"{days_needed} D"

    logging.info(f"Requesting historical data with duration: {duration}")

    bars = ib.reqHistoricalData(
        Stock(symbol, "SMART", "USD"),
        endDateTime="",  # Current time
        durationStr=duration,
        barSizeSetting=f"{timeframe} mins",
        whatToShow="TRADES",
        useRTH=True,
    )

    if not bars:
        logging.warning("No historical data returned. Using default risk value.")
        return 0.5  # Default risk value

    # Convert to pandas DataFrame
    df = pd.DataFrame(bars)

    # Calculate volatility using Average True Range (ATR)
    df["high_low"] = df["high"] - df["low"]
    df["high_close"] = abs(df["high"] - df["close"].shift(1))
    df["low_close"] = abs(df["low"] - df["close"].shift(1))
    df["tr"] = df[["high_low", "high_close", "low_close"]].max(axis=1)
    atr = df["tr"].mean()

    # Calculate risk as a percentage of ATR (adjust this factor based on your risk tolerance)
    risk_factor = 0.5  # More conservative: 0.3, More aggressive: 0.7
    R = round(atr * risk_factor, 2)

    logging.info(f"Calculated risk (R) based on {timeframe}-min volatility: ${R}")
    return R


def create_trailing_stop_order(action, quantity, trail_amount):
    """
    Creates a trailing stop order manually.

    Parameters:
    - action: 'SELL' or 'BUY'
    - quantity: Number of shares/contracts
    - trail_amount: The trailing amount
    """
    trailing_stop_order = Order(
        action=action,
        orderType="TRAIL",
        totalQuantity=quantity,
        auxPrice=trail_amount,  # This sets the trailing amount
    )
    return trailing_stop_order


def enter_trade(stock, direction, share_size, R):
    logging.info("Entering trade...")
    # Place initial market order for share_size shares
    initial_action = "BUY" if direction == "long" else "SELL"
    initial_order = MarketOrder(initial_action, share_size)
    trade = ib.placeOrder(stock, initial_order)
    ib.sleep(2)  # Wait for the order to fill
    entry_price = trade.orderStatus.avgFillPrice  # Capture fill price for reference
    logging.info(f"Initial order filled at {entry_price}")

    # Set initial stop loss
    stop_price = (
        entry_price - R if direction == "long" else entry_price + R
    )  # Stop loss logic for long/short
    stop_action = "SELL" if direction == "long" else "BUY"
    stop_loss_order = StopOrder(stop_action, share_size, stop_price)
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop loss order placed at {stop_price}")

    return trade, entry_price, stop_loss_order


def manage_trade(entry_price, trade, stop_loss_order, direction, share_size, R):
    logging.info("Managing trade...")
    # Set profit targets
    partial1_target = entry_price + R if direction == "long" else entry_price - R
    partial2_target = (
        entry_price + 2 * R if direction == "long" else entry_price - 2 * R
    )
    remaining_shares = share_size
    first_partial = False

    partial_size = math.ceil(share_size / 3)

    while remaining_shares > 0:
        # Check portfolio for current position
        portfolio = ib.portfolio()
        for item in portfolio:
            if item.contract.symbol == stock.symbol:
                if int(item.position) == 0:
                    logging.info("Position is 0. Exiting trade management.")
                    return  # Exit the function if the position is 0

        # Get latest price
        market_data = ib.reqMktData(stock)
        ib.sleep(1)  # Short delay for price polling
        current_price = market_data.last
        logging.info(f"Current price: {current_price}")

        # First partial take profit
        if not first_partial and (
            (
                current_price >= partial1_target
                if direction == "long"
                else current_price <= partial1_target
            )
        ):
            logging.info("First partial take profit target hit.")
            # Take partial of partial_size shares
            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order1 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order1)
            ib.cancelOrder(stop_loss_order)  # Remove initial stop
            logging.info(
                f"Partial order of {partial_size} shares placed and initial stop loss canceled."
            )

            # Adjust stop to break-even
            new_stop_price = entry_price
            stop_action = "SELL" if direction == "long" else "BUY"
            break_even_stop = StopOrder(
                stop_action, share_size - partial_size, new_stop_price
            )
            ib.placeOrder(stock, break_even_stop)
            logging.info(f"Break-even stop loss order placed at {new_stop_price}")
            remaining_shares -= partial_size
            first_partial = True  # Ensure first partial is only taken once

        # Second partial take profit
        if remaining_shares == share_size - partial_size and (
            (
                current_price >= partial2_target
                if direction == "long"
                else current_price <= partial2_target
            )
        ):
            logging.info("Second partial take profit target hit.")
            # Take another partial of partial_size shares
            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order2 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order2)
            ib.cancelOrder(break_even_stop)  # Remove break-even stop
            logging.info(
                f"Partial order of {partial_size} shares placed and break-even stop loss canceled."
            )

            # Set trailing stop for remaining shares
            trail_amount = R / 2  # Set trailing amount to half of R
            trailing_action = "SELL" if direction == "long" else "BUY"
            trailing_stop_order = create_trailing_stop_order(
                trailing_action, remaining_shares - partial_size, trail_amount
            )
            ib.placeOrder(stock, trailing_stop_order)
            logging.info(
                f"Trailing stop order placed for remaining {remaining_shares - partial_size} shares."
            )
            remaining_shares -= partial_size

        # Stop loss triggered
        if (current_price <= entry_price - R and direction == "long") or (
            current_price >= entry_price + R and direction == "short"
        ):
            logging.info("Stop loss triggered.")
            break

        ib.sleep(1)


# Main execution
if __name__ == "__main__":
    symbol = "NVDA"  # Change to your desired stock symbol
    direction = "short"  # Change to 'long' or 'short' based on the desired trade
    share_size = 100  # Define the initial share size
    timeframe = 5  # 1-min or 5-min chart

    # Calculate risk based on volatility
    R = calculate_volatility_based_risk(symbol, timeframe=timeframe, lookback=30)

    # Define contract for the stock
    stock = Stock(symbol, "SMART", "USD")

    # # Enter and manage trade
    trade, entry_price, stop = enter_trade(stock, direction, share_size, R)
    manage_trade(entry_price, trade, stop, direction, share_size, R)

    # # Disconnect from API
    ib.disconnect()
