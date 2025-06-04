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

# Global configuration
TEST_MODE = False  # Set to True for faster testing
TEST_RISK_PCT = 0.01  # 1% risk for testing

# Position sizing configuration - CASH ONLY
FIXED_RISK_DOLLARS = 100.0  # Risk exactly $100 per trade
MIN_POSITION_SIZE = 1  # Minimum 1 share
MAX_POSITION_SIZE = 500  # Reduced max for cash-only trading
MIN_RISK_REWARD_RATIO = 1.5  # Minimum 1.5:1 risk/reward ratio
CASH_USAGE_LIMIT = 0.9  # Use maximum 90% of available cash per trade

# S/R level configuration
SR_BUFFER_PERCENTAGE = 0.15  # 0.15% buffer around S/R levels
MIN_ADJUSTMENT_TICKS = 5  # Minimum ticks to adjust when near S/R
MAX_ADJUSTMENT_PERCENTAGE = 0.5  # Maximum 0.5% adjustment from original target


def get_account_value():
    """Get current account value from Interactive Brokers"""
    try:
        account_summary = ib.accountSummary()

        # Look for NetLiquidation value (total account value)
        for item in account_summary:
            if item.tag == "NetLiquidation":
                account_value = float(item.value)
                logging.info(f"Account Net Liquidation Value: ${account_value:,.2f}")
                return account_value

        # If NetLiquidation not found, try TotalCashValue
        for item in account_summary:
            if item.tag == "TotalCashValue":
                account_value = float(item.value)
                logging.info(f"Account Total Cash Value: ${account_value:,.2f}")
                return account_value

        logging.warning("Could not find NetLiquidation or TotalCashValue")
        return None

    except Exception as e:
        logging.error(f"Error getting account value: {e}")
        return None


def get_available_cash():
    """Get available cash (not margin) from Interactive Brokers"""
    try:
        account_summary = ib.accountSummary()

        # Look for AvailableFunds (cash available for trading)
        for item in account_summary:
            if item.tag == "AvailableFunds":
                available_cash = float(item.value)
                logging.info(f"Available Cash: ${available_cash:,.2f}")
                return available_cash

        # If AvailableFunds not found, try CashBalance
        for item in account_summary:
            if item.tag == "CashBalance":
                available_cash = float(item.value)
                logging.info(f"Cash Balance: ${available_cash:,.2f}")
                return available_cash

        # If neither found, try TotalCashValue
        for item in account_summary:
            if item.tag == "TotalCashValue":
                available_cash = float(item.value)
                logging.info(f"Total Cash Value: ${available_cash:,.2f}")
                return available_cash

        logging.warning("Could not find available cash amount")
        return None

    except Exception as e:
        logging.error(f"Error getting available cash: {e}")
        return None


