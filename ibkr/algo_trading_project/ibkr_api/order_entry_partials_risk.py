"""
Order entry script for IBKR with risk management and partials logic.
"""

from ib_insync import *
import math
import logging

# --- CONFIGURABLE PARAMETERS ---
ACCOUNT_AMOUNT = 10000  # Default account size in USD
TRADE_RISK_PCT = 0.01  # % of account to risk per trade (e.g. 0.01 = 1%)
PRICE_RISK_PCT = 0.003  # % of price for stop (e.g. 0.005 = 0.5%)
MAX_RISK_PCT = 0.01  # Max % of account to risk (e.g. 0.01 = 1%)

# --- IBKR CONNECTION ---
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=2)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def calc_shares(
    entry_price,
    account_amount=ACCOUNT_AMOUNT,
    trade_risk_pct=TRADE_RISK_PCT,
    price_risk_pct=PRICE_RISK_PCT,
    max_risk_pct=MAX_RISK_PCT,
):
    logging.debug(
        f"calc_shares called with entry_price={entry_price}, account_amount={account_amount}, trade_risk_pct={trade_risk_pct}, price_risk_pct={price_risk_pct}, max_risk_pct={max_risk_pct}"
    )
    risk_per_trade = min(account_amount * trade_risk_pct, account_amount * max_risk_pct)
    stop_dist = entry_price * price_risk_pct
    if stop_dist == 0:
        raise ValueError("Stop distance cannot be zero.")
    shares = math.floor(risk_per_trade / stop_dist)
    # Cap shares so that total position does not exceed account size
    max_shares_by_equity = math.floor(account_amount / entry_price)
    shares = min(shares, max_shares_by_equity)
    logging.debug(
        f"calc_shares result: shares={shares}, stop_dist={stop_dist}, risk_per_trade={risk_per_trade}"
    )
    return max(shares, 1), stop_dist, risk_per_trade


def place_entry_and_stop(stock, direction, shares, entry_price, stop_dist):
    action = "BUY" if direction == "long" else "SELL"
    stop_action = "SELL" if direction == "long" else "BUY"
    # Ensure shares is always positive
    shares = abs(shares)
    logging.info(
        f"Placing entry order:stock={stock.symbol} action={action}, shares={shares}, direction={direction}"
    )
    if (direction == "long" and action != "BUY") or (
        direction == "short" and action != "SELL"
    ):
        logging.warning(
            f"Direction/action mismatch: direction={direction}, action={action}"
        )
    entry_order = MarketOrder(action, shares)
    logging.debug(f"Sending entry order: {entry_order}")
    trade = ib.placeOrder(stock, entry_order)
    ib.sleep(2)
    fill_price = trade.orderStatus.avgFillPrice or entry_price
    logging.debug(f"Entry order fill_price: {fill_price}")
    stop_price = (
        fill_price - stop_dist if direction == "long" else fill_price + stop_dist
    )
    stop_price = round(stop_price, 2)
    logging.info(
        f"Placing stop order: action={stop_action}, shares={shares}, stop_price={stop_price}"
    )
    stop_order = StopOrder(stop_action, shares, stop_price)
    logging.debug(f"Sending stop order: {stop_order}")
    ib.placeOrder(stock, stop_order)
    return trade, fill_price, stop_order


