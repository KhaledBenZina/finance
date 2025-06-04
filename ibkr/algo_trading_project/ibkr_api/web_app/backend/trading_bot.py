import asyncio
import json
import math
import logging
import nest_asyncio
import time
import sys
import numpy as np
import pandas as pd
from aiohttp import web
from ib_insync import *

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize IB connection
ib = IB()
connected_clients = set()
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds


async def connect_ib_with_retry():
    """Connect to Interactive Brokers with retry logic"""
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            if not ib.isConnected():
                logger.info(
                    f"Connection attempt {attempt}/{MAX_RETRY_ATTEMPTS} to Interactive Brokers..."
                )

                # Verify TWS/Gateway settings
                host = "127.0.0.1"
                port = (
                    7497  # 7497 for TWS paper trading, 7496 for Gateway paper trading
                )
                clientId = 1

                logger.info(f"Connecting to {host}:{port} with clientId {clientId}")

                # Set a timeout for the connection
                ib.connect(host, port, clientId=clientId, timeout=15)

                # Verify connection is established
                if ib.isConnected():
                    logger.info("Successfully connected to Interactive Brokers")

                    # Check if we can retrieve account information
                    # This is a good test to validate the connection is working properly
                    try:
                        accounts = ib.managedAccounts()
                        logger.info(f"Available accounts: {accounts}")
                    except Exception as e:
                        logger.warning(
                            f"Connected but couldn't retrieve account info: {e}"
                        )

                    return True
                else:
                    logger.error("Connection failed despite no errors")
            else:
                logger.info("Already connected to Interactive Brokers")
                return True

        except Exception as e:
            logger.error(f"Connection attempt {attempt} failed: {e}")

            # Provide more helpful messages based on common errors
            if "timeout" in str(e).lower():
                logger.error(
                    """
                CONNECTION TIMEOUT: Please check that:
                1. TWS or IB Gateway is running
                2. API connections are enabled in TWS/Gateway settings
                3. Auto-restart for API connections is enabled
                4. The correct port is being used (7496 for Gateway, 7497 for TWS paper trading)
                """
                )
            elif "permission denied" in str(e).lower():
                logger.error(
                    """
                PERMISSION DENIED: Please check that:
                1. You've accepted API connections in TWS/Gateway
                2. The clientId (1) is not being used by another application
                """
                )

            if attempt < MAX_RETRY_ATTEMPTS:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"All {MAX_RETRY_ATTEMPTS} connection attempts failed")
                return False

    return False


# 3R Trading Strategy Functions
async def calculate_volatility_based_risk(symbol, timeframe=5, lookback=20):
    """
    Calculate risk (R) based on recent volatility.
    """
    logger.info(
        f"Calculating volatility-based risk for {symbol} on {timeframe}-min chart..."
    )

    # Convert lookback periods to seconds for proper duration format
    seconds_needed = lookback * timeframe * 60

    # Use proper duration format: integer + space + unit (S|D|W|M|Y)
    duration = f"{seconds_needed} S"

    # For longer periods, convert to days to avoid potential issues
    if seconds_needed > 86400:  # More than 1 day in seconds
        days_needed = math.ceil(seconds_needed / 86400)
        duration = f"{days_needed} D"

    logger.info(f"Requesting historical data with duration: {duration}")

    # Request historical data
    try:
        bars = ib.reqHistoricalData(
            Stock(symbol, "SMART", "USD"),
            endDateTime="",  # Current time
            durationStr=duration,
            barSizeSetting=f"{timeframe} mins",
            whatToShow="TRADES",
            useRTH=True,
        )

        if not bars or len(bars) < lookback / 2:  # At least half the requested bars
            logger.warning(
                f"Insufficient historical data returned ({len(bars) if bars else 0} bars). Using default risk value."
            )
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

        logger.info(f"Calculated risk (R) based on {timeframe}-min volatility: ${R}")
        return R

    except Exception as e:
        logger.error(f"Error calculating volatility-based risk: {e}")
        return 0.5  # Default risk value on error