def calculate_position_size(
    entry_price,
    stop_price,
    account_value,
    fixed_risk_dollars=FIXED_RISK_DOLLARS,
    direction="long",
):
    """Calculate position size based on fixed dollar risk - NO MARGIN"""
    if not entry_price or not stop_price or entry_price <= 0 or stop_price <= 0:
        logging.error("Invalid entry or stop price for position sizing")
        return None, None

    # Get available cash for trading
    available_cash = get_available_cash()
    if not available_cash or available_cash <= 0:
        logging.error("No available cash for trading")
        return None, None

    # Use 90% of available cash as safety buffer
    usable_cash = available_cash * CASH_USAGE_LIMIT

    # Calculate risk per share (distance between entry and stop)
    risk_per_share = abs(entry_price - stop_price)

    if risk_per_share <= 0:
        logging.error("Risk per share must be greater than 0")
        return None, None

    # Calculate position size based on fixed dollar risk
    position_size_by_risk = int(fixed_risk_dollars / risk_per_share)

    # Calculate maximum position size based on available cash
    if direction == "short":
        # For short selling without margin, we can't short more than we have in cash
        logging.warning("SHORT SELLING WITHOUT MARGIN IS VERY RESTRICTIVE")
        logging.warning("Consider using long positions only for cash-only trading")

        # For cash-only short selling, we can only short what we can cover
        max_position_size_by_cash = int(usable_cash / entry_price)

        logging.info(f"Cash-Only Short Position Analysis:")
        logging.info(f"  Available Cash: ${available_cash:,.2f}")
        logging.info(f"  Usable Cash ({CASH_USAGE_LIMIT*100}%): ${usable_cash:,.2f}")
        logging.info(f"  Max Shares by Cash: {max_position_size_by_cash}")

    else:
        # For long positions, we can buy as many shares as cash allows
        max_position_size_by_cash = int(usable_cash / entry_price)

        logging.info(f"Cash-Only Long Position Analysis:")
        logging.info(f"  Available Cash: ${available_cash:,.2f}")
        logging.info(f"  Usable Cash ({CASH_USAGE_LIMIT*100}%): ${usable_cash:,.2f}")
        logging.info(f"  Stock Price: ${entry_price:.2f}")
        logging.info(f"  Max Shares by Cash: {max_position_size_by_cash}")

    # Use the smaller of risk-based or cash-based position size
    position_size = min(position_size_by_risk, max_position_size_by_cash)

    # Apply safety limits
    position_size = max(MIN_POSITION_SIZE, min(position_size, MAX_POSITION_SIZE))

    # Check if we have enough cash for the trade
    position_value = position_size * entry_price
    if position_value > usable_cash:
        logging.error(f"Not enough cash for trade:")
        logging.error(f"  Position Value: ${position_value:,.2f}")
        logging.error(f"  Available Cash: ${usable_cash:,.2f}")
        return None, None

    # Check if position size was limited by cash
    if position_size < position_size_by_risk:
        logging.warning(f"Position size limited by available cash:")
        logging.warning(f"  Risk-based size: {position_size_by_risk} shares")
        logging.warning(f"  Cash-limited size: {position_size} shares")
        logging.warning(
            f"  Position reduced by {position_size_by_risk - position_size} shares"
        )

    # Calculate actual risk with final position size
    actual_risk_dollars = position_size * risk_per_share

    # Calculate cash usage
    cash_usage_pct = (position_value / available_cash) * 100

    # Calculate risk as percentage of account for reference
    risk_percentage_of_account = (
        (actual_risk_dollars / account_value) * 100 if account_value else 0
    )

    logging.info(f"Fixed Dollar Risk Position Sizing:")
    logging.info(f"  Target Risk: ${fixed_risk_dollars:.2f}")
    logging.info(f"  Risk per Share: ${risk_per_share:.2f}")
    logging.info(f"  Position Size: {position_size} shares")
    logging.info(f"  Position Value: ${position_value:,.2f}")
    logging.info(f"  Cash Usage: {cash_usage_pct:.1f}% of available cash")
    logging.info(f"  Actual Risk: ${actual_risk_dollars:.2f}")
    logging.info(f"  Risk as % of Account: {risk_percentage_of_account:.2f}%")
    logging.info(f"  NO MARGIN USED - CASH ONLY TRADE")

    return position_size, actual_risk_dollars


def get_current_price(stock):
    """Get current market price for a stock"""
    try:
        ticker = ib.reqTickers(stock)[0]
        current_price = (
            ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
        )

        if current_price <= 0:
            ib.reqMktData(stock, "", False, False)
            ib.sleep(2)
            ticker = ib.reqTickers(stock)[0]
            current_price = (
                ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
            )

        return current_price
    except Exception as e:
        logging.error(f"Error getting current price: {e}")
        return None


def calculate_dynamic_risk(stock, atr_period=14):
    """Calculate dynamic risk based on ATR"""
    bars = ib.reqHistoricalData(
        stock,
        endDateTime="",
        durationStr="5 D",
        barSizeSetting="15 mins",
        whatToShow="TRADES",
        useRTH=True,
    )

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
        return round(atr * 0.5, 2)
    else:
        return 0.5


