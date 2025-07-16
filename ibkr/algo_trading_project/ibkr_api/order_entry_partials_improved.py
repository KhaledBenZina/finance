from ib_insync import *
import time
import logging
import math
import statistics

# Connect to TWS API
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Global configuration for testing
TEST_MODE = True  # Set to True for faster testing
TEST_RISK_PCT = 0.001  # 0.1% risk for very tight targets in test mode


# Calculate dynamic risk based on ATR (Average True Range)
def calculate_dynamic_risk(stock, atr_period=14):
    """
    Calculate dynamic risk based on ATR
    """
    # Get historical data
    bars = ib.reqHistoricalData(
        stock,
        endDateTime="",
        durationStr="5 D",
        barSizeSetting="15 mins",
        whatToShow="TRADES",
        useRTH=True,
    )

    # Calculate ATR
    if len(bars) > atr_period:
        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close

            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)

            true_range = max(tr1, tr2, tr3)
            true_ranges.append(true_range)

        atr = statistics.mean(true_ranges[-atr_period:])
        # Return ATR adjusted value (you can tune this multiplier)
        return round(atr * 0.5, 2)
    else:
        # Default if not enough data
        return 0.5


def create_trailing_stop_order(action, quantity, trail_amount):
    """
    Creates a trailing stop order manually.
    """
    trailing_stop_order = Order(
        action=action,
        orderType="TRAIL",
        totalQuantity=quantity,
        auxPrice=trail_amount,  # This sets the trailing amount
        tif="GTC",  # Good Till Cancelled
    )
    return trailing_stop_order


def enter_trade(stock, direction, share_size, test_mode=False, test_risk_pct=0.01):
    logging.info(f"Entering {direction} trade...")

    if test_mode:
        # In test mode, use a very small risk amount (e.g., 1% of price)
        # to make partial profit targets trigger faster
        ticker = ib.reqTickers(stock)[0]
        current_price = (
            ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
        )
        risk_amount = round(
            current_price * test_risk_pct, 2
        )  # Small percentage of price
        logging.info(f"TEST MODE: Using small risk amount: {risk_amount}")
    else:
        # Normal operation - calculate dynamic risk based on ATR
        risk_amount = calculate_dynamic_risk(stock)
        logging.info(f"Dynamic risk calculated: {risk_amount}")

    # Place initial market order for share_size shares
    initial_action = "BUY" if direction == "long" else "SELL"
    initial_order = MarketOrder(initial_action, share_size)
    trade = ib.placeOrder(stock, initial_order)
    ib.sleep(2)  # Wait for the order to fill

    if trade.orderStatus.status != "Filled":
        logging.warning("Order not filled within timeout period")
        return None, None, None, None

    entry_price = trade.orderStatus.avgFillPrice
    logging.info(f"Initial order filled at {entry_price}")

    # Set initial stop loss
    stop_price = (
        entry_price - risk_amount if direction == "long" else entry_price + risk_amount
    )
    stop_action = "SELL" if direction == "long" else "BUY"
    stop_loss_order = StopOrder(stop_action, share_size, stop_price)
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop loss order placed at {stop_price}")

    return trade, entry_price, stop_loss_order, risk_amount


def get_price_distance(current_price, target_price, direction="long"):
    """Calculate how far price is from target (in percent and ticks)"""
    if current_price == 0 or target_price == 0:
        return "N/A", "N/A"

    # For long trades, targets are above entry, stops below
    if direction == "long":
        distance = target_price - current_price
    # For short trades, targets are below entry, stops above
    else:
        distance = current_price - target_price

    # Calculate percentage
    pct_distance = (abs(distance) / current_price) * 100

    # Approximate ticks (assuming $0.01 tick size, adjust if needed)
    ticks_distance = abs(distance) * 100

    return f"{pct_distance:.2f}%", f"{ticks_distance:.0f} ticks"