async def create_trailing_stop_order(action, quantity, trail_amount):
    """
    Creates a trailing stop order manually.
    """
    trailing_stop_order = Order(
        action=action,
        orderType="TRAIL",
        totalQuantity=quantity,
        auxPrice=trail_amount,  # This sets the trailing amount
    )
    return trailing_stop_order


async def enter_3r_trade(ws, symbol, direction, share_size, timeframe, lookback):
    """
    Implements the 3R trading strategy
    """
    try:
        # Define stock contract
        stock = Stock(symbol, "SMART", "USD")

        # Calculate risk based on volatility
        R = await calculate_volatility_based_risk(
            symbol, timeframe=timeframe, lookback=lookback
        )

        # Send initial confirmation and R value
        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Calculating risk",
                "message": f"Calculated R value: ${R}",
                "r_value": R,
            }
        )

        # Place initial market order for share_size shares
        initial_action = "BUY" if direction == "long" else "SELL"
        initial_order = MarketOrder(initial_action, share_size)

        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Entering trade",
                "message": f"Placing initial {initial_action} order for {share_size} shares",
            }
        )

        trade = ib.placeOrder(stock, initial_order)
        await asyncio.sleep(2)  # Wait for the order to fill

        # Check if order is filled
        filled = False
        timeout = 10  # seconds
        start_time = time.time()
        while not filled and (time.time() - start_time) < timeout:
            ib.waitOnUpdate(timeout=0.2)
            if trade.orderStatus.status == "Filled":
                filled = True
                break
            await asyncio.sleep(0.5)

        if not filled:
            await ws.send_json(
                {
                    "type": "3r_trade_update",
                    "status": "Warning",
                    "message": "Order not filled within timeout period. Will use last status available.",
                }
            )

        # Capture fill price for reference
        entry_price = trade.orderStatus.avgFillPrice
        if not entry_price or math.isnan(entry_price):
            # Get current market price as fallback
            market_data = ib.reqMktData(stock)
            await asyncio.sleep(1)
            entry_price = market_data.last

        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Trade entered",
                "message": f"Initial order filled at {entry_price}",
                "entry_price": entry_price,
            }
        )

        # Set initial stop loss
        stop_price = entry_price - R if direction == "long" else entry_price + R
        stop_action = "SELL" if direction == "long" else "BUY"
        stop_loss_order = StopOrder(stop_action, share_size, stop_price)
        ib.placeOrder(stock, stop_loss_order)

        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Stop loss placed",
                "message": f"Stop loss order placed at {stop_price}",
                "stop_price": stop_price,
            }
        )

        # Calculate profit targets
        partial1_target = entry_price + R if direction == "long" else entry_price - R
        partial2_target = (
            entry_price + 2 * R if direction == "long" else entry_price - 2 * R
        )

        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Targets set",
                "message": f"1R target: {partial1_target}, 2R target: {partial2_target}",
                "target1": partial1_target,
                "target2": partial2_target,
            }
        )

        # Start trade management in a background task
        asyncio.create_task(
            manage_3r_trade(
                ws,
                entry_price,
                trade,
                stop_loss_order,
                direction,
                share_size,
                R,
                stock,
                partial1_target,
                partial2_target,
            )
        )

        return True

    except Exception as e:
        logger.error(f"Error executing 3R trade: {e}")
        await ws.send_json(
            {"type": "error", "message": f"Failed to execute 3R trade: {e}"}
        )
        return False


