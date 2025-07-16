def calculate_position_size(stock, account_cash, risk_percentage=0.02, commission_per_trade=1.0):
    """
    Calculate position size based on available cash and risk management

    Args:
        stock: IB stock contract
        account_cash: Available cash in account
        risk_percentage: Percentage of account to risk per trade (default 2%)
        commission_per_trade: Commission cost per trade in USD

    Returns:
        tuple: (position_size_shares, risk_per_share, entry_price_estimate)
    """
    # Get current market price
    ticker = ib.reqTickers(stock)[0]
    current_price = ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last

    if current_price <= 0:
        logging.error("Could not get valid market price")
        return 0, 0, 0

    # Calculate risk amount (2% of account by default)
    total_risk_amount = account_cash * risk_percentage

    # Calculate dynamic risk per share (your existing ATR-based method)
    risk_per_share = calculate_dynamic_risk(stock)

    # If in test mode, use smaller risk
    if TEST_MODE:
        risk_per_share = current_price * TEST_RISK_PCT

    # Calculate maximum shares we can afford
    # Account for: stock price + commissions for entry and potential multiple exits
    # Estimate 4 trades total (1 entry + 3 partial exits) = $4 commission
    total_commission_estimate = 4 * commission_per_trade
    max_affordable_shares = int((account_cash - total_commission_estimate) / current_price)

    # Calculate shares based on risk management
    if risk_per_share > 0:
        risk_based_shares = int(total_risk_amount / risk_per_share)
    else:
        risk_based_shares = 0

    # Use the smaller of the two to ensure we don't exceed account limits
    position_size = min(max_affordable_shares, risk_based_shares)

    # Ensure minimum viable position (at least 3 shares for 3-part exit strategy)
    if position_size < 3:
        logging.warning(f"Calculated position size ({position_size}) too small for 3-part strategy")
        if max_affordable_shares >= 3:
            position_size = 3
            logging.info(f"Using minimum position size of 3 shares")
        else:
            logging.error(f"Account too small - can only afford {max_affordable_shares} shares at ${current_price}")
            return 0, 0, current_price

    # Log the calculation details
    logging.info(f"=== POSITION SIZE CALCULATION ===")
    logging.info(f"Account Cash: ${account_cash:,.2f}")
    logging.info(f"Current Price: ${current_price:.2f}")
    logging.info(f"Risk Percentage: {risk_percentage * 100:.1f}%")
    logging.info(f"Total Risk Amount: ${total_risk_amount:.2f}")
    logging.info(f"Risk Per Share: ${risk_per_share:.2f}")
    logging.info(f"Max Affordable Shares: {max_affordable_shares}")
    logging.info(f"Risk-Based Shares: {risk_based_shares}")
    logging.info(f"Final Position Size: {position_size} shares")
    logging.info(f"Total Position Value: ${position_size * current_price:.2f}")
    logging.info(f"Estimated Commissions: ${total_commission_estimate:.2f}")
    logging.info(f"Cash Remaining: ${account_cash - (position_size * current_price) - total_commission_estimate:.2f}")
    logging.info("=================================")

    return position_size, risk_per_share, current_price


def get_account_cash():
    """
    Get available cash from IB account
    """
    try:
        account_summary = ib.accountSummary()

        for item in account_summary:
            if item.tag == 'AvailableFunds' and item.currency == 'USD':
                available_cash = float(item.value)
                logging.info(f"Available cash in account: ${available_cash:,.2f}")
                return available_cash

        # Fallback - try TotalCashValue
        for item in account_summary:
            if item.tag == 'TotalCashValue' and item.currency == 'USD':
                total_cash = float(item.value)
                logging.info(f"Total cash value: ${total_cash:,.2f}")
                return total_cash

        logging.error("Could not find cash balance in account summary")
        return 0

    except Exception as e:
        logging.error(f"Error getting account cash: {e}")
        return 0


# Modified main execution section
if __name__ == "__main__":
    try:
        # REAL MONEY SETTINGS
        TEST_MODE = False  # Set to False for real trading
        RISK_PERCENTAGE = 0.02  # Risk 2% of account per trade (adjust as needed)

        direction = "short"  # Change to 'long' or 'short' based on desired trade
        stock = Stock("NVDA", "SMART", "USD")

        # Make sure we're connected
        if not ib.isConnected():
            ib.connect("127.0.0.1", 7497, clientId=1)

        # Enter trade with dynamic position sizing
        trade, entry_price, stop_loss_order, risk_amount, calculated_share_size = enter_trade_with_dynamic_size(
            stock, direction, RISK_PERCENTAGE, TEST_MODE
        )

        if trade and entry_price and stop_loss_order and calculated_share_size:
            logging.info(f"Trade entered at {entry_price} with {calculated_share_size} shares")
            logging.info(f"Risk amount per share: ${risk_amount:.2f}")
            logging.info(f"Total position value: ${entry_price * calculated_share_size:.2f}")

            # Start trade management with calculated share size
            manage_trade(
                entry_price,
                trade,
                stop_loss_order,
                direction,
                calculated_share_size,  # Use calculated size instead of fixed 100
                risk_amount,
                stock,
            )
        else:
            logging.warning("Trade entry failed, exiting.")

    except Exception as e:
        logging.error(f"Error in main execution: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            logging.info("Disconnected from TWS API")


# Modified enter_trade function
def enter_trade_with_dynamic_size(stock, direction, risk_percentage=0.02, test_mode=False, test_risk_pct=0.01):
    """
    Enter trade with position size calculated based on account cash
    """
    logging.info(f"Entering {direction} trade with dynamic position sizing...")

    # Get account cash
    account_cash = get_account_cash()
    if account_cash <= 0:
        logging.error("Could not determine account cash or insufficient funds")
        return None, None, None, None, None

    # Calculate position size
    share_size, risk_amount, current_price = calculate_position_size(
        stock, account_cash, risk_percentage, commission_per_trade=1.0
    )

    if share_size <= 0:
        logging.error("Cannot calculate valid position size")
        return None, None, None, None, None

    # Use your existing enter_trade logic but with calculated share_size
    if test_mode:
        risk_amount = current_price * test_risk_pct
        logging.info(f"TEST MODE: Using small risk amount: {risk_amount}")

    # Place initial market order
    initial_action = "BUY" if direction == "long" else "SELL"
    initial_order = MarketOrder(initial_action, share_size)
    trade = ib.placeOrder(stock, initial_order)
    ib.sleep(2)

    if trade.orderStatus.status != "Filled":
        logging.warning("Order not filled within timeout period")
        return None, None, None, None, None

    entry_price = trade.orderStatus.avgFillPrice
    logging.info(f"Initial order filled at {entry_price} for {share_size} shares")

    # Set initial stop loss
    stop_price = (
        entry_price - risk_amount if direction == "long" else entry_price + risk_amount
    )
    stop_action = "SELL" if direction == "long" else "BUY"
    stop_loss_order = StopOrder(stop_action, share_size, stop_price)
    ib.placeOrder(stock, stop_loss_order)
    logging.info(f"Stop loss order placed at {stop_price}")

    return trade, entry_price, stop_loss_order, risk_amount, share_size