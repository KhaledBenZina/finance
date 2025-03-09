# File: trading_alerts.py

import yfinance as yf
import pandas as pd
import numpy as np
import subprocess
import time
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# List of big-cap US stocks
symbols = ["NVDA", "TSLA"]

# Configurable threshold for proximity to key levels
THRESHOLD = 0.01  # 1% difference
ALERT_INTERVAL = (
    60  # Minimum interval in seconds between repeated alerts for the same condition
)

# Dictionary to track last alert times
last_alert_time = {symbol: {} for symbol in symbols}


def calculate_camarilla_pivots(high, low, close):
    """
    Calculate camarilla pivot points.
    """
    diff = high - low
    pivots = {
        "S3": close - diff * 1.1 / 12,
        "S4": close - diff * 1.1 / 6,
        "S5": close - diff * 1.1 / 2,
        "R3": close + diff * 1.1 / 12,
        "R4": close + diff * 1.1 / 6,
        "R5": close + diff * 1.1 / 2,
    }
    return pivots


def get_daily_levels(symbol):
    """
    Fetch historical daily data and calculate key levels using yfinance.
    """
    try:
        data = yf.download(symbol, period="5d", interval="1d")
        if data.empty:
            logging.warning(f"No historical data for {symbol}.")
            return None

        high, low, close = data["High"][-1], data["Low"][-1], data["Close"][-1]
        pivots = calculate_camarilla_pivots(high, low, close)

        levels = {
            "previous_close": close,
            "previous_high": high,
            "previous_low": low,
            "S3": pivots["S3"],
            "S4": pivots["S4"],
            "S5": pivots["S5"],
            "R3": pivots["R3"],
            "R4": pivots["R4"],
            "R5": pivots["R5"],
        }
        logging.info(f"Daily key levels for {symbol}: {levels}")
        return levels
    except Exception as e:
        logging.error(f"Error fetching daily data for {symbol}: {e}")
        return None


def calculate_intraday_levels(data):
    """
    Calculate intraday levels (VWAP, SMA) based on 1-minute data.
    """
    try:
        vwap = (data["Close"] * data["Volume"]).cumsum() / data["Volume"].cumsum()
        sma_50 = data["Close"].rolling(window=50).mean().iloc[-1]
        sma_200 = data["Close"].rolling(window=200).mean().iloc[-1]

        intraday_levels = {"VWAP": vwap.iloc[-1], "SMA_50": sma_50, "SMA_200": sma_200}
        logging.info(f"Intraday levels: {intraday_levels}")
        return intraday_levels
    except Exception as e:
        logging.error(f"Error calculating intraday levels: {e}")
        return {}


def check_conditions(symbol, daily_levels):
    """
    Monitor real-time data and check conditions.
    """
    try:
        data = yf.download(symbol, period="1d", interval="1m")
        if data.empty:
            logging.warning(f"No real-time data for {symbol}.")
            return

        intraday_levels = calculate_intraday_levels(data)
        current_price = data["Close"][-1]
        current_volume = data["Volume"][-1]
        prev_volume = data["Volume"][-2] if len(data) > 1 else 0

        all_levels = {**daily_levels, **intraday_levels}

        for level_name, level_value in all_levels.items():
            if abs(current_price - level_value) / level_value <= THRESHOLD:
                if current_volume > prev_volume:  # Volume rising
                    last_alert = last_alert_time[symbol].get(level_name, None)
                    if (
                        not last_alert
                        or (datetime.now() - last_alert).total_seconds()
                        > ALERT_INTERVAL
                    ):
                        send_alert(symbol, level_name, level_value, current_price)
                        last_alert_time[symbol][level_name] = datetime.now()
    except Exception as e:
        logging.error(f"Error checking conditions for {symbol}: {e}")


def send_alert(symbol, level_name, level_value, current_price):
    """
    Send a system alert using notify-send.
    """
    alert_message = (
        f"Alert: {symbol} is approaching {level_name} ({level_value:.2f}).\n"
        f"Current price: {current_price:.2f}"
    )
    subprocess.run(["notify-send", "Trading Alert", alert_message])
    logging.info(f"Sent alert for {symbol}: {alert_message}")
    print(alert_message)


def main():
    logging.info("Starting trading alert system...")
    while True:
        for symbol in symbols:
            daily_levels = get_daily_levels(symbol)
            if daily_levels:
                check_conditions(symbol, daily_levels)
        time.sleep(10)  # Adjust the frequency as needed


if __name__ == "__main__":
    main()