async def manage_3r_trade(
    ws,
    entry_price,
    trade,
    stop_loss_order,
    direction,
    share_size,
    R,
    stock,
    partial1_target,
    partial2_target,
):
    """
    Manages the 3R trade with partial profit taking
    """
    try:
        logger.info("Managing 3R trade...")
        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Managing trade",
                "message": "Monitoring price for partial exits and stop adjustments",
            }
        )

        remaining_shares = share_size
        first_partial = False
        second_partial = False
        break_even_stop = None
        partial_size = math.ceil(share_size / 3)

        # Monitor the trade for a set period or until closed
        max_monitoring_time = 60 * 60  # 1 hour maximum
        start_monitoring_time = time.time()

        while (
            remaining_shares > 0
            and (time.time() - start_monitoring_time) < max_monitoring_time
        ):
            # Check if we still have a position
            try:
                portfolio = ib.portfolio()
                position_size = 0

                for item in portfolio:
                    if item.contract.symbol == stock.symbol:
                        position_size = item.position
                        if (direction == "long" and position_size <= 0) or (
                            direction == "short" and position_size >= 0
                        ):
                            await ws.send_json(
                                {
                                    "type": "3r_trade_update",
                                    "status": "Closed",
                                    "message": f"Position closed. Final size: {position_size}",
                                }
                            )
                            return  # Exit the function if the position is closed
                        break
            except Exception as e:
                logger.error(f"Error checking portfolio: {e}")

            # Get latest price
            try:
                market_data = ib.reqMktData(stock)
                await asyncio.sleep(1)  # Short delay for price polling
                current_price = market_data.last

                if current_price and not math.isnan(current_price):
                    logger.info(f"Current price: {current_price}")

                    # Send price update periodically (not every loop to avoid flooding)
                    if int(time.time()) % 10 == 0:  # Every 10 seconds
                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Price update",
                                "message": f"Current price: {current_price}",
                                "current_price": current_price,
                            }
                        )

                    # First partial take profit
                    if not first_partial and (
                        (
                            current_price >= partial1_target
                            if direction == "long"
                            else current_price <= partial1_target
                        )
                    ):
                        logger.info("First partial take profit target hit.")
                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Target 1 hit",
                                "message": f"First partial target hit: {partial1_target}",
                            }
                        )

                        # Take partial of partial_size shares
                        partial_action = "SELL" if direction == "long" else "BUY"
                        partial_order1 = MarketOrder(partial_action, partial_size)
                        ib.placeOrder(stock, partial_order1)
                        ib.cancelOrder(stop_loss_order)  # Remove initial stop

                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Partial exit",
                                "message": f"Exited {partial_size} shares at 1R profit. Moving stop to breakeven.",
                            }
                        )

                        # Adjust stop to break-even
                        new_stop_price = entry_price
                        stop_action = "SELL" if direction == "long" else "BUY"
                        break_even_stop = StopOrder(
                            stop_action, share_size - partial_size, new_stop_price
                        )
                        ib.placeOrder(stock, break_even_stop)

                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Stop moved",
                                "message": f"Breakeven stop placed at {new_stop_price}",
                                "new_stop": new_stop_price,
                            }
                        )

                        remaining_shares -= partial_size
                        first_partial = True

                    # Second partial take profit
                    if (
                        first_partial
                        and not second_partial
                        and (
                            (
                                current_price >= partial2_target
                                if direction == "long"
                                else current_price <= partial2_target
                            )
                        )
                    ):
                        logger.info("Second partial take profit target hit.")
                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Target 2 hit",
                                "message": f"Second partial target hit: {partial2_target}",
                            }
                        )

                        # Take another partial of partial_size shares
                        partial_action = "SELL" if direction == "long" else "BUY"
                        partial_order2 = MarketOrder(partial_action, partial_size)
                        ib.placeOrder(stock, partial_order2)

                        if break_even_stop:
                            ib.cancelOrder(break_even_stop)  # Remove break-even stop

                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Partial exit",
                                "message": f"Exited {partial_size} shares at 2R profit. Setting trailing stop for remainder.",
                            }
                        )

                        # Set trailing stop for remaining shares
                        trail_amount = R / 2  # Set trailing amount to half of R
                        trailing_action = "SELL" if direction == "long" else "BUY"
                        trailing_stop_order = await create_trailing_stop_order(
                            trailing_action,
                            remaining_shares - partial_size,
                            trail_amount,
                        )
                        ib.placeOrder(stock, trailing_stop_order)

                        await ws.send_json(
                            {
                                "type": "3r_trade_update",
                                "status": "Trailing stop",
                                "message": f"Trailing stop set with {trail_amount} distance for remaining {remaining_shares - partial_size} shares",
                            }
                        )

                        remaining_shares -= partial_size
                        second_partial = True

            except Exception as e:
                logger.error(f"Error getting price data: {e}")

            # Sleep before next check
            await asyncio.sleep(5)

        # If we exit the loop normally, the trade is still open with trailing stops
        await ws.send_json(
            {
                "type": "3r_trade_update",
                "status": "Monitoring complete",
                "message": f"Automatic monitoring period complete. Trade has appropriate stops in place.",
            }
        )

    except Exception as e:
        logger.error(f"Error managing 3R trade: {e}")
        await ws.send_json(
            {"type": "error", "message": f"Error in trade management: {e}"}
        )