def get_support_resistance_levels(stock):
    """Calculate key support and resistance levels"""
    levels = {}

    try:
        # Get current day data
        today_bars = ib.reqHistoricalData(
            stock,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )

        # Get previous day data
        prev_day_bars = ib.reqHistoricalData(
            stock,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )

        if len(today_bars) > 0:
            today = today_bars[-1]
            levels["today_high"] = today.high
            levels["today_low"] = today.low

        if len(prev_day_bars) >= 2:
            prev_day = prev_day_bars[-2]
            levels["prev_day_high"] = prev_day.high
            levels["prev_day_low"] = prev_day.low
            levels["prev_day_close"] = prev_day.close

            # Calculate Camarilla levels
            prev_high = prev_day.high
            prev_low = prev_day.low
            prev_close = prev_day.close

            levels["camarilla_r4"] = prev_close + ((prev_high - prev_low) * 1.1) / 2
            levels["camarilla_s4"] = prev_close - ((prev_high - prev_low) * 1.1) / 2
            levels["camarilla_r3"] = prev_close + ((prev_high - prev_low) * 1.1) / 4
            levels["camarilla_s3"] = prev_close - ((prev_high - prev_low) * 1.1) / 4

        logging.info(f"S/R levels calculated: {levels}")
        return levels

    except Exception as e:
        logging.error(f"Error calculating S/R levels: {e}")
        return {}


def is_near_support_resistance(price, sr_levels, buffer_pct=SR_BUFFER_PERCENTAGE):
    """Check if a price is near any support/resistance level"""
    if not sr_levels:
        return False, None, None

    closest_distance = float("inf")
    closest_level = None
    closest_name = None

    for level_name, level_price in sr_levels.items():
        if level_price is None:
            continue

        distance = abs(price - level_price)
        percentage_distance = (distance / price) * 100

        if percentage_distance <= buffer_pct:
            if distance < closest_distance:
                closest_distance = distance
                closest_level = level_price
                closest_name = level_name

    is_near = closest_level is not None
    return is_near, closest_level, closest_name


def adjust_target_for_sr_levels(original_target, sr_levels, direction, current_price):
    """Adjust target price if it's too close to a support/resistance level"""
    is_near, closest_level, level_name = is_near_support_resistance(
        original_target, sr_levels
    )

    if not is_near:
        return original_target, "No adjustment needed"

    logging.info(f"Target {original_target} is near {level_name} at {closest_level}")

    # Calculate adjustment based on direction
    if direction == "long":
        if original_target >= closest_level:
            adjusted_target = closest_level + (MIN_ADJUSTMENT_TICKS * 0.01)
        else:
            adjusted_target = closest_level - (MIN_ADJUSTMENT_TICKS * 0.01)
    else:  # short
        if original_target <= closest_level:
            adjusted_target = closest_level - (MIN_ADJUSTMENT_TICKS * 0.01)
        else:
            adjusted_target = closest_level + (MIN_ADJUSTMENT_TICKS * 0.01)

    # Ensure adjustment isn't too extreme
    max_adjustment = current_price * (MAX_ADJUSTMENT_PERCENTAGE / 100)
    adjustment_amount = abs(adjusted_target - original_target)

    if adjustment_amount > max_adjustment:
        if direction == "long":
            adjusted_target = original_target + (
                max_adjustment if adjusted_target > original_target else -max_adjustment
            )
        else:
            adjusted_target = original_target - (
                max_adjustment if adjusted_target < original_target else -max_adjustment
            )

    reason = f"Adjusted from {original_target:.2f} to {adjusted_target:.2f} due to {level_name} at {closest_level:.2f}"
    return adjusted_target, reason


def adjust_stop_loss_for_sr_levels(original_stop, sr_levels, direction, entry_price):
    """Adjust stop loss if it's too close to a support/resistance level"""
    is_near, closest_level, level_name = is_near_support_resistance(
        original_stop, sr_levels
    )

    if not is_near:
        return original_stop, "No adjustment needed"

    logging.info(f"Stop loss {original_stop} is near {level_name} at {closest_level}")

    if direction == "long":
        adjusted_stop = closest_level - (MIN_ADJUSTMENT_TICKS * 0.01)
    else:  # short
        adjusted_stop = closest_level + (MIN_ADJUSTMENT_TICKS * 0.01)

    reason = f"Adjusted stop from {original_stop:.2f} to {adjusted_stop:.2f} due to {level_name} at {closest_level:.2f}"
    return adjusted_stop, reason