def display_trade_status(
    current_price,
    entry_price,
    stop_price,
    partial1_target,
    partial2_target,
    direction,
    remaining_shares,
    trade_stage,
    partial3_target=None,
):
    """Display comprehensive trade status"""
    # Calculate P&L
    if direction == "long":
        points_pnl = current_price - entry_price
        pct_pnl = (points_pnl / entry_price) * 100
    else:  # short
        points_pnl = entry_price - current_price
        pct_pnl = (points_pnl / entry_price) * 100

    # Calculate dollar P&L
    dollar_pnl = points_pnl * remaining_shares

    # Format P&L with colors (+ for green, - for red)
    pnl_sign = "+" if points_pnl >= 0 else ""

    # Calculate distances to targets and stop
    if trade_stage == "Initial":
        tp1_pct, tp1_ticks = get_price_distance(
            current_price, partial1_target, direction
        )
        tp2_pct, tp2_ticks = get_price_distance(
            current_price, partial2_target, direction
        )
        tp3_pct, tp3_ticks = (
            get_price_distance(current_price, partial3_target or 0, direction)
            if partial3_target
            else ("N/A", "N/A")
        )
        sl_pct, sl_ticks = get_price_distance(current_price, stop_price, direction)

        status_str = f"""
╔════════════════ TRADE STATUS ════════════════╗
║ Symbol: {stock.symbol:<7}  Direction: {direction.upper():<5}  Shares: {remaining_shares:<4} ║
║ Stage: {trade_stage:<7}                              ║
╠═══════════════════════════════════════════════╣
║ Entry: {entry_price:<7.2f}    Current: {current_price:<7.2f}           ║
║ P&L:   {pnl_sign}{points_pnl:<+7.2f} pts ({pnl_sign}{pct_pnl:.2f}%)              ║
║ P&L:   ${pnl_sign}{dollar_pnl:.2f} (approx. {remaining_shares} shares)       ║
╠═══════════════════════════════════════════════╣
║ Stop Loss @ {stop_price:<7.2f}  Distance: {sl_pct} ({sl_ticks})  ║
║ Target 1 @ {partial1_target:<7.2f}  Distance: {tp1_pct} ({tp1_ticks})  ║
║ Target 2 @ {partial2_target:<7.2f}  Distance: {tp2_pct} ({tp2_ticks})  ║
"""
        # Add third target if present
        if partial3_target:
            status_str += f"║ Target 3 @ {partial3_target:<7.2f}  Distance: {tp3_pct} ({tp3_ticks})  ║\n"

        status_str += "╚═══════════════════════════════════════════════╝\n"

    elif trade_stage == "Partial1":
        tp2_pct, tp2_ticks = get_price_distance(
            current_price, partial2_target, direction
        )
        tp3_pct, tp3_ticks = (
            get_price_distance(current_price, partial3_target or 0, direction)
            if partial3_target
            else ("N/A", "N/A")
        )
        sl_pct, sl_ticks = get_price_distance(current_price, stop_price, direction)

        status_str = f"""
╔════════════════ TRADE STATUS ════════════════╗
║ Symbol: {stock.symbol:<7}  Direction: {direction.upper():<5}  Shares: {remaining_shares:<4} ║
║ Stage: {trade_stage:<7}                              ║
╠═══════════════════════════════════════════════╣
║ Entry: {entry_price:<7.2f}    Current: {current_price:<7.2f}           ║
║ P&L:   {pnl_sign}{points_pnl:<+7.2f} pts ({pnl_sign}{pct_pnl:.2f}%)              ║
║ P&L:   ${pnl_sign}{dollar_pnl:.2f} (approx. {remaining_shares} shares)       ║
╠═══════════════════════════════════════════════╣
║ Break-Even @ {stop_price:<7.2f}  Distance: {sl_pct} ({sl_ticks})  ║
║ Target 2 @ {partial2_target:<7.2f}  Distance: {tp2_pct} ({tp2_ticks})  ║
"""
        # Add third target if present
        if partial3_target:
            status_str += f"║ Target 3 @ {partial3_target:<7.2f}  Distance: {tp3_pct} ({tp3_ticks})  ║\n"

        status_str += "║ Target 1: ✓ FILLED                             ║\n"
        status_str += "╚═══════════════════════════════════════════════╝\n"

    elif trade_stage == "Partial2":
        if partial3_target:
            tp3_pct, tp3_ticks = get_price_distance(
                current_price, partial3_target, direction
            )
            sl_pct, sl_ticks = get_price_distance(current_price, stop_price, direction)

            status_str = f"""
╔════════════════ TRADE STATUS ════════════════╗
║ Symbol: {stock.symbol:<7}  Direction: {direction.upper():<5}  Shares: {remaining_shares:<4} ║
║ Stage: {trade_stage:<7}                              ║
╠═══════════════════════════════════════════════╣
║ Entry: {entry_price:<7.2f}    Current: {current_price:<7.2f}           ║
║ P&L:   {pnl_sign}{points_pnl:<+7.2f} pts ({pnl_sign}{pct_pnl:.2f}%)              ║
║ P&L:   ${pnl_sign}{dollar_pnl:.2f} (approx. {remaining_shares} shares)       ║
╠═══════════════════════════════════════════════╣
║ Profit Lock Stop @ {stop_price:<7.2f}  Distance: {sl_pct}   ║
║ Target 3 @ {partial3_target:<7.2f}  Distance: {tp3_pct} ({tp3_ticks})  ║
║ Target 1: ✓ FILLED                             ║
║ Target 2: ✓ FILLED                             ║
╚═══════════════════════════════════════════════╝
"""
        else:
            # If no third target, show trailing stop info
            status_str = f"""
╔════════════════ TRADE STATUS ════════════════╗
║ Symbol: {stock.symbol:<7}  Direction: {direction.upper():<5}  Shares: {remaining_shares:<4} ║
║ Stage: {trade_stage:<7}                              ║
╠═══════════════════════════════════════════════╣
║ Entry: {entry_price:<7.2f}    Current: {current_price:<7.2f}           ║
║ P&L:   {pnl_sign}{points_pnl:<+7.2f} pts ({pnl_sign}{pct_pnl:.2f}%)              ║
║ P&L:   ${pnl_sign}{dollar_pnl:.2f} (approx. {remaining_shares} shares)       ║
╠═══════════════════════════════════════════════╣
║ Trailing Stop: ${stop_price} trail amount           ║
║ Target 1: ✓ FILLED                             ║
║ Target 2: ✓ FILLED                             ║
╚═══════════════════════════════════════════════╝
"""
    elif trade_stage == "Complete":
        status_str = f"""
╔════════════════ TRADE STATUS ════════════════╗
║ Symbol: {stock.symbol:<7}  Direction: {direction.upper():<5}  Shares: {remaining_shares:<4} ║
║ Stage: {trade_stage:<7}                              ║
╠═══════════════════════════════════════════════╣
║ Entry: {entry_price:<7.2f}    Current: {current_price:<7.2f}           ║
║ P&L:   {pnl_sign}{points_pnl:<+7.2f} pts ({pnl_sign}{pct_pnl:.2f}%)              ║
╠═══════════════════════════════════════════════╣
║ Target 1: ✓ FILLED                             ║
║ Target 2: ✓ FILLED                             ║
║ Target 3: ✓ FILLED                             ║
║ TRADE COMPLETED                                 ║
╚═══════════════════════════════════════════════╝
"""

    # Fix the display to ensure right borders align correctly
    fixed_lines = []
    for line in status_str.split("\n"):
        if "║" in line:
            # Ensure line is exactly 49 characters wide (including borders)
            content = line.strip()
            if len(content) < 49:
                padding = " " * (49 - len(content))
                # Find the last '║' and replace it with '║' + padding
                last_idx = content.rfind("║")
                if last_idx != -1:
                    content = content[:last_idx] + padding + "║"
            fixed_lines.append(content)
        else:
            fixed_lines.append(line)

    fixed_status = "\n".join(fixed_lines)
    logging.info(f"\n{fixed_status}")
    return