# Import additional modules needed for alerting
import threading
import datetime

# Dictionary to store active alert configurations
active_alerts = {}
alert_task = None


async def start_price_alerts(ws, alert_config):
    """
    Start monitoring price alerts for the provided symbols
    """
    try:
        symbols = alert_config.get("symbols", [])

        if not symbols:
            await ws.send_json(
                {"type": "error", "message": "No symbols provided for alerting"}
            )
            return False

        # Register this websocket for alerts
        client_id = id(ws)
        active_alerts[client_id] = {
            "ws": ws,
            "symbols": symbols,
            "last_alert_time": {},  # Track when we last sent an alert for each symbol
            "reference_data": {},  # Store reference data like VWAP, prev close
        }

        # Get reference data for each symbol
        await initialize_reference_data(client_id, symbols)

        logger.info(
            f"Started price alerting for client {client_id} with {len(symbols)} symbols"
        )

        # Start the alerting background task if not already running
        global alert_task
        if alert_task is None or alert_task.done():
            alert_task = asyncio.create_task(price_alert_monitor())

        return True

    except Exception as e:
        logger.error(f"Error starting price alerts: {e}")
        await ws.send_json({"type": "error", "message": f"Failed to start alerts: {e}"})
        return False


async def stop_price_alerts(ws):
    """
    Stop monitoring price alerts for this client
    """
    try:
        client_id = id(ws)
        if client_id in active_alerts:
            del active_alerts[client_id]
            logger.info(f"Stopped price alerting for client {client_id}")

            # If no more clients are using alerts, cancel the background task
            if not active_alerts and alert_task and not alert_task.done():
                alert_task.cancel()

        return True

    except Exception as e:
        logger.error(f"Error stopping price alerts: {e}")
        return False


async def initialize_reference_data(client_id, symbols):
    """
    Get initial reference data for each monitored symbol
    """
    if client_id not in active_alerts:
        return

    client_data = active_alerts[client_id]
    ws = client_data["ws"]

    for symbol_data in symbols:
        symbol = symbol_data["symbol"]

        # Create a contract for this symbol
        contract = Stock(symbol, "SMART", "USD")

        # Store reference info
        ref_data = {}

        # Get previous day's close if needed
        if symbol_data.get("prevClose", False):
            try:
                # Request 1-day bar for yesterday
                now = datetime.datetime.now()
                yesterday = now - datetime.timedelta(days=1)
                yesterday_str = yesterday.strftime("%Y%m%d %H:%M:%S")

                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime=yesterday_str,
                    durationStr="1 D",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                )

                if bars and len(bars) > 0:
                    ref_data["prev_close"] = bars[0].close
                    logger.info(
                        f"Previous close for {symbol}: {ref_data['prev_close']}"
                    )

                    # Send confirmation to client
                    await ws.send_json(
                        {
                            "type": "alert",
                            "alertType": "info",
                            "message": f"Loaded previous close for {symbol}: ${ref_data['prev_close']:.2f}",
                        }
                    )
            except Exception as e:
                logger.error(f"Error getting previous close for {symbol}: {e}")

        # Get VWAP if needed
        if symbol_data.get("vwap", False):
            try:
                # Use today's data to calculate VWAP
                now = datetime.datetime.now()
                today_str = now.strftime("%Y%m%d %H:%M:%S")

                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime=today_str,
                    durationStr="1 D",
                    barSizeSetting="5 mins",
                    whatToShow="TRADES",
                    useRTH=True,
                )

                if bars and len(bars) > 0:
                    # Calculate VWAP: Σ(Price * Volume) / Σ(Volume)
                    total_volume = sum(bar.volume for bar in bars)

                    if total_volume > 0:
                        vwap = (
                            sum(
                                (bar.wap if not math.isnan(bar.wap) else bar.close)
                                * bar.volume
                                for bar in bars
                            )
                            / total_volume
                        )
                        ref_data["vwap"] = vwap
                        logger.info(f"VWAP for {symbol}: {vwap}")

                        # Send confirmation to client
                        await ws.send_json(
                            {
                                "type": "alert",
                                "alertType": "info",
                                "message": f"Calculated VWAP for {symbol}: ${vwap:.2f}",
                            }
                        )
            except Exception as e:
                logger.error(f"Error calculating VWAP for {symbol}: {e}")

        # Store the reference data
        client_data["reference_data"][symbol] = ref_data

    # Update the active_alerts dictionary
    active_alerts[client_id] = client_data


