"""
VWAP intraday pullback strategy for big-cap US stocks (IBKR / ib_insync).
Run in paper trading first. Requires: pip install ib_insync pandas numpy
"""

import time
import math
import logging
from datetime import datetime, timedelta, time as dtime
import pandas as pd
import numpy as np
from ib_insync import IB, Stock, util, MarketOrder, LimitOrder, Order

# ---------------------------
# CONFIG
# ---------------------------
IB_HOST = "127.0.0.1"
IB_PORT = 7497  # 7497 for paper TWS by default; 7496 for live TWS (check your set-up)
CLIENT_ID = 1

TICKERS = ["AAPL", "MSFT"]  # pick your liquid names
EXCHANGE = "SMART"
CURRENCY = "USD"

BAR_SIZE = "1 min"
DURATION_STR = "1 D"  # pull today's data
WHAT_TO_SHOW = "TRADES"

MINUTES_TO_ESTABLISH_BIAS = 15
MAX_TRADES_PER_TICKER = 2
RISK_PCT = 0.003  # risk 0.3% of account equity per trade
RR = 1.0  # reward:risk for first target (you can add second target)
MAX_OPEN_POSITIONS = 3

# thresholds
VWAP_TOUCH_TOLERANCE = 0.0015  # 0.15% tolerance around VWAP for 'touch'
MIN_VOLUME_MULTIPLIER = 1.0  # entry candle must have volume >= this * avg_volume
STOP_BUFFER = 0.0005  # extra buffer to avoid being too tight (0.05%)

# trading hours (Eastern) - adapt if needed
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


# ---------------------------
# UTILS
# ---------------------------
def typical_price(row):
    return (row["high"] + row["low"] + row["close"]) / 3.0