def manage_trade(
    entry_price, trade, stop_loss_order, direction, share_size, risk_amount, stock
):
    logging.info(f"Managing {direction} trade...")

    # Set profit targets using the dynamic risk amount
    partial1_target = (
        entry_price + (1.5 * risk_amount)
        if direction == "long"
        else entry_price - (1.5 * risk_amount)
    )
    partial2_target = (
        entry_price + (3 * risk_amount)
        if direction == "long"
        else entry_price - (3 * risk_amount)
    )
    partial3_target = (
        entry_price + (5 * risk_amount)
        if direction == "long"
        else entry_price - (5 * risk_amount)
    )

    logging.info(
        f"Profit targets - First: {partial1_target}, Second: {partial2_target}, Third: {partial3_target}"
    )

    # Initial position setup
    remaining_shares = share_size
    first_partial = False
    second_partial = False
    partial_size = math.ceil(share_size / 3)  # Divide into three equal parts

    # Current stop price (initially)
    current_stop_price = (
        entry_price - risk_amount if direction == "long" else entry_price + risk_amount
    )

    # Trade stage tracking
    trade_stage = "Initial"

    # Display counter
    display_counter = 0

    # For testing purposes - record starting time to simulate price movement
    start_time = time.time()

    # Flag to check if trade was manually modified by user
    manual_modification_check_time = time.time()

    # Main trade management loop
    while remaining_shares > 0:
        # Check portfolio for current position
        portfolio = ib.portfolio()
        position_exists = False
        actual_position_size = 0

        for item in portfolio:
            if item.contract.symbol == stock.symbol:
                position_exists = True
                # For long positions, we want positive size
                if direction == "long":
                    actual_position_size = max(0, int(item.position))
                # For short positions, we want the absolute value of negative size
                else:
                    actual_position_size = abs(min(0, int(item.position)))

                if actual_position_size == 0:
                    logging.info("Position is 0. Exiting trade management.")
                    return  # Exit the function if the position is 0

                # Check if position was manually modified (every 10 seconds)
                if time.time() - manual_modification_check_time > 10:
                    if actual_position_size != remaining_shares:
                        logging.info(
                            f"Position size changed from {remaining_shares} to {actual_position_size} - likely manual modification"
                        )
                        remaining_shares = actual_position_size
                    manual_modification_check_time = time.time()

        if not position_exists:
            logging.info("Position not found in portfolio. Exiting trade management.")
            return

        # Get latest price
        ticker = ib.reqTickers(stock)[0]
        current_price = (
            ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
        )

        # TEST MODE: Simulate price movement to trigger take profit orders faster
        elapsed_seconds = time.time() - start_time

        if TEST_MODE:
            # After 5 seconds, trigger first partial
            if elapsed_seconds > 5 and not first_partial:
                logging.info(
                    "TEST MODE: Simulating price movement to trigger first partial"
                )
                if direction == "long":
                    current_price = partial1_target + 0.01  # Just above target
                else:
                    current_price = partial1_target - 0.01  # Just below target

            # After 10 seconds, trigger second partial
            elif elapsed_seconds > 10 and first_partial and not second_partial:
                logging.info(
                    "TEST MODE: Simulating price movement to trigger second partial"
                )
                if direction == "long":
                    current_price = partial2_target + 0.01  # Just above target
                else:
                    current_price = partial2_target - 0.01  # Just below target

            # After 15 seconds, trigger third partial or trailing stop
            elif elapsed_seconds > 15 and second_partial:
                logging.info(
                    "TEST MODE: Simulating price movement to trigger third target"
                )
                if direction == "long":
                    current_price = partial3_target + 0.01  # Just above target
                else:
                    current_price = partial3_target - 0.01  # Just below target

            # After 20 seconds, simulate stop loss if still have shares
            elif elapsed_seconds > 20 and remaining_shares > 0:
                logging.info(
                    "TEST MODE: Simulating price movement to trigger trailing stop"
                )
                if direction == "long":
                    current_price = entry_price - (2 * risk_amount)  # Below stop
                else:
                    current_price = entry_price + (2 * risk_amount)  # Above stop

        # Display status periodically
        display_counter += 1
        if display_counter >= 5:
            # Update display to include third target if needed
            display_trade_status(
                current_price,
                entry_price,
                current_stop_price,
                partial1_target,
                partial2_target,
                direction,
                remaining_shares,
                trade_stage,
                partial3_target,
            )
            display_counter = 0

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
                stop_action, remaining_shares - partial_size, new_stop_price
            )
            ib.placeOrder(stock, break_even_stop)
            logging.info(f"Break-even stop loss order placed at {new_stop_price}")

            # Update state
            remaining_shares -= partial_size
            first_partial = True  # Ensure first partial is only taken once
            stop_loss_order = break_even_stop  # Update the current stop reference
            current_stop_price = new_stop_price  # Update for status display
            trade_stage = "Partial1"  # Update stage for display purposes

            # Wait for partial to fill and verify position size
            ib.sleep(2)
            for item in portfolio:
                if item.contract.symbol == stock.symbol:
                    actual_size = (
                        abs(item.position) if direction == "short" else item.position
                    )
                    if actual_size != remaining_shares:
                        logging.info(
                            f"Position size after first partial: {actual_size}, expected {remaining_shares}"
                        )
                        remaining_shares = actual_size

        # Second partial take profit
        elif (
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
            logging.info("Second partial take profit target hit.")
            # Take another partial of partial_size shares
            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order2 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order2)
            ib.cancelOrder(stop_loss_order)  # Remove break-even stop
            logging.info(
                f"Partial order of {partial_size} shares placed and break-even stop loss canceled."
            )

            # Set tighter stop for remaining shares - move stop to entry + 1R for long or entry - 1R for short
            new_stop_price = (
                entry_price + risk_amount
                if direction == "long"
                else entry_price - risk_amount
            )
            stop_action = "SELL" if direction == "long" else "BUY"
            profit_lock_stop = StopOrder(
                stop_action, remaining_shares - partial_size, new_stop_price
            )
            ib.placeOrder(stock, profit_lock_stop)
            logging.info(
                f"Profit-lock stop order placed at {new_stop_price} for remaining {remaining_shares - partial_size} shares."
            )

            # Update state
            remaining_shares -= partial_size
            second_partial = True  # Mark second partial as complete
            stop_loss_order = profit_lock_stop  # Update the current stop reference
            current_stop_price = new_stop_price  # Update for status display
            trade_stage = "Partial2"  # Update stage for display purposes

            # Wait for partial to fill and verify position size
            ib.sleep(2)
            for item in portfolio:
                if item.contract.symbol == stock.symbol:
                    actual_size = (
                        abs(item.position) if direction == "short" else item.position
                    )
                    if actual_size != remaining_shares:
                        logging.info(
                            f"Position size after second partial: {actual_size}, expected {remaining_shares}"
                        )
                        remaining_shares = actual_size

        # Third partial take profit - let the remaining shares run to the final target
        elif second_partial and (
            (
                current_price >= partial3_target
                if direction == "long"
                else current_price <= partial3_target
            )
        ):
            logging.info("Third/Final target hit.")
            # Take the final portion
            partial_action = "SELL" if direction == "long" else "BUY"
            final_order = MarketOrder(partial_action, remaining_shares)
            ib.placeOrder(stock, final_order)
            ib.cancelOrder(stop_loss_order)  # Remove the profit-lock stop
            logging.info(
                f"Final order of {remaining_shares} shares placed. Exiting trade completely."
            )

            # Update state
            remaining_shares = 0
            trade_stage = "Complete"

        # Check for stop loss
        if (current_price <= current_stop_price and direction == "long") or (
            current_price >= current_stop_price and direction == "short"
        ):
            logging.info(f"Stop loss at {current_stop_price} likely triggered.")

            # Verify that position is actually closed by checking portfolio
            ib.sleep(1)  # Wait a moment for the order to process
            portfolio = ib.portfolio()
            position_closed = True

            for item in portfolio:
                if item.contract.symbol == stock.symbol:
                    if (direction == "long" and item.position > 0) or (
                        direction == "short" and item.position < 0
                    ):
                        position_closed = False
                        logging.info(
                            f"Position still open after stop hit: {item.position} shares remaining"
                        )
                        remaining_shares = abs(item.position)
                        break

            if position_closed:
                logging.info(
                    "Position verified as closed - stop loss executed successfully"
                )
                remaining_shares = 0
            else:
                # Force close the position if stop didn't trigger but should have
                logging.warning(
                    "Stop loss should have triggered but position still open - forcing close"
                )
                close_action = "SELL" if direction == "long" else "BUY"
                close_order = MarketOrder(close_action, remaining_shares)
                ib.placeOrder(stock, close_order)
                logging.info(
                    f"Emergency close order placed for remaining {remaining_shares} shares"
                )
                ib.sleep(2)  # Wait for the emergency close to execute
                remaining_shares = 0

            break

        # Break if all shares are gone
        if remaining_shares <= 0:
            logging.info("All shares have been sold/bought back.")
            break

        # Sleep to reduce API calls
        ib.sleep(1)

    logging.info("Trade management complete.")


