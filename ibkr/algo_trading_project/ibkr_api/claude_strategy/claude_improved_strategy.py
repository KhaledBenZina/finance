from ib_insync import *
import time
import logging
import math
import statistics

from analysis_functions import TradingSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Global configuration for testing
TEST_MODE = False  # Set to True for faster testing
TEST_RISK_PCT = 0.001  # 0.1% risk for very tight targets in test mode

if __name__ == "__main__":
    try:
        # Test mode settings
        TEST_MODE = False  # Set to True for faster testing
        TEST_RISK_PCT = 0.001  # 0.1% risk for very tight targets in test mode

        # Account settings
        ACCOUNT_SIZE = 16000  # Your account size in dollars
        RISK_PERCENT = 1.0  # Risk percentage (1.0 = 1% of account per trade)
        USE_ADAPTIVE_TARGETS = True  # Enable market regime-based target adjustment

        direction = "long"  # Change to 'long' or 'short' based on the desired trade
        # Define contract for the stock (e.g., NVDA)
        stock = Stock("NVDA", "SMART", "USD")

        # Instantiate the trading system (connects automatically)
        ts = TradingSystem()

        # Make sure we're connected
        if not ts.isConnected():
            ts.connect("127.0.0.1", 7497, clientId=1)

        # Get current price for position sizing calculation
        ticker = ts.reqTickers(stock)[0]
        current_price = (
            ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
        )

        # Calculate risk amount - either dynamic from ATR or fixed for testing
        if TEST_MODE:
            risk_amount = round(current_price * TEST_RISK_PCT, 2)
        else:
            risk_amount = ts.calculate_dynamic_risk(stock)

        # Calculate position size based on account risk parameters
        share_size = ts.calculate_position_size(
            ACCOUNT_SIZE, RISK_PERCENT, risk_amount, current_price, direction
        )
        logging.info(f"Using dynamic position size of {share_size} shares")

        # Determine market regime for adaptive targets
        if USE_ADAPTIVE_TARGETS and not TEST_MODE:
            regime, volatility_ratio = ts.get_market_regime(stock)
        else:
            regime, volatility_ratio = "ranging", 1.0  # Default for testing

        trade, entry_price, stop_loss_order, risk_amount = ts.enter_trade(
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

            # Set targets - either adaptive or fixed
            if USE_ADAPTIVE_TARGETS and not TEST_MODE:
                first_target, second_target, third_target, target_allocation = (
                    ts.adjust_targets_for_regime(
                        entry_price, risk_amount, direction, regime, volatility_ratio
                    )
                )

                # Calculate actual shares to exit at each target
                partial1_size = math.ceil(share_size * target_allocation[0])
                partial2_size = math.ceil(share_size * target_allocation[1])
                partial3_size = share_size - partial1_size - partial2_size
            else:
                # Standard fixed targets
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

                # Fixed allocation (equal thirds)
                partial1_size = math.ceil(share_size / 3)
                partial2_size = math.ceil(share_size / 3)
                partial3_size = share_size - partial1_size - partial2_size

            logging.info(f"Target 1: {first_target} with {partial1_size} shares")
            logging.info(f"Target 2: {second_target} with {partial2_size} shares")
            logging.info(f"Target 3: {third_target} with {partial3_size} shares")

            # Calculate expected profit if all targets hit
            avg_exit_price = (
                (first_target * partial1_size)
                + (second_target * partial2_size)
                + (third_target * partial3_size)
            ) / share_size

            expected_profit = (
                (avg_exit_price - entry_price) * share_size
                if direction == "long"
                else (entry_price - avg_exit_price) * share_size
            )
            expected_r = expected_profit / (risk_amount * share_size)
            logging.info(
                f"Expected profit if all targets hit: ${expected_profit:.2f} ({expected_r:.2f}R)"
            )

            # Start trade management with the partial sizes
            ts.manage_trade(
                entry_price,
                trade,
                stop_loss_order,
                direction,
                share_size,
                risk_amount,
                stock,
                first_target=first_target,
                second_target=second_target,
                third_target=third_target,
                partial1_size=partial1_size,
                partial2_size=partial2_size,
            )
        else:
            logging.warning("Trade entry failed, exiting.")

    except Exception as e:
        logging.error(f"Error in main execution: {e}")
        import traceback

        logging.error(traceback.format_exc())
    finally:
        # Disconnect from API
        if ts.isConnected():
            ts.disconnect()
            logging.info("Disconnected from TWS API")