def compute_intraday_vwap(df):
    """
    df expected with columns: open, high, low, close, volume and index is datetime (NY/Exchange tz).
    Returns a Series of VWAP computed cumulatively from the first row.
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    cum_pv = pv.cumsum()
    cum_v = df["volume"].cumsum()
    vwap = cum_pv / cum_v.replace(0, np.nan)
    return vwap


def get_account_equity(ib):
    # simple approach: sum of netLiquidation in all accounts. You can refine to your prefered account
    acct = ib.accountValues()
    # find NetLiquidation
    for ev in acct:
        if ev.tag == "NetLiquidation" and ev.currency == "USD":
            try:
                return float(ev.value)
            except:
                continue
    # fallback
    return 100000.0


def qty_from_risk(equity, risk_pct, entry_price, stop_price):
    risk_amount = equity * risk_pct
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0:
        return 0
    raw_qty = math.floor(risk_amount / per_share_risk)
    return max(0, int(raw_qty))


# ---------------------------
# IB CONNECT
# ---------------------------
ib = IB()
ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID, timeout=10)
logging.info("Connected to IBKR: %s", ib.isConnected())

# prepare contract objects
contracts = {sym: Stock(sym, EXCHANGE, CURRENCY) for sym in TICKERS}

# state
trade_counts = {sym: 0 for sym in TICKERS}
open_positions = {}  # sym -> ib position object or qty
active_orders = {}  # orderId -> metadata


# ---------------------------
# MAIN LOGIC
# ---------------------------
def daily_vwap_logic(sym):
    """
    Fetch today's 1-min bars, compute VWAP and check signals.
    Returns DataFrame with vwap column.
    """
    contract = contracts[sym]
    # request historical bars from IB for 1 day; then compute VWAP from market open
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=DURATION_STR,
        barSizeSetting=BAR_SIZE,
        whatToShow=WHAT_TO_SHOW,
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        logging.warning("No bars for %s", sym)
        return None

    df = util.df(bars)
    # ensure columns: date, open, high, low, close, volume
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df[["open", "high", "low", "close", "volume"]].copy()

    # restrict to today's regular session (safety)
    df = df.between_time(MARKET_OPEN, MARKET_CLOSE)

    df["vwap"] = compute_intraday_vwap(df)
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3
    # rolling avg volume for entry filter
    df["vol_avg_5"] = df["volume"].rolling(5, min_periods=1).mean()
    return df


def signal_check_and_trade(sym, df):
    """
    Check for entry signals on latest bar and place bracket order if criteria met.
    """
    global trade_counts, open_positions, active_orders

    if df is None or df.empty:
        return

    latest = df.iloc[-1]
    now = latest.name.to_pydatetime()

    # ensure bias established
    if len(df) < MINUTES_TO_ESTABLISH_BIAS:
        return

    # determine bias: compare recent mean price (last 3 bars close) vs VWAP
    recent_mean = df["close"].iloc[-3:].mean()
    current_vwap = latest["vwap"]
    if pd.isna(current_vwap):
        return

    bias = "neutral"
    if recent_mean > current_vwap:
        bias = "bull"
    elif recent_mean < current_vwap:
        bias = "bear"

    # avoid trading if bias neutral
    if bias == "neutral":
        return

    # check if we already have reached trade limit for this ticker today
    if trade_counts.get(sym, 0) >= MAX_TRADES_PER_TICKER:
        return

    # skip if we already have open position in this symbol
    pos_qty = 0
    positions = ib.positions()
    for p in positions:
        if p.contract.symbol == sym:
            pos_qty = p.position
            break
    if pos_qty != 0:
        return

    # define "touch" of VWAP: price within tolerance of VWAP
    price = latest["close"]
    tol = VWAP_TOUCH_TOLERANCE * price
    touched_vwap = abs(price - current_vwap) <= tol

    # check volume on latest candle
    vol_ok = latest["volume"] >= (MIN_VOLUME_MULTIPLIER * latest["vol_avg_5"])

    # momentum filter: simple RSI-ish via returns
    recent_return = (df["close"].iloc[-1] - df["close"].iloc[-3]) / df["close"].iloc[-3]
    if bias == "bull":
        momentum_ok = recent_return > 0  # simple
    else:
        momentum_ok = recent_return < 0

    # ENTRY conditions: bias established AND touched VWAP AND volume/momentum confirmation
    entry_allowed = touched_vwap and vol_ok and momentum_ok

    if not entry_allowed:
        return

    # prepare order parameters
    equity = get_account_equity(ib)
    # stop price: for long, place stop just below recent low (last 5 bars) minus buffer
    recent_low = df["low"].iloc[-5:].min()
    recent_high = df["high"].iloc[-5:].max()

    if bias == "bull":
        entry_price = (
            price  # market/limit at current close; you can set small limit below
        )
        stop_price = recent_low * (1.0 - STOP_BUFFER)
        target_price = entry_price + (entry_price - stop_price) * RR
    else:
        entry_price = price
        stop_price = recent_high * (1.0 + STOP_BUFFER)
        target_price = entry_price - (stop_price - entry_price) * RR

    qty = qty_from_risk(equity, RISK_PCT, entry_price, stop_price)
    if qty <= 0:
        logging.info(
            "Qty computed zero for %s: equity=%.2f entry=%.2f stop=%.2f",
            sym,
            equity,
            entry_price,
            stop_price,
        )
        return

    logging.info(
        "Placing %s entry for %s, qty=%d entry=%.4f stop=%.4f target=%.4f",
        bias,
        sym,
        qty,
        entry_price,
        stop_price,
        target_price,
    )

    # create bracket order: parent + profit taker + stop
    contract = contracts[sym]
    # Use Limit entry at entry_price (or market if you prefer)
    parent = LimitOrder(
        "BUY" if bias == "bull" else "SELL", qty, entry_price, tif="DAY"
    )
    parent.orderId = None

    # Profit taker
    if bias == "bull":
        take = LimitOrder("SELL", qty, target_price)
    else:
        take = LimitOrder("BUY", qty, target_price)

    # Stop
    if bias == "bull":
        stop = Order(
            action="SELL", totalQuantity=qty, orderType="STP", auxPrice=stop_price
        )
    else:
        stop = Order(
            action="BUY", totalQuantity=qty, orderType="STP", auxPrice=stop_price
        )

    # attach OCA or send bracket manually. ib_insync has bracketOrder helper but we'll send 3 orders and link via parentId
    bracket = ib.bracketOrder(
        (
            parent.orderType
            if hasattr(parent, "orderType")
            else parent.orderType if hasattr(parent, "orderType") else "LMT"
        ),
        (
            parent.action
            if hasattr(parent, "action")
            else parent.action if hasattr(parent, "action") else "BUY"
        ),
        qty,
        entry_price,
        target_price,
        stop_price,
    )

    # bracketOrder returns list [parent, take, stop]
    # BUT ib.bracketOrder expects parameters differently; simpler: use ib.placeOrder for parent then attach child orders with parentId
    # For clarity and safety: use Market parent for immediate entry (or limit). Here we place a LIMIT parent then 2 child orders.

    # Place parent and children
    try:
        # Place parent:
        order_parent = LimitOrder(
            "BUY" if bias == "bull" else "SELL", qty, entry_price, tif="DAY"
        )
        trade = ib.placeOrder(contract, order_parent)
        # wait for orderId to be assigned
        time.sleep(0.5)
        parentId = order_parent.orderId

        # create and place child stop and take with parentId set
        take_order = LimitOrder("SELL" if bias == "bull" else "BUY", qty, target_price)
        take_order.parentId = parentId
        take_order.transmit = False

        stop_order = Order(
            action="SELL" if bias == "bull" else "BUY",
            totalQuantity=qty,
            orderType="STP",
            auxPrice=stop_price,
        )
        stop_order.parentId = parentId
        stop_order.transmit = True  # final transmit True to send children together

        trade_take = ib.placeOrder(contract, take_order)
        trade_stop = ib.placeOrder(contract, stop_order)

        # track
        trade_counts[sym] = trade_counts.get(sym, 0) + 1
        active_orders[parentId] = dict(
            sym=sym, parent=order_parent, take=take_order, stop=stop_order, time=now
        )

        logging.info("Bracket placed for %s parentId=%s", sym, parentId)

    except Exception as e:
        logging.exception("Failed to place bracket for %s: %s", sym, e)
        return


# ---------------------------
# RUN LOOP (polling)
# ---------------------------
def main_loop():
    # run during market hours
    logging.info("Starting main loop")
    while True:
        now_utc = datetime.now(datetime.timezone.utc)
        # convert to local NY time naive approximations? ib returns bars in market timezone; trust ib timestamps
        # Simplest: only run between market open and close in local machine timezone if your machine is aligned. Better: check exchange time in bars.

        # For each symbol, fetch latest df and run logic
        for sym in TICKERS:
            try:
                df = daily_vwap_logic(sym)
                signal_check_and_trade(sym, df)
            except Exception as e:
                logging.exception("Error processing %s: %s", sym, e)

        # housekeeping: cancel stale orders, clear trackers after market close
        local_time = datetime.now().time()
        if local_time > MARKET_CLOSE:
            logging.info("Market closed - exiting loop")
            break

        # sleep: because we use 1-min bars, wake up every 30 seconds to catch new bars quickly
        time.sleep(30)


if __name__ == "__main__":
    try:
        main_loop()
    finally:
        logging.info("Disconnecting IB")
        ib.disconnect()