def manage_partials(stock, direction, entry_price, stop_dist, shares, stop_order):
    # Partial sizes
    p1 = math.floor(shares * 0.3)
    p2 = math.floor(shares * 0.4)
    p3 = shares - p1 - p2
    stop1 = stop_order
    # Place limit orders for profit targets
    if direction == "long":
        t1_price = round(entry_price + stop_dist, 2)
        t2_price = round(entry_price + 2 * stop_dist, 2)
        t3_price = round(entry_price + 3 * stop_dist, 2)
        action = "SELL"
    else:
        t1_price = round(entry_price - stop_dist, 2)
        t2_price = round(entry_price - 2 * stop_dist, 2)
        t3_price = round(entry_price - 3 * stop_dist, 2)
        action = "BUY"
    # Place all limit orders at once
    t1_order = LimitOrder(action, p1, t1_price)
    t2_order = LimitOrder(action, p2, t2_price)
    t3_order = LimitOrder(action, p3, t3_price)
    t1_trade = ib.placeOrder(stock, t1_order)
    t2_trade = ib.placeOrder(stock, t2_order)
    t3_trade = ib.placeOrder(stock, t3_order)
    filled1 = filled2 = filled3 = False
    while True:
        ib.sleep(1)
        # Get current price
        md = ib.reqMktData(stock, "", False, False)
        price = md.last or md.close
        # Get current position
        positions = ib.positions()
        pos = 0.0
        for p in positions:
            if p.contract.conId == stock.conId:
                pos = p.position
                break
        ####Logging #### Determine next target and stop for logging
        if not filled1:
            next_target = t1_price
            next_target_str = f"T1 @ {t1_price}"
        elif not filled2:
            next_target = t2_price
            next_target_str = f"T2 @ {t2_price}"
        elif not filled3:
            next_target = t3_price
            next_target_str = f"T3 @ {t3_price}"
        else:
            next_target = None
            next_target_str = "No further targets"
        # Current stop value
        if filled2:
            stop_val = (
                round(entry_price + 2 * stop_dist, 2)
                if direction == "long"
                else round(entry_price - 2 * stop_dist, 2)
            )
        elif filled1:
            stop_val = (
                round(entry_price + stop_dist, 2)
                if direction == "long"
                else round(entry_price - stop_dist, 2)
            )
        else:
            stop_val = round(entry_price, 2)
        logging.info(
            f"Actual price: {price}, Next target: {next_target_str}, Stop at: {stop_val}, Position: {pos}, R={stop_dist}"
        )
        # Check order statuses
        if not filled1 and t1_trade.orderStatus.filled >= p1:
            filled1 = True
            # Move stop to BE
            ib.cancelOrder(stop1)
            stop_price = round(entry_price, 2)
            stop1 = StopOrder(action, shares - p1, stop_price)
            ib.placeOrder(stock, stop1)
            logging.info(
                f"Partial 1: Limit order filled for {p1} at {t1_price}, stop moved to BE {stop_price}"
            )
        if filled1 and not filled2 and t2_trade.orderStatus.filled >= p2:
            filled2 = True
            # Move stop to 1R
            ib.cancelOrder(stop1)
            stop_price = (
                round(entry_price + stop_dist, 2)
                if direction == "long"
                else round(entry_price - stop_dist, 2)
            )
            stop2 = StopOrder(action, shares - p1 - p2, stop_price)
            ib.placeOrder(stock, stop2)
            logging.info(
                f"Partial 2: Limit order filled for {p2} at {t2_price}, stop moved to 1R {stop_price}"
            )
        if filled2 and not filled3 and t3_trade.orderStatus.filled >= p3:
            filled3 = True
            # Move stop to 2R (for any remaining, but should be flat)
            ib.cancelOrder(stop2)
            stop_price = (
                round(entry_price + 2 * stop_dist, 2)
                if direction == "long"
                else round(entry_price - 2 * stop_dist, 2)
            )
            stop3 = StopOrder(action, 0, stop_price)
            logging.info(
                f"Partial 3: Limit order filled for {p3} at {t3_price}, stop moved to 2R {stop_price}"
            )
            break
        # Stop loss triggered (position closed)
        if pos == 0.0:
            logging.info(
                "Position is 0.0, manual exit or stop loss triggered. Exiting trade management."
            )
            # Cancel all remaining limit orders
            if not filled1:
                ib.cancelOrder(t1_order)
            if not filled2:
                ib.cancelOrder(t2_order)
            if not filled3:
                ib.cancelOrder(t3_order)
            break
    logging.info("Trade management complete.")


def run_strategy(symbol, direction="long"):
    stock = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(stock)
    md = ib.reqMktData(stock, "", False, False)
    ib.sleep(2)
    entry_price = md.last or md.close
    if entry_price is None or (
        isinstance(entry_price, float) and (math.isnan(entry_price) or entry_price == 0)
    ):
        print(
            f"ERROR: Could not retrieve a valid market price for {symbol}. Check your market data subscriptions and try again."
        )
        ib.disconnect()
        return
    shares, stop_dist, _ = calc_shares(entry_price)
    trade, fill_price, stop_order = place_entry_and_stop(
        stock, direction, shares, entry_price, stop_dist
    )
    manage_partials(stock, direction, fill_price, stop_dist, shares, stop_order)
    logging.info(
        f"Calculated shares={shares}, stop_dist={stop_dist}, entry_price={entry_price}"
    )


0

if __name__ == "__main__":
    logging.info("Script started as main.")
    run_strategy("AMD", direction="long")