async def price_alert_monitor():
    """
    Background task to monitor prices and send alerts
    """
    try:
        logger.info("Starting price alert monitoring task")

        # Create a throttling mechanism to not spam alerts
        # We'll only send one alert per symbol every 5 minutes
        ALERT_THROTTLE_SECONDS = 300  # 5 minutes
        PRICE_CHECK_INTERVAL = 10  # Check prices every 10 seconds
        THRESHOLD_PERCENTAGE = 0.005  # 0.5% threshold for proximity alerts

        while True:
            # Exit if no clients are monitoring
            if not active_alerts:
                logger.info("No active alert clients, stopping monitoring task")
                break

            # Process each client
            client_ids = list(active_alerts.keys())

            for client_id in client_ids:
                # Skip if client was removed
                if client_id not in active_alerts:
                    continue

                client_data = active_alerts[client_id]
                ws = client_data["ws"]

                # Skip if websocket is closed
                if ws.closed:
                    logger.info(
                        f"WebSocket closed for client {client_id}, removing alerts"
                    )
                    if client_id in active_alerts:
                        del active_alerts[client_id]
                    continue

                # Check each symbol
                for symbol_data in client_data["symbols"]:
                    if not symbol_data.get("active", True):
                        continue

                    symbol = symbol_data["symbol"]
                    last_alert_times = client_data["last_alert_time"]
                    now = time.time()

                    # Throttle alerts
                    if (
                        symbol in last_alert_times
                        and (now - last_alert_times[symbol]) < ALERT_THROTTLE_SECONDS
                    ):
                        continue

                    # Get current price
                    contract = Stock(symbol, "SMART", "USD")

                    try:
                        # Request market data
                        market_data = ib.reqMktData(contract)
                        await asyncio.sleep(0.5)  # Wait for data to populate

                        # Use last price or similar if available
                        current_price = None
                        if market_data.last and not math.isnan(market_data.last):
                            current_price = market_data.last
                        elif market_data.close and not math.isnan(market_data.close):
                            current_price = market_data.close
                        elif market_data.marketPrice and not math.isnan(
                            market_data.marketPrice
                        ):
                            current_price = market_data.marketPrice

                        # Cancel market data to avoid memory leaks
                        ib.cancelMktData(contract)

                        if current_price is None:
                            continue

                        # Get reference data
                        ref_data = client_data["reference_data"].get(symbol, {})

                        # Check previous close proximity
                        if (
                            symbol_data.get("prevClose", False)
                            and "prev_close" in ref_data
                        ):
                            prev_close = ref_data["prev_close"]

                            # Calculate percentage difference
                            pct_diff = abs(current_price - prev_close) / prev_close

                            if pct_diff <= THRESHOLD_PERCENTAGE:
                                # Send alert
                                await ws.send_json(
                                    {
                                        "type": "alert",
                                        "alertType": "prevClose",
                                        "message": f"Warning: {symbol} is approaching Previous Day Close (${prev_close:.2f})! Current: ${current_price:.2f}",
                                    }
                                )

                                # Update last alert time
                                last_alert_times[symbol] = now
                                client_data["last_alert_time"] = last_alert_times
                                active_alerts[client_id] = client_data
                                break  # Only send one alert per symbol at a time

                        # Check VWAP proximity
                        if symbol_data.get("vwap", False) and "vwap" in ref_data:
                            vwap = ref_data["vwap"]

                            # Calculate percentage difference
                            pct_diff = abs(current_price - vwap) / vwap

                            if pct_diff <= THRESHOLD_PERCENTAGE:
                                # Send alert
                                await ws.send_json(
                                    {
                                        "type": "alert",
                                        "alertType": "vwap",
                                        "message": f"Warning: {symbol} is approaching VWAP (${vwap:.2f})! Current: ${current_price:.2f}",
                                    }
                                )

                                # Update last alert time
                                last_alert_times[symbol] = now
                                client_data["last_alert_time"] = last_alert_times
                                active_alerts[client_id] = client_data
                                break  # Only send one alert per symbol at a time

                    except Exception as e:
                        logger.error(f"Error checking price for {symbol}: {e}")

            # Wait before next check
            await asyncio.sleep(PRICE_CHECK_INTERVAL)

    except asyncio.CancelledError:
        logger.info("Price alert monitoring task was cancelled")
    except Exception as e:
        logger.error(f"Error in price alert monitoring task: {e}")


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Add this client to our set of connected clients
    connected_clients.add(ws)
    logger.info(f"Client connected. Total clients: {len(connected_clients)}")

    # Ensure IB is connected
    if not await connect_ib_with_retry():
        # Send connection error message to client
        await ws.send_json(
            {
                "type": "error",
                "message": "Failed to connect to Interactive Brokers. Please check that TWS/Gateway is running.",
            }
        )

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    logger.info(f"Received message: {data}")

                    # Check if we're still connected
                    if not ib.isConnected():
                        logger.warning("IB connection lost, attempting to reconnect...")
                        if not await connect_ib_with_retry():
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "message": "Lost connection to Interactive Brokers and failed to reconnect.",
                                }
                            )
                            continue

                    if data["type"] == "market_data":
                        symbol = data["symbol"]
                        await send_market_data(ws, symbol)

                    elif data["type"] == "trade":
                        symbol = data["symbol"]
                        direction = data["direction"]
                        quantity = int(data["quantity"])
                        tradeType = data.get("tradeType", "standard")

                        if tradeType == "standard":
                            await execute_trade(ws, symbol, direction, quantity)
                        elif tradeType == "3r_volatility":
                            timeframe = int(data.get("timeframe", 5))
                            lookback = int(data.get("lookback", 20))
                            await enter_3r_trade(
                                ws, symbol, direction, quantity, timeframe, lookback
                            )

                    elif data["type"] == "positions":
                        await send_positions(ws)

                    elif data["type"] == "connection_test":
                        # Simple endpoint to test if IB is connected
                        if ib.isConnected():
                            await ws.send_json(
                                {"type": "connection_test", "status": "connected"}
                            )
                        else:
                            await ws.send_json(
                                {"type": "connection_test", "status": "disconnected"}
                            )

                    # New handlers for alerting functionality
                    elif data["type"] == "start_alerting":
                        symbols = data.get("symbols", [])
                        await start_price_alerts(ws, {"symbols": symbols})

                    elif data["type"] == "stop_alerting":
                        await stop_price_alerts(ws)

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await ws.send_json({"type": "error", "message": str(e)})

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(
                    f"WebSocket connection closed with exception {ws.exception()}"
                )

    finally:
        # Clean up any active alerts for this client
        await stop_price_alerts(ws)

        # Remove this client from connected clients
        connected_clients.remove(ws)
        logger.info(f"Client disconnected. Remaining clients: {len(connected_clients)}")

    return ws