def calculate_adjusted_targets(entry_price, risk_amount, direction, stock):
    """Calculate targets with S/R level adjustments"""
    sr_levels = get_support_resistance_levels(stock)

    # Calculate original targets
    original_target1 = (
        entry_price + (1.5 * risk_amount)
        if direction == "long"
        else entry_price - (1.5 * risk_amount)
    )
    original_target2 = (
        entry_price + (3 * risk_amount)
        if direction == "long"
        else entry_price - (3 * risk_amount)
    )
    original_target3 = (
        entry_price + (5 * risk_amount)
        if direction == "long"
        else entry_price - (5 * risk_amount)
    )

    # Adjust targets based on S/R levels
    adjusted_target1, reason1 = adjust_target_for_sr_levels(
        original_target1, sr_levels, direction, entry_price
    )
    adjusted_target2, reason2 = adjust_target_for_sr_levels(
        original_target2, sr_levels, direction, entry_price
    )
    adjusted_target3, reason3 = adjust_target_for_sr_levels(
        original_target3, sr_levels, direction, entry_price
    )

    logging.info(f"Target 1: {reason1}")
    logging.info(f"Target 2: {reason2}")
    logging.info(f"Target 3: {reason3}")

    return adjusted_target1, adjusted_target2, adjusted_target3, sr_levels


def validate_trade_setup(entry_price, stop_price, target_price, direction):
    """Validate that the trade setup meets minimum risk/reward requirements"""
    if not all([entry_price, stop_price, target_price]):
        return False, "Missing price data"

    risk = abs(entry_price - stop_price)
    reward = (
        target_price - entry_price
        if direction == "long"
        else entry_price - target_price
    )

    if risk <= 0:
        return False, "Risk must be greater than 0"

    if reward <= 0:
        return False, "Reward must be greater than 0"

    risk_reward_ratio = reward / risk

    if risk_reward_ratio < MIN_RISK_REWARD_RATIO:
        return (
            False,
            f"Risk/reward ratio {risk_reward_ratio:.2f} is below minimum {MIN_RISK_REWARD_RATIO}",
        )

    logging.info(f"Trade validated with {risk_reward_ratio:.2f} risk/reward ratio")
    return True, f"Trade setup valid with {risk_reward_ratio:.2f} risk/reward ratio"


