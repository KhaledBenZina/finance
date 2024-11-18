from ib_insync import *
import time
import logging

# Connect to TWS API
ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)  # Adjust port for live vs. paper

# Define contract for the stock (e.g., AAPL)
stock = Stock("NVDA", "SMART", "USD")


# Function to enter the trade
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


def enter_trade():
    logging.info("Entering trade...")
    # Place initial market order for 100 shares
    initial_order = MarketOrder("BUY", 100)  # Use 'SELL' for short position
    trade = ib.placeOrder(stock, initial_order)
    ib.sleep(2)  # Wait for the order to fill
    entry_price = trade.orderStatus.avgFillPrice  # Capture fill price for reference
    logging.info(f"Initial order filled at {entry_price}")

    # Set initial stop loss at +/- $0.50
    stop_loss_order = StopOrder("SELL", 100, entry_price - 0.5)  # Use '+0.5' for short
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop loss order placed at {entry_price - 0.5}")

    return trade, entry_price, stop_loss_order


# Function to adjust orders as price hits targets
def manage_trade(entry_price, trade, stop_loss_order):
    logging.info("Managing trade...")
    # Monitor for price conditions to hit partial targets
    first_partial = False
    while True:
        # Get latest price
        market_data = ib.reqMktData(stock)
        ib.sleep(1)  # Short delay for price polling
        current_price = market_data.last
        logging.info(f"Current price: {current_price}")

        # Check for first partial take profit at +/- $0.5
        if current_price >= entry_price + 0.5 and first_partial:
            logging.info("First partial take profit target hit.")
            # Take partial of 30 shares
            partial_order1 = MarketOrder("SELL", 30)
            ib.placeOrder(stock, partial_order1)
            ib.cancelOrder(stop_loss_order)  # Remove initial stop
            logging.info(
                "Partial order of 30 shares placed and initial stop loss canceled."
            )
            # Adjust stop to break-even
            break_even_stop = StopOrder("SELL", 70, entry_price)
            ib.placeOrder(stock, break_even_stop)
            logging.info(f"Break-even stop loss order placed at {entry_price}")
            ib.sleep(1)
            first_partial = True

        # Check for second partial take profit at +/- $1.0
        if current_price >= entry_price + 1.0:
            logging.info("Second partial take profit target hit.")
            # Take another partial of 30 shares
            partial_order2 = MarketOrder("SELL", 30)
            ib.placeOrder(stock, partial_order2)
            ib.cancelOrder(break_even_stop)  # Remove break-even stop
            logging.info(
                "Partial order of 30 shares placed and break-even stop loss canceled."
            )

            # Set trailing stop for remaining 40 shares at +/- $0.5
            trailing_stop_order = create_trailing_stop_order("SELL", 40, 0.5)
            ib.placeOrder(stock, trailing_stop_order)
            logging.info("Trailing stop order placed for remaining 40 shares.")
            break

        # Let trade run until end of day or exit conditions are met
        if market_data.last <= entry_price - 0.5:  # Stop loss hit
            logging.info("Stop loss triggered.")
            break
        ib.sleep(1)


# Execute strategy
trade, entry_price, stop = enter_trade()
manage_trade(entry_price, trade, stop)

# Disconnect from API after trading session
ib.disconnect()
