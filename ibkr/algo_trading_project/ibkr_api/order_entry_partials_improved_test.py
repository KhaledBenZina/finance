from ib_insync import *
import time
import logging
import math
import pandas as pd

# Connect to TWS API
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def get_ATR(stock, period=14):
    """
    Fetch historical data and calculate the Average True Range (ATR).
    """
    bars = ib.reqHistoricalData(
        stock,
        endDateTime="",
        durationStr="30 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )

    if not bars:
        logging.error("Failed to retrieve historical data for ATR calculation.")
        return 0.5  # Default to 0.5 if ATR cannot be fetched

    df = pd.DataFrame(bars)
    df["high-low"] = df["high"] - df["low"]
    df["high-close"] = abs(df["high"] - df["close"].shift(1))
    df["low-close"] = abs(df["low"] - df["close"].shift(1))
    df["true_range"] = df[["high-low", "high-close", "low-close"]].max(axis=1)
    atr = df["true_range"].rolling(window=period).mean().iloc[-1]

    logging.info(f"ATR calculated: {atr:.2f}")
    return atr


def create_trailing_stop_order(action, quantity, trail_amount):
    return Order(
        action=action, orderType="TRAIL", totalQuantity=quantity, auxPrice=trail_amount
    )


def enter_trade(stock, direction, share_size, atr):
    logging.info("Entering trade...")

    initial_action = "BUY" if direction == "long" else "SELL"
    initial_order = MarketOrder(initial_action, share_size)
    trade = ib.placeOrder(stock, initial_order)

    while not trade.orderStatus.avgFillPrice:
        ib.sleep(0.5)

    entry_price = trade.orderStatus.avgFillPrice
    logging.info(f"Trade filled at {entry_price}")

    # ATR-based stop-loss & take-profits
    stop_loss = (
        entry_price - (atr * 1.5) if direction == "long" else entry_price + (atr * 1.5)
    )
    partial1_target = (
        entry_price + (atr * 1.5) if direction == "long" else entry_price - (atr * 1.5)
    )
    partial2_target = (
        entry_price + (atr * 3) if direction == "long" else entry_price - (atr * 3)
    )

    stop_action = "SELL" if direction == "long" else "BUY"
    stop_loss_order = StopOrder(stop_action, share_size, stop_loss)
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop-loss placed at {stop_loss}")

    return trade, entry_price, stop_loss_order, partial1_target, partial2_target


def manage_trade(
    entry_price,
    trade,
    stop_loss_order,
    direction,
    share_size,
    partial1_target,
    partial2_target,
):
    logging.info("Managing trade...")

    remaining_shares = share_size
    first_partial = False
    partial_size = math.ceil(share_size / 3)

    while remaining_shares > 0:
        portfolio = ib.portfolio()
        position_found = False

        for item in portfolio:
            if item.contract.symbol == stock.symbol and int(item.position) > 0:
                position_found = True
                break

        if not position_found:
            logging.info("Position closed. Exiting trade management.")
            return

        market_data = ib.reqMktData(stock)
        ib.sleep(1)
        current_price = market_data.last if market_data.last else market_data.close

        logging.info(f"Current price: {current_price}")

        if not first_partial and (
            (
                current_price >= partial1_target
                if direction == "long"
                else current_price <= partial1_target
            )
        ):
            logging.info("First partial profit hit.")

            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order1 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order1)
            ib.sleep(1)

            ib.cancelOrder(stop_loss_order)

            new_stop_price = entry_price
            break_even_stop = StopOrder(
                partial_action, share_size - partial_size, new_stop_price
            )
            ib.placeOrder(stock, break_even_stop)
            logging.info(f"Break-even stop set at {new_stop_price}")

            remaining_shares -= partial_size
            first_partial = True

        if remaining_shares == share_size - partial_size and (
            (
                current_price >= partial2_target
                if direction == "long"
                else current_price <= partial2_target
            )
        ):
            logging.info("Second partial take profit hit.")

            partial_order2 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order2)
            ib.sleep(1)

            ib.cancelOrder(break_even_stop)

            trail_amount = atr * 1.5
            trailing_action = "SELL" if direction == "long" else "BUY"
            trailing_stop_order = create_trailing_stop_order(
                trailing_action, remaining_shares - partial_size, trail_amount
            )
            ib.placeOrder(stock, trailing_stop_order)
            logging.info(
                f"Trailing stop set for {remaining_shares - partial_size} shares."
            )

            remaining_shares -= partial_size

        if (current_price <= entry_price - (atr * 1.5) and direction == "long") or (
            current_price >= entry_price + (atr * 1.5) and direction == "short"
        ):
            logging.info("Stop loss hit.")
            break

        ib.sleep(1)


# Execution
direction = "long"
share_size = 100
stock = Stock("NVDA", "SMART", "USD")

atr = get_ATR(stock)  # Fetch ATR before entering trade
trade, entry_price, stop, partial1, partial2 = enter_trade(
    stock, direction, share_size, atr
)
manage_trade(entry_price, trade, stop, direction, share_size, partial1, partial2)

ib.disconnect()