def get_price_distance(current_price, target_price, direction="long"):
    """Calculate how far price is from target (in percent and ticks)"""
    if current_price == 0 or target_price == 0:
        return "N/A", "N/A"

    if direction == "long":
        distance = target_price - current_price
    else:
        distance = current_price - target_price

    pct_distance = (abs(distance) / current_price) * 100
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
    sr_levels=None,
    account_value=None,
    total_risk_dollars=None,
):
    """Display comprehensive trade status"""

    # Calculate P&L
    if direction == "long":
        points_pnl = current_price - entry_price
        pct_pnl = (points_pnl / entry_price) * 100
    else:
        points_pnl = entry_price - current_price
        pct_pnl = (points_pnl / entry_price) * 100

    dollar_pnl = points_pnl * remaining_shares
    pnl_sign = "+" if points_pnl >= 0 else ""

    # Account P&L percentage
    account_pnl_pct = ""
    if account_value and account_value > 0:
        account_pnl_pct = f" ({(dollar_pnl / account_value) * 100:.2f}% of account)"

    print("\n" + "=" * 60)
    print(
        f"TRADE STATUS - {stock.symbol} {direction.upper()} - {remaining_shares} shares - Stage: {trade_stage}"
    )
    print("=" * 60)
    print(f"Entry: ${entry_price:.2f}    Current: ${current_price:.2f}")
    print(f"P&L:   {pnl_sign}{points_pnl:+.2f} pts ({pnl_sign}{pct_pnl:+.2f}%)")
    print(f"P&L:   ${pnl_sign}{dollar_pnl:+.2f}{account_pnl_pct}")

    if total_risk_dollars and account_value:
        print(
            f"Risk:  ${total_risk_dollars:.2f} ({(total_risk_dollars/account_value)*100:.2f}% of account)"
        )

    print("-" * 60)

    if trade_stage == "Initial":
        tp1_pct, tp1_ticks = get_price_distance(
            current_price, partial1_target, direction
        )
        tp2_pct, tp2_ticks = get_price_distance(
            current_price, partial2_target, direction
        )
        sl_pct, sl_ticks = get_price_distance(current_price, stop_price, direction)

        print(f"Stop Loss @ ${stop_price:.2f}  Distance: {sl_pct} ({sl_ticks})")
        print(f"Target 1 @ ${partial1_target:.2f}  Distance: {tp1_pct} ({tp1_ticks})")
        print(f"Target 2 @ ${partial2_target:.2f}  Distance: {tp2_pct} ({tp2_ticks})")

        if partial3_target:
            tp3_pct, tp3_ticks = get_price_distance(
                current_price, partial3_target, direction
            )
            print(
                f"Target 3 @ ${partial3_target:.2f}  Distance: {tp3_pct} ({tp3_ticks})"
            )

    elif trade_stage == "Partial1":
        tp2_pct, tp2_ticks = get_price_distance(
            current_price, partial2_target, direction
        )
        sl_pct, sl_ticks = get_price_distance(current_price, stop_price, direction)

        print(f"Break-Even @ ${stop_price:.2f}  Distance: {sl_pct}")
        print(f"Target 2 @ ${partial2_target:.2f}  Distance: {tp2_pct} ({tp2_ticks})")
        if partial3_target:
            tp3_pct, tp3_ticks = get_price_distance(
                current_price, partial3_target, direction
            )
            print(
                f"Target 3 @ ${partial3_target:.2f}  Distance: {tp3_pct} ({tp3_ticks})"
            )
        print("Target 1: ✓ FILLED")

    elif trade_stage == "Partial2":
        if partial3_target:
            tp3_pct, tp3_ticks = get_price_distance(
                current_price, partial3_target, direction
            )
            sl_pct, sl_ticks = get_price_distance(current_price, stop_price, direction)
            print(f"Profit Lock @ ${stop_price:.2f}")
            print(
                f"Target 3 @ ${partial3_target:.2f}  Distance: {tp3_pct} ({tp3_ticks})"
            )
        else:
            print(f"Trailing Stop: ${stop_price:.2f}")
        print("Target 1: ✓ FILLED")
        print("Target 2: ✓ FILLED")

    elif trade_stage == "Complete":
        print("Target 1: ✓ FILLED")
        print("Target 2: ✓ FILLED")
        print("Target 3: ✓ FILLED")
        print("TRADE COMPLETED")

    # Show key S/R levels
    if sr_levels:
        print("-" * 60)
        print("KEY S/R LEVELS:")
        if "today_high" in sr_levels:
            print(f"Today High: ${sr_levels['today_high']:.2f}")
        if "today_low" in sr_levels:
            print(f"Today Low:  ${sr_levels['today_low']:.2f}")
        if "camarilla_r4" in sr_levels:
            print(f"Cam R4:     ${sr_levels['camarilla_r4']:.2f}")
        if "camarilla_s4" in sr_levels:
            print(f"Cam S4:     ${sr_levels['camarilla_s4']:.2f}")

    print("=" * 60)