# Main execution
if __name__ == "__main__":
    try:
        # Test mode settings
        TEST_MODE = False  # Set to True for faster testing
        TEST_RISK_PCT = 0.01  # 0.1% risk for very tight targets in test mode

        direction = "long"  # Change to 'long' or 'short' based on the desired trade
        share_size = 100  # Define the initial share size
        # Define contract for the stock (e.g., NVDA)
        stock = Stock("AMD", "SMART", "USD")

        # Make sure we're connected
        if not ib.isConnected():
            ib.connect("127.0.0.1", 7497, clientId=1)

        trade, entry_price, stop_loss_order, risk_amount = enter_trade(
            stock, direction, share_size, TEST_MODE, TEST_RISK_PCT
        )

        if trade and entry_price and stop_loss_order:
            # Display trade information before management starts
            logging.info(
                f"Trade entered at {entry_price} with risk amount of {risk_amount}"
            )
            logging.info(
                f"Initial stop loss at {entry_price - risk_amount if direction == 'long' else entry_price + risk_amount}"
            )

            # Targets for a 3-part strategy with the first target at 1.5R, second at 3R, and third at 5R
            first_target = (
                entry_price + (1.5 * risk_amount)
                if direction == "long"
                else entry_price - (1.5 * risk_amount)
            )
            second_target = (
                entry_price + (3 * risk_amount)
                if direction == "long"
                else entry_price - (3 * risk_amount)
            )
            third_target = (
                entry_price + (5 * risk_amount)
                if direction == "long"
                else entry_price - (5 * risk_amount)
            )

            logging.info(f"Target 1: {first_target} (1.5R)")
            logging.info(f"Target 2: {second_target} (3R)")
            logging.info(f"Target 3: {third_target} (5R)")

            # Start trade management
            manage_trade(
                entry_price,
                trade,
                stop_loss_order,
                direction,
                share_size,
                risk_amount,
                stock,
            )
        else:
            logging.warning("Trade entry failed, exiting.")

    except Exception as e:
        logging.error(f"Error in main execution: {e}")
    finally:
        # Disconnect from API
        if ib.isConnected():
            ib.disconnect()
            logging.info("Disconnected from TWS API")
