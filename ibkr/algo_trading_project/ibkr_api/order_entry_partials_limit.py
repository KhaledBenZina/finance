import math
import logging
from ib_insync import *

# Assumes 'ib' is a connected IB instance
# Place entry, stop, and limit orders for partial exits


def place_entry_stop_and_targets(stock, direction, shares, entry_price, stop_dist):
    action = "BUY" if direction == "long" else "SELL"
    stop_action = "SELL" if direction == "long" else "BUY"
    shares = abs(shares)
    logging.info(
        f"Placing entry order: action={action}, shares={shares}, direction={direction}"
    )
    entry_order = MarketOrder(action, shares)
    trade = ib.placeOrder(stock, entry_order)
    ib.sleep(2)
    fill_price = trade.orderStatus.avgFillPrice or entry_price
    stop_price = (
        fill_price - stop_dist if direction == "long" else fill_price + stop_dist
    )
    stop_price = round(stop_price, 2)
    stop_order = StopOrder(stop_action, shares, stop_price)
    ib.placeOrder(stock, stop_order)
    # Calculate targets and partial sizes
    p1 = math.floor(shares * 0.3)
    p2 = math.floor(shares * 0.4)
    p3 = shares - p1 - p2
    targets = [
        (p1, fill_price + stop_dist if direction == "long" else fill_price - stop_dist),
        (
            p2,
            (
                fill_price + 2 * stop_dist
                if direction == "long"
                else fill_price - 2 * stop_dist
            ),
        ),
        (
            p3,
            (
                fill_price + 3 * stop_dist
                if direction == "long"
                else fill_price - 3 * stop_dist
            ),
        ),
    ]
    limit_orders = []
    for qty, tgt in targets:
        tgt = round(tgt, 2)
        limit_action = "SELL" if direction == "long" else "BUY"
        order = LimitOrder(limit_action, qty, tgt)
        ib.placeOrder(stock, order)
        limit_orders.append(order)
    return trade, fill_price, stop_order, limit_orders


# Example usage:
# trade, fill_price, stop_order, limit_orders = place_entry_stop_and_targets(stock, 'long', 100, 50.0, 1.0)
# Now monitor for stop or target fills and adjust/cancel orders as needed.