def enter_trade(
    stock,
    direction,
    risk_percentage=ACCOUNT_RISK_PERCENTAGE,
    test_mode=False,
    test_risk_pct=0.01,
):
    """Enter a trade with automatic position sizing"""

    logging.info(f"Entering {direction} trade with {risk_percentage}% account risk...")

    # Get account value for position sizing
    account_value = get_account_value()
    if not account_value:
        logging.error(
            "Could not retrieve account value. Cannot calculate position size."
        )
        return None, None, None, None, None, None

    # Get current price
    current_price = get_current_price(stock)
    if not current_price:
        logging.error("Could not retrieve current price")
        return None, None, None, None, None, None

    if test_mode:
        risk_amount = round(current_price * test_risk_pct, 2)
        logging.info(f"TEST MODE: Using small risk amount: {risk_amount}")
        share_size = 10  # Fixed small size for testing
    else:
        risk_amount = calculate_dynamic_risk(stock)
        logging.info(f"Dynamic risk calculated: {risk_amount}")

    # Calculate initial stop price
    initial_stop_price = (
        current_price - risk_amount
        if direction == "long"
        else current_price + risk_amount
    )

    # Get S/R levels for stop loss adjustment
    sr_levels = get_support_resistance_levels(stock)

    # Adjust stop loss based on S/R levels
    adjusted_stop_price, stop_reason = adjust_stop_loss_for_sr_levels(
        initial_stop_price, sr_levels, direction, current_price
    )
    logging.info(f"Stop loss: {stop_reason}")

    # Calculate position size based on account value and risk
    if not test_mode:
        share_size, actual_risk_dollars = calculate_position_size(
            current_price, adjusted_stop_price, account_value, risk_percentage
        )

        if not share_size:
            logging.error("Could not calculate position size")
            return None, None, None, None, None, None
    else:
        actual_risk_dollars = share_size * abs(current_price - adjusted_stop_price)

    # Calculate adjusted targets for validation
    adjusted_target1, adjusted_target2, adjusted_target3, _ = (
        calculate_adjusted_targets(
            current_price, abs(current_price - adjusted_stop_price), direction, stock
        )
    )

    # Validate trade setup
    is_valid, validation_message = validate_trade_setup(
        current_price, adjusted_stop_price, adjusted_target1, direction
    )

    if not is_valid:
        logging.warning(f"Trade setup invalid: {validation_message}")
        return None, None, None, None, None, None

    logging.info(f"Trade setup validated: {validation_message}")

    # Place initial market order
    initial_action = "BUY" if direction == "long" else "SELL"
    initial_order = MarketOrder(initial_action, share_size)
    trade = ib.placeOrder(stock, initial_order)
    ib.sleep(2)

    if trade.orderStatus.status != "Filled":
        logging.warning("Order not filled within timeout period")
        return None, None, None, None, None, None

    entry_price = trade.orderStatus.avgFillPrice
    logging.info(f"Initial order filled at ${entry_price:.2f} for {share_size} shares")

    # Recalculate stop loss based on actual entry price
    recalculated_stop = (
        entry_price - risk_amount if direction == "long" else entry_price + risk_amount
    )
    final_stop_price, final_stop_reason = adjust_stop_loss_for_sr_levels(
        recalculated_stop, sr_levels, direction, entry_price
    )
    logging.info(f"Final stop loss: {final_stop_reason}")

    # Place stop loss order
    stop_action = "SELL" if direction == "long" else "BUY"
    stop_loss_order = StopOrder(stop_action, share_size, final_stop_price)
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop loss order placed at ${final_stop_price:.2f}")

    # Calculate final risk metrics
    final_risk_per_share = abs(entry_price - final_stop_price)
    final_risk_dollars = share_size * final_risk_per_share
    final_risk_percentage = (final_risk_dollars / account_value) * 100

    logging.info(f"Final Trade Metrics:")
    logging.info(f"  Entry: ${entry_price:.2f}, Stop: ${final_stop_price:.2f}")
    logging.info(
        f"  Position: {share_size} shares, Risk: ${final_risk_per_share:.2f}/share"
    )
    logging.info(
        f"  Total Risk: ${final_risk_dollars:.2f} ({final_risk_percentage:.2f}%)"
    )

    return (
        trade,
        entry_price,
        stop_loss_order,
        final_risk_per_share,
        sr_levels,
        share_size,
    )