async def send_market_data(ws, symbol):
    try:
        stock = Stock(symbol, "SMART", "USD")

        # Cancel previous market data subscription if exists
        # contracts_to_cancel = []
        # for contract in ib.reqMktDataList():
        #     if contract.symbol == symbol:
        #         contracts_to_cancel.append(contract)

        # for contract in contracts_to_cancel:
        #     ib.cancelMktData(contract)

        # Request market data with error handling
        try:
            market_data = ib.reqMktData(stock)
        except Exception as e:
            logger.error(f"Failed to request market data: {e}")
            await ws.send_json(
                {
                    "type": "market_data",
                    "symbol": symbol,
                    "price": "Error requesting data",
                }
            )
            return

        # Wait for data to be populated (with timeout)
        timeout = 5  # seconds
        price = None

        # Use a non-blocking approach to wait for data
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if market_data.last is not None and not math.isnan(market_data.last):
                price = market_data.last
                break
            await asyncio.sleep(0.1)

        # If we didn't get a last price, try marketPrice as fallback
        if (
            price is None
            and market_data.marketPrice is not None
            and not math.isnan(market_data.marketPrice)
        ):
            price = market_data.marketPrice

        # If still no price, try bid/ask midpoint
        if (
            price is None
            and market_data.bid is not None
            and market_data.ask is not None
        ):
            if not math.isnan(market_data.bid) and not math.isnan(market_data.ask):
                price = (market_data.bid + market_data.ask) / 2

        # Send the data
        await ws.send_json(
            {
                "type": "market_data",
                "symbol": symbol,
                "price": price if price is not None else "No Data",
            }
        )

    except Exception as e:
        logger.error(f"Error sending market data: {e}")
        await ws.send_json({"type": "error", "message": str(e)})


