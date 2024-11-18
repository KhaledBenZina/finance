from ib_insync import *
import time
import logging

# Connect to TWS API
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


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


def enter_trade(stock, direction):
    logging.info("Entering trade...")
    # Place initial market order for 100 shares
    initial_action = "BUY" if direction == "long" else "SELL"
    initial_order = MarketOrder(initial_action, 100)
    trade = ib.placeOrder(stock, initial_order)
    ib.sleep(2)  # Wait for the order to fill
    entry_price = trade.orderStatus.avgFillPrice  # Capture fill price for reference
    logging.info(f"Initial order filled at {entry_price}")

    # Set initial stop loss
    stop_price = (
        entry_price - 0.5 if direction == "long" else entry_price + 0.5
    )  # Stop loss logic for long/short
    stop_action = "SELL" if direction == "long" else "BUY"
    stop_loss_order = StopOrder(stop_action, 100, stop_price)
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop loss order placed at {stop_price}")

    return trade, entry_price, stop_loss_order


def manage_trade(entry_price, trade, stop_loss_order, direction):
    logging.info("Managing trade...")
    # Set profit targets
    partial1_target = entry_price + 0.5 if direction == "long" else entry_price - 0.5
    partial2_target = entry_price + 1.0 if direction == "long" else entry_price - 1.0
    remaining_shares = 100
    first_partial = False

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
            # Take partial of 30 shares
            partial_action = "SELL" if direction == "long" else "BUY"
            partial_order1 = MarketOrder(partial_action, 30)
            ib.placeOrder(stock, partial_order1)
            ib.cancelOrder(stop_loss_order)  # Remove initial stop
            logging.info(
                "Partial order of 30 shares placed and initial stop loss canceled."
            )

            # Adjust stop to break-even
            new_stop_price = entry_price
            stop_action = "SELL" if direction == "long" else "BUY"
            break_even_stop = StopOrder(stop_action, 70, new_stop_price)
            ib.placeOrder(stock, break_even_stop)
            logging.info(f"Break-even stop loss order placed at {new_stop_price}")
            remaining_shares -= 30
            first_partial = True  # Ensure first partial is only taken once

        # Second partial take profit
        if remaining_shares == 70 and (
            (
                current_price >= partial2_target
                if direction == "long"
                else current_price <= partial2_target
            )
        ):
            logging.info("Second partial take profit target hit.")
            # Take another partial of 30 shares
            partial_order2 = MarketOrder(partial_action, 30)
            ib.placeOrder(stock, partial_order2)
            ib.cancelOrder(break_even_stop)  # Remove break-even stop
            logging.info(
                "Partial order of 30 shares placed and break-even stop loss canceled."
            )

            # Set trailing stop for remaining 40 shares
            trail_amount = 0.5
            trailing_action = "SELL" if direction == "long" else "BUY"
            trailing_stop_order = create_trailing_stop_order(
                trailing_action, 40, trail_amount
            )
            ib.placeOrder(stock, trailing_stop_order)
            logging.info("Trailing stop order placed for remaining 40 shares.")
            remaining_shares -= 30

        # Stop loss triggered
        if (current_price <= entry_price - 0.5 and direction == "long") or (
            current_price >= entry_price + 0.5 and direction == "short"
        ):
            logging.info("Stop loss triggered.")
            break

        ib.sleep(1)


# Main execution
direction = "short"  # Change to 'long' or 'short' based on the desired trade
# Define contract for the stock (e.g., NVDA)
stock = Stock("NVDA", "SMART", "USD")
trade, entry_price, stop = enter_trade(stock, direction)
manage_trade(entry_price, trade, stop, direction)

# Disconnect from API
ib.disconnect()