def manage_trade(
    entry_price,
    trade,
    stop_loss_order,
    direction,
    share_size,
    risk_amount,
    stock,
    sr_levels,
    account_value=None,
    total_risk_dollars=None,
):
    """Manage the trade with partial profit taking"""

    logging.info(f"Managing {direction} trade...")

    # Calculate adjusted targets using S/R levels
    partial1_target, partial2_target, partial3_target, _ = calculate_adjusted_targets(
        entry_price, risk_amount, direction, stock
    )

    logging.info(
        f"Adjusted targets - T1: ${partial1_target:.2f}, T2: ${partial2_target:.2f}, T3: ${partial3_target:.2f}"
    )

    # Initial position setup
    remaining_shares = share_size
    first_partial = False
    second_partial = False
    partial_size = math.ceil(share_size / 3)

    # Current stop price
    current_stop_price = (
        entry_price - risk_amount if direction == "long" else entry_price + risk_amount
    )

    # Trade stage tracking
    trade_stage = "Initial"
    display_counter = 0

    # For testing - simulate price movement
    start_time = time.time()
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
                if direction == "long":
                    actual_position_size = max(0, int(item.position))
                else:
                    actual_position_size = abs(min(0, int(item.position)))

                if actual_position_size == 0:
                    logging.info("Position is 0. Exiting trade management.")
                    return

                # Check for manual modifications
                if time.time() - manual_modification_check_time > 10:
                    if actual_position_size != remaining_shares:
                        logging.info(
                            f"Position size changed from {remaining_shares} to {actual_position_size}"
                        )
                        remaining_shares = actual_position_size
                    manual_modification_check_time = time.time()

        if not position_exists:
            logging.info("Position not found in portfolio. Exiting trade management.")
            return

        # Get latest price
        current_price = get_current_price(stock)
        if not current_price:
            logging.warning("Could not get current price")
            ib.sleep(1)
            continue

        # TEST MODE: Simulate price movement
        elapsed_seconds = time.time() - start_time
        if TEST_MODE:
            if elapsed_seconds > 5 and not first_partial:
                logging.info("TEST MODE: Simulating price movement for first partial")
                current_price = (
                    partial1_target + 0.01
                    if direction == "long"
                    else partial1_target - 0.01
                )
            elif elapsed_seconds > 10 and first_partial and not second_partial:
                logging.info("TEST MODE: Simulating price movement for second partial")
                current_price = (
                    partial2_target + 0.01
                    if direction == "long"
                    else partial2_target - 0.01
                )
            elif elapsed_seconds > 15 and second_partial:
                logging.info("TEST MODE: Simulating price movement for third target")
                current_price = (
                    partial3_target + 0.01
                    if direction == "long"
                    else partial3_target - 0.01
                )
            elif elapsed_seconds > 20 and remaining_shares > 0:
                logging.info("TEST MODE: Simulating stop loss trigger")
                current_price = (
                    entry_price - (2 * risk_amount)
                    if direction == "long"
                    else entry_price + (2 * risk_amount)
                )

        # Display status periodically
        display_counter += 1
        if display_counter >= 5:
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
                sr_levels,
                account_value,
                total_risk_dollars,
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
            logging.info("First partial target hit.")
            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order1 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order1)
            ib.cancelOrder(stop_loss_order)
            logging.info(
                f"Partial order of {partial_size} shares placed and initial stop canceled."
            )

            # Move stop to break-even
            new_stop_price = entry_price
            stop_action = "SELL" if direction == "long" else "BUY"
            break_even_stop = StopOrder(
                stop_action, remaining_shares - partial_size, new_stop_price
            )
            ib.placeOrder(stock, break_even_stop)
            logging.info(f"Break-even stop placed at ${new_stop_price:.2f}")

            remaining_shares -= partial_size
            first_partial = True
            stop_loss_order = break_even_stop
            current_stop_price = new_stop_price
            trade_stage = "Partial1"

            ib.sleep(2)

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
            logging.info("Second partial target hit.")
            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order2 = MarketOrder(partial_action, partial_size)
            ib.placeOrder(stock, partial_order2)
            ib.cancelOrder(stop_loss_order)
            logging.info(
                f"Second partial order of {partial_size} shares placed and break-even stop canceled."
            )

            # Set profit-lock stop
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
            logging.info(f"Profit-lock stop placed at ${new_stop_price:.2f}")

            remaining_shares -= partial_size
            second_partial = True
            stop_loss_order = profit_lock_stop
            current_stop_price = new_stop_price
            trade_stage = "Partial2"

            ib.sleep(2)

        # Third partial take profit
        elif second_partial and (
            (
                current_price >= partial3_target
                if direction == "long"
                else current_price <= partial3_target
            )
        ):
            logging.info("Third/Final target hit.")
            partial_action = "SELL" if direction == "long" else "BUY"
            final_order = MarketOrder(partial_action, remaining_shares)
            ib.placeOrder(stock, final_order)
            ib.cancelOrder(stop_loss_order)
            logging.info(
                f"Final order of {remaining_shares} shares placed. Trade completed."
            )

            remaining_shares = 0
            trade_stage = "Complete"

        # Check for stop loss
        if (current_price <= current_stop_price and direction == "long") or (
            current_price >= current_stop_price and direction == "short"
        ):
            logging.info(f"Stop loss at ${current_stop_price:.2f} likely triggered.")

            ib.sleep(1)  # Wait for order to process
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
                # Force close if stop didn't trigger
                logging.warning(
                    "Stop loss should have triggered but position still open - forcing close"
                )
                close_action = "SELL" if direction == "long" else "BUY"
                close_order = MarketOrder(close_action, remaining_shares)
                ib.placeOrder(stock, close_order)
                logging.info(
                    f"Emergency close order placed for remaining {remaining_shares} shares"
                )
                ib.sleep(2)
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
        # Configuration
        TEST_MODE = False  # Set to True for faster testing
        TEST_RISK_PCT = 0.01  # 1% risk for testing
        direction = "long"  # Change to 'long' or 'short'
        fixed_risk_dollars = 100.0  # Risk exactly $100 per trade

        # Define stock contract
        stock = Stock("NVDA", "SMART", "USD")

        # Ensure connection
        if not ib.isConnected():
            ib.connect("127.0.0.1", 7497, clientId=1)

        logging.info("=" * 60)
        logging.info("STARTING TRADE SETUP")
        logging.info("=" * 60)

        # Enter trade with fixed dollar risk
        result = enter_trade(
            stock, direction, fixed_risk_dollars, TEST_MODE, TEST_RISK_PCT
        )

        if result[0] is None:  # Check if trade entry failed
            logging.warning("Trade entry failed, exiting.")
        else:
            trade, entry_price, stop_loss_order, risk_amount, sr_levels, share_size = (
                result
            )

            # Get account value for display
            account_value = get_account_value() or 0
            total_risk_dollars = share_size * risk_amount

            # Display comprehensive trade information
            logging.info("=" * 60)
            logging.info("TRADE SUCCESSFULLY ENTERED")
            logging.info("=" * 60)
            logging.info(f"Entry Price: ${entry_price:.2f}")
            logging.info(f"Position Size: {share_size} shares")
            logging.info(f"Fixed Risk Amount: ${fixed_risk_dollars:.2f}")
            logging.info(f"Actual Risk: ${total_risk_dollars:.2f}")

            if account_value > 0:
                actual_risk_pct = (total_risk_dollars / account_value) * 100
                logging.info(f"Risk as % of Account: {actual_risk_pct:.2f}%")

            # Calculate and display adjusted targets
            target1, target2, target3, _ = calculate_adjusted_targets(
                entry_price, risk_amount, direction, stock
            )

            logging.info(f"Adjusted Target 1: ${target1:.2f} (1.5R)")
            logging.info(f"Adjusted Target 2: ${target2:.2f} (3R)")
            logging.info(f"Adjusted Target 3: ${target3:.2f} (5R)")

            # Calculate potential profits
            potential_profit_1 = abs(target1 - entry_price) * (share_size // 3)
            potential_profit_2 = abs(target2 - entry_price) * (share_size // 3)
            potential_profit_3 = abs(target3 - entry_price) * (share_size // 3)
            total_potential_profit = (
                potential_profit_1 + potential_profit_2 + potential_profit_3
            )

            logging.info(f"Potential Profits:")
            logging.info(f"  Target 1: ${potential_profit_1:.2f}")
            logging.info(f"  Target 2: ${potential_profit_2:.2f}")
            logging.info(f"  Target 3: ${potential_profit_3:.2f}")
            logging.info(f"  Total Max Profit: ${total_potential_profit:.2f}")
            logging.info(
                f"  Risk/Reward Ratio: {total_potential_profit/total_risk_dollars:.2f}:1"
            )

            logging.info("=" * 60)
            logging.info("STARTING TRADE MANAGEMENT")
            logging.info("=" * 60)

            # Start trade management
            manage_trade(
                entry_price,
                trade,
                stop_loss_order,
                direction,
                share_size,
                risk_amount,
                stock,
                sr_levels,
                account_value,
                total_risk_dollars,
            )

    except Exception as e:
        logging.error(f"Error in main execution: {e}")
        import traceback

        logging.error(traceback.format_exc())
    finally:
        # Disconnect from API
        if ib.isConnected():
            ib.disconnect()
            logging.info("Disconnected from TWS API")