async def execute_trade(ws, symbol, direction, quantity):
    try:
        stock = Stock(symbol, "SMART", "USD")
        order_type = "BUY" if direction == "long" else "SELL"
        order = MarketOrder(order_type, quantity)

        # Place the order
        try:
            trade = ib.placeOrder(stock, order)
            logger.info(f"Order placed: {order_type} {quantity} {symbol}")

            # Send confirmation
            await ws.send_json(
                {"type": "trade_update", "symbol": symbol, "status": "Order Placed"}
            )

            # Wait for order status updates
            timeout = 5  # seconds
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                ib.waitOnUpdate(timeout=0.2)
                if trade.orderStatus.status:
                    await ws.send_json(
                        {
                            "type": "trade_update",
                            "symbol": symbol,
                            "status": trade.orderStatus.status,
                        }
                    )
                    break
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            await ws.send_json(
                {"type": "error", "message": f"Failed to place order: {e}"}
            )

    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        await ws.send_json({"type": "error", "message": str(e)})


async def send_positions(ws):
    try:
        # Make sure we're connected before trying to get portfolio
        if not ib.isConnected():
            await ws.send_json(
                {"type": "error", "message": "Not connected to Interactive Brokers"}
            )
            return

        # Get portfolio data
        try:
            portfolio = ib.portfolio()

            positions = [
                {
                    "symbol": pos.contract.symbol,
                    "quantity": pos.position,
                    "price": pos.marketPrice if not math.isnan(pos.marketPrice) else 0,
                    "marketValue": (
                        pos.marketValue if not math.isnan(pos.marketValue) else 0
                    ),
                    "averageCost": (
                        pos.averageCost if not math.isnan(pos.averageCost) else 0
                    ),
                    "unrealizedPNL": (
                        pos.unrealizedPNL if not math.isnan(pos.unrealizedPNL) else 0
                    ),
                }
                for pos in portfolio
            ]

            # Send positions data
            await ws.send_json({"type": "positions", "positions": positions})

        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            await ws.send_json(
                {"type": "error", "message": f"Failed to get portfolio: {e}"}
            )

    except Exception as e:
        logger.error(f"Error sending positions: {e}")
        await ws.send_json({"type": "error", "message": str(e)})


async def start_background_tasks(app):
    """Background task to keep connection alive"""
    try:
        # Initialize connection
        if not await connect_ib_with_retry():
            logger.error(
                "Failed to establish initial connection to Interactive Brokers"
            )
            # We'll continue running to allow retry attempts later
    except Exception as e:
        logger.error(f"Error in startup: {e}")


async def cleanup_background_tasks(app):
    """Cleanup task to disconnect properly"""
    try:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from Interactive Brokers")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def main():
    # Initialize the aiohttp web application
    app = web.Application()

    # Add WebSocket route
    app.router.add_get("/ws", websocket_handler)

    # Add startup and cleanup handlers
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)

    # Run the server
    logger.info("Starting WebSocket server on http://0.0.0.0:8765/ws")
    try:
        web.run_app(app, host="0.0.0.0", port=8765)
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Ensure IB is disconnected
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from Interactive Brokers")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
