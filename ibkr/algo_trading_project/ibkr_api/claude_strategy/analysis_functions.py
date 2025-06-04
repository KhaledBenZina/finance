import time
import logging
import math
import statistics
from ib_insync import *


class TradingSystem(IB):
    def __init__(self, host="127.0.0.1", port=7497, clientId=1):
        super().__init__()
        self.connect(host, port, clientId=clientId)

    def calculate_dynamic_risk(self, stock, atr_period=14):
        """Calculate dynamic risk based on ATR"""
        bars = self.reqHistoricalData(
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

    def calculate_position_size(
        self, account_size, risk_percent, risk_amount, entry_price, direction
    ):
        """Calculate dynamic position size based on account size and risk parameters"""
        max_risk_dollars = account_size * (risk_percent / 100)
        if risk_amount <= 0:
            logging.warning("Risk amount must be positive! Using minimum risk of $0.01")
            risk_amount = 0.01
        position_size = max_risk_dollars / risk_amount
        position_size = math.floor(position_size)
        position_size = max(1, position_size)
        logging.info(f"Position sizing calculation:")
        logging.info(f"Account size: ${account_size:,.2f}")
        logging.info(f"Risk percent: {risk_percent}%")
        logging.info(f"Risk amount per share: ${risk_amount:.2f}")
        logging.info(f"Maximum dollar risk: ${max_risk_dollars:.2f}")
        logging.info(f"Calculated position size: {position_size} shares")
        return position_size

    def get_market_regime(self, stock, lookback_days=20):
        """Determine the current market regime (trending, ranging, volatile)"""
        try:
            bars = self.reqHistoricalData(
                stock,
                endDateTime="",
                durationStr=f"{lookback_days} D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
            )
            if len(bars) < 5:
                logging.warning(
                    f"Not enough historical data for {stock.symbol}, using default regime"
                )
                return "ranging", 1.0
            closes = [bar.close for bar in bars]
            returns = [
                100 * (closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))
            ]
            recent_volatility = (
                statistics.stdev(returns[-5:]) if len(returns) >= 5 else 0
            )
            overall_volatility = statistics.stdev(returns) if len(returns) >= 2 else 0
            volatility_ratio = (
                recent_volatility / overall_volatility
                if overall_volatility > 0
                else 1.0
            )
            start_price = closes[0]
            end_price = closes[-1]
            price_change_pct = 100 * (end_price / start_price - 1)
            x = list(range(len(closes)))
            y = closes
            n = len(x)
            sum_x = sum(x)
            sum_y = sum(y)
            sum_x_squared = sum(xi**2 for xi in x)
            sum_xy = sum(xi * yi for xi, yi in zip(x, y))
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x_squared - sum_x**2)
            y_mean = sum_y / n
            ss_total = sum((yi - y_mean) ** 2 for yi in y)
            y_pred = [slope * xi + (sum_y - slope * sum_x) / n for xi in x]
            ss_residual = sum((yi - y_predi) ** 2 for yi, y_predi in zip(y, y_pred))
            r_squared = 1 - (ss_residual / ss_total) if ss_total > 0 else 0
            if r_squared > 0.7:
                regime = "trending_up" if slope > 0 else "trending_down"
            elif volatility_ratio > 1.5:
                regime = "volatile"
            else:
                regime = "ranging"
            logging.info(f"Market regime analysis for {stock.symbol}:")
            logging.info(f"- Price change: {price_change_pct:.2f}%")
            logging.info(f"- Volatility ratio: {volatility_ratio:.2f}")
            logging.info(f"- Trend strength (R²): {r_squared:.2f}")
            logging.info(f"- Detected regime: {regime}")
            return regime, volatility_ratio
        except Exception as e:
            logging.error(f"Error in get_market_regime: {e}")
            return "ranging", 1.0

    def adjust_targets_for_regime(
        self, entry_price, risk_amount, direction, regime, volatility_ratio
    ):
        """Adjust profit targets based on market regime and volatility"""
        base_target1_r = 1.5
        base_target2_r = 3.0
        base_target3_r = 5.0
        target_allocation = [1 / 3, 1 / 3, 1 / 3]
        if regime == "trending_up" and direction == "long":
            adjusted_target1_r = base_target1_r * 1.2
            adjusted_target2_r = base_target2_r * 1.3
            adjusted_target3_r = base_target3_r * 1.5
            target_allocation = [0.25, 0.35, 0.4]
        elif regime == "trending_down" and direction == "short":
            adjusted_target1_r = base_target1_r * 1.2
            adjusted_target2_r = base_target2_r * 1.3
            adjusted_target3_r = base_target3_r * 1.5
            target_allocation = [0.25, 0.35, 0.4]
        elif regime == "volatile":
            adjusted_target1_r = base_target1_r * 0.8
            adjusted_target2_r = base_target2_r * 0.9
            adjusted_target3_r = base_target3_r * 1.0
            target_allocation = [0.4, 0.4, 0.2]
        elif regime == "ranging":
            adjusted_target1_r = base_target1_r * 0.9
            adjusted_target2_r = base_target2_r * 0.8
            adjusted_target3_r = base_target3_r * 0.7
            target_allocation = [0.4, 0.4, 0.2]
        else:
            adjusted_target1_r = base_target1_r
            adjusted_target2_r = base_target2_r
            adjusted_target3_r = base_target3_r
        volatility_adjustment = min(1.5, max(0.7, volatility_ratio))
        adjusted_target1_r *= volatility_adjustment
        adjusted_target2_r *= volatility_adjustment
        adjusted_target3_r *= volatility_adjustment
        if direction == "long":
            target1 = entry_price + (adjusted_target1_r * risk_amount)
            target2 = entry_price + (adjusted_target2_r * risk_amount)
            target3 = entry_price + (adjusted_target3_r * risk_amount)
        else:
            target1 = entry_price - (adjusted_target1_r * risk_amount)
            target2 = entry_price - (adjusted_target2_r * risk_amount)
            target3 = entry_price - (adjusted_target3_r * risk_amount)
        logging.info(
            f"Adjusted targets for {regime} regime (volatility ratio: {volatility_ratio:.2f}):"
        )
        logging.info(f"- Target 1: {target1:.2f} ({adjusted_target1_r:.2f}R)")
        logging.info(f"- Target 2: {target2:.2f} ({adjusted_target2_r:.2f}R)")
        logging.info(f"- Target 3: {target3:.2f} ({adjusted_target3_r:.2f}R)")
        logging.info(
            f"- Target allocation: {[f'{a*100:.0f}%' for a in target_allocation]}"
        )
        return target1, target2, target3, target_allocation

    def get_price_distance(self, current_price, target_price, direction="long"):
        if current_price == 0 or target_price == 0:
            return "N/A", "N/A"
        if direction == "long":
            distance = target_price - current_price
        else:
            distance = current_price - target_price
        pct_distance = (abs(distance) / current_price) * 100
        ticks_distance = abs(distance) * 100
        return f"{pct_distance:.2f}%", f"{ticks_distance:.0f} ticks"

    def create_trailing_stop_order(self, action, quantity, trail_amount):
        trailing_stop_order = Order(
            action=action,
            orderType="TRAIL",
            totalQuantity=quantity,
            auxPrice=trail_amount,
            tif="GTC",
        )
        return trailing_stop_order

    def enter_trade(
        self, stock, direction, share_size, test_mode=False, test_risk_pct=0.01
    ):
        logging.info(
            f"Entering {direction} trade for {share_size} shares of {stock.symbol}"
        )
        if test_mode:
            ticker = self.reqTickers(stock)[0]
            current_price = (
                ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
            )
            risk_amount = round(current_price * test_risk_pct, 2)
            logging.info(f"TEST MODE: Using simplified risk amount: {risk_amount}")
        else:
            risk_amount = self.calculate_dynamic_risk(stock)
            logging.info(f"Dynamic risk calculated: {risk_amount}")
        initial_action = "BUY" if direction == "long" else "SELL"
        initial_order = MarketOrder(initial_action, share_size)
        trade = self.placeOrder(stock, initial_order)
        fill_timeout = 5
        start_time = time.time()
        while time.time() - start_time < fill_timeout:
            if trade.orderStatus.status == "Filled":
                break
            self.sleep(0.5)
        if trade.orderStatus.status != "Filled":
            logging.warning(f"Order not filled within {fill_timeout} seconds timeout")
            return None, None, None, None
        entry_price = trade.orderStatus.avgFillPrice
        logging.info(f"Order filled at {entry_price}")
        r_value = share_size * risk_amount
        logging.info(f"R-value for trade: ${r_value:.2f}")
        stop_price = (
            entry_price - risk_amount
            if direction == "long"
            else entry_price + risk_amount
        )
        stop_action = "SELL" if direction == "long" else "BUY"
        stop_loss_order = StopOrder(stop_action, share_size, stop_price)
        self.placeOrder(stock, stop_loss_order)
        logging.info(f"Stop loss placed at {stop_price} (1R from entry)")
        return trade, entry_price, stop_loss_order, risk_amount

    def display_trade_status(
        self,
        current_price,
        entry_price,
        stop_price,
        partial1_target,
        partial2_target,
        direction,
        remaining_shares,
        trade_stage,
        stock,
        partial3_target=None,
    ):
        if direction == "long":
            points_pnl = current_price - entry_price
            pct_pnl = (points_pnl / entry_price) * 100
        else:
            points_pnl = entry_price - current_price
            pct_pnl = (points_pnl / entry_price) * 100
        dollar_pnl = points_pnl * remaining_shares
        pnl_sign = "+" if points_pnl >= 0 else ""
        if trade_stage == "Initial":
            tp1_pct, tp1_ticks = self.get_price_distance(
                current_price, partial1_target, direction
            )
            tp2_pct, tp2_ticks = self.get_price_distance(
                current_price, partial2_target, direction
            )
            tp3_pct, tp3_ticks = (
                self.get_price_distance(current_price, partial3_target or 0, direction)
                if partial3_target
                else ("N/A", "N/A")
            )
            sl_pct, sl_ticks = self.get_price_distance(
                current_price, stop_price, direction
            )
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
            if partial3_target:
                status_str += f"║ Target 3 @ {partial3_target:<7.2f}  Distance: {tp3_pct} ({tp3_ticks})  ║\n"
            status_str += "╚═══════════════════════════════════════════════╝\n"
        elif trade_stage == "Partial1":
            tp2_pct, tp2_ticks = self.get_price_distance(
                current_price, partial2_target, direction
            )
            tp3_pct, tp3_ticks = (
                self.get_price_distance(current_price, partial3_target or 0, direction)
                if partial3_target
                else ("N/A", "N/A")
            )
            sl_pct, sl_ticks = self.get_price_distance(
                current_price, stop_price, direction
            )
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
            if partial3_target:
                status_str += f"║ Target 3 @ {partial3_target:<7.2f}  Distance: {tp3_pct} ({tp3_ticks})  ║\n"
            status_str += "║ Target 1: ✓ FILLED                             ║\n"
            status_str += "╚═══════════════════════════════════════════════╝\n"
        elif trade_stage == "Partial2":
            if partial3_target:
                tp3_pct, tp3_ticks = self.get_price_distance(
                    current_price, partial3_target, direction
                )
                sl_pct, sl_ticks = self.get_price_distance(
                    current_price, stop_price, direction
                )
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
        fixed_lines = []
        for line in status_str.split("\n"):
            if "║" in line:
                content = line.strip()
                if len(content) < 49:
                    padding = " " * (49 - len(content))
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
        self,
        entry_price,
        trade,
        stop_loss_order,
        direction,
        share_size,
        risk_amount,
        stock,
        first_target=None,
        second_target=None,
        third_target=None,
        partial1_size=None,
        partial2_size=None,
    ):
        logging.info(f"Managing {direction} trade...")
        if first_target is None:
            first_target = (
                entry_price + (1.5 * risk_amount)
                if direction == "long"
                else entry_price - (1.5 * risk_amount)
            )
        if second_target is None:
            second_target = (
                entry_price + (3 * risk_amount)
                if direction == "long"
                else entry_price - (3 * risk_amount)
            )
        if third_target is None:
            third_target = (
                entry_price + (5 * risk_amount)
                if direction == "long"
                else entry_price - (5 * risk_amount)
            )
        if partial1_size is None:
            partial1_size = math.ceil(share_size / 3)
        if partial2_size is None:
            partial2_size = math.ceil(share_size / 3)
        partial3_size = share_size - partial1_size - partial2_size
        logging.info(
            f"Profit targets - First: {first_target} ({partial1_size} shares), "
            + f"Second: {second_target} ({partial2_size} shares), "
            + f"Third: {third_target} ({partial3_size} shares)"
        )
        remaining_shares = share_size
        first_partial = False
        second_partial = False
        current_stop_price = (
            entry_price - risk_amount
            if direction == "long"
            else entry_price + risk_amount
        )
        trade_stage = "Initial"
        display_counter = 0
        start_time = time.time()
        manual_modification_check_time = time.time()
        last_price_check_time = time.time()
        time_without_progress = 0
        while remaining_shares > 0:
            portfolio = self.portfolio()
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
                    if time.time() - manual_modification_check_time > 10:
                        if actual_position_size != remaining_shares:
                            logging.info(
                                f"Position size changed from {remaining_shares} to {actual_position_size} - likely manual modification"
                            )
                            remaining_shares = actual_position_size
                        manual_modification_check_time = time.time()
            if not position_exists:
                logging.info(
                    "Position not found in portfolio. Exiting trade management."
                )
                return
            ticker = self.reqTickers(stock)[0]
            current_price = (
                ticker.marketPrice() if ticker.marketPrice() != 0 else ticker.last
            )
            elapsed_seconds = time.time() - start_time
            if "TEST_MODE" in globals() and TEST_MODE:
                if elapsed_seconds > 5 and not first_partial:
                    logging.info(
                        "TEST MODE: Simulating price movement to trigger first partial"
                    )
                    if direction == "long":
                        current_price = first_target + 0.01
                    else:
                        current_price = first_target - 0.01
                elif elapsed_seconds > 10 and first_partial and not second_partial:
                    logging.info(
                        "TEST MODE: Simulating price movement to trigger second partial"
                    )
                    if direction == "long":
                        current_price = second_target + 0.01
                    else:
                        current_price = second_target - 0.01
                elif elapsed_seconds > 15 and second_partial:
                    logging.info(
                        "TEST MODE: Simulating price movement to trigger third target"
                    )
                    if direction == "long":
                        current_price = third_target + 0.01
                    else:
                        current_price = third_target - 0.01
                elif elapsed_seconds > 20 and remaining_shares > 0:
                    logging.info(
                        "TEST MODE: Simulating price movement to trigger trailing stop"
                    )
                    if direction == "long":
                        current_price = entry_price - (2 * risk_amount)
                    else:
                        current_price = entry_price + (2 * risk_amount)
            if "TEST_MODE" not in globals() or not TEST_MODE:
                if time.time() - last_price_check_time > 60:
                    if first_partial and not second_partial:
                        target_distance = abs(second_target - current_price)
                        target_pct = target_distance / abs(second_target - first_target)
                        if target_pct > 0.8:
                            time_without_progress += 60
                        else:
                            time_without_progress = 0
                    elif second_partial:
                        target_distance = abs(third_target - current_price)
                        target_pct = target_distance / abs(third_target - second_target)
                        if target_pct > 0.8:
                            time_without_progress += 60
                        else:
                            time_without_progress = 0
                    last_price_check_time = time.time()
                    if time_without_progress > 1800 and first_partial:
                        logging.info(
                            f"No significant progress toward target for 30 minutes - tightening stop"
                        )
                        if stop_loss_order is not None:
                            self.cancelOrder(stop_loss_order)
                        new_stop_price = (
                            current_price * 0.995
                            if direction == "long"
                            else current_price * 1.005
                        )
                        stop_action = "SELL" if direction == "long" else "BUY"
                        tighter_stop = StopOrder(
                            stop_action, remaining_shares, new_stop_price
                        )
                        self.placeOrder(stock, tighter_stop)
                        stop_loss_order = tighter_stop
                        current_stop_price = new_stop_price
                        logging.info(
                            f"Time-based stop adjustment - new stop at {new_stop_price}"
                        )
                        time_without_progress = 0
            display_counter += 1
            if display_counter >= 5:
                self.display_trade_status(
                    current_price,
                    entry_price,
                    current_stop_price,
                    first_target,
                    second_target,
                    direction,
                    remaining_shares,
                    trade_stage,
                    stock,
                    partial3_target=third_target,
                )
                display_counter = 0
            if not first_partial and (
                (
                    current_price >= first_target
                    if direction == "long"
                    else current_price <= first_target
                )
            ):
                logging.info(f"First partial take profit target hit at {first_target}.")
                partial_action = "SELL" if direction == "long" else "BUY"
                partial_order1 = MarketOrder(partial_action, partial1_size)
                self.placeOrder(stock, partial_order1)
                self.cancelOrder(stop_loss_order)
                logging.info(
                    f"Partial order of {partial1_size} shares placed and initial stop loss canceled."
                )
                new_stop_price = entry_price
                stop_action = "SELL" if direction == "long" else "BUY"
                break_even_stop = StopOrder(
                    stop_action, remaining_shares - partial1_size, new_stop_price
                )
                self.placeOrder(stock, break_even_stop)
                logging.info(f"Break-even stop loss order placed at {new_stop_price}")
                remaining_shares -= partial1_size
                first_partial = True
                stop_loss_order = break_even_stop
                current_stop_price = new_stop_price
                trade_stage = "Partial1"
                self.sleep(2)
                for item in portfolio:
                    if item.contract.symbol == stock.symbol:
                        actual_size = (
                            abs(item.position)
                            if direction == "short"
                            else item.position
                        )
                        if actual_size != remaining_shares:
                            logging.info(
                                f"Position size after first partial: {actual_size}, expected {remaining_shares}"
                            )
                            remaining_shares = actual_size
            elif (
                first_partial
                and not second_partial
                and (
                    (
                        current_price >= second_target
                        if direction == "long"
                        else current_price <= second_target
                    )
                )
            ):
                logging.info(
                    f"Second partial take profit target hit at {second_target}."
                )
                partial_action = "SELL" if direction == "long" else "BUY"
                partial_order2 = MarketOrder(partial_action, partial2_size)
                self.placeOrder(stock, partial_order2)
                self.cancelOrder(stop_loss_order)
                logging.info(
                    f"Partial order of {partial2_size} shares placed and break-even stop loss canceled."
                )
                new_stop_price = (
                    entry_price + risk_amount
                    if direction == "long"
                    else entry_price - risk_amount
                )
                stop_action = "SELL" if direction == "long" else "BUY"
                profit_lock_stop = StopOrder(
                    stop_action, remaining_shares - partial2_size, new_stop_price
                )
                self.placeOrder(stock, profit_lock_stop)
                logging.info(
                    f"Profit-lock stop order placed at {new_stop_price} for remaining {remaining_shares - partial2_size} shares."
                )
                remaining_shares -= partial2_size
                second_partial = True
                stop_loss_order = profit_lock_stop
                current_stop_price = new_stop_price
                trade_stage = "Partial2"
                self.sleep(2)
                for item in portfolio:
                    if item.contract.symbol == stock.symbol:
                        actual_size = (
                            abs(item.position)
                            if direction == "short"
                            else item.position
                        )
                        if actual_size != remaining_shares:
                            logging.info(
                                f"Position size after second partial: {actual_size}, expected {remaining_shares}"
                            )
                            remaining_shares = actual_size
            elif second_partial and (
                (
                    current_price >= third_target
                    if direction == "long"
                    else current_price <= third_target
                )
            ):
                logging.info(f"Third/Final target hit at {third_target}.")
                partial_action = "SELL" if direction == "long" else "BUY"
                final_order = MarketOrder(partial_action, remaining_shares)
                self.placeOrder(stock, final_order)
                self.cancelOrder(stop_loss_order)
                logging.info(
                    f"Final order of {remaining_shares} shares placed. Exiting trade completely."
                )
                remaining_shares = 0
                trade_stage = "Complete"
            if (current_price <= current_stop_price and direction == "long") or (
                current_price >= current_stop_price and direction == "short"
            ):
                logging.info(f"Stop loss at {current_stop_price} likely triggered.")
                self.sleep(1)
                portfolio = self.portfolio()
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
                    logging.warning(
                        "Stop loss should have triggered but position still open - forcing close"
                    )
                    close_action = "SELL" if direction == "long" else "BUY"
                    close_order = MarketOrder(close_action, remaining_shares)
                    self.placeOrder(stock, close_order)
                    logging.info(
                        f"Emergency close order placed for remaining {remaining_shares} shares"
                    )
                    self.sleep(2)
                    remaining_shares = 0
                break
            if remaining_shares <= 0:
                logging.info("All shares have been sold/bought back.")
                break
            self.sleep(1)
        if "TEST_MODE" not in globals() or not TEST_MODE:
            filled_orders = self.fills()
            symbol_fills = [
                fill for fill in filled_orders if fill.contract.symbol == stock.symbol
            ]
            if symbol_fills:
                buy_value = sum(
                    fill.execution.price * fill.execution.shares
                    for fill in symbol_fills
                    if fill.execution.side == "BOT"
                )
                sell_value = sum(
                    fill.execution.price * fill.execution.shares
                    for fill in symbol_fills
                    if fill.execution.side == "SLD"
                )
                if direction == "long":
                    trade_pnl = sell_value - buy_value
                else:
                    trade_pnl = buy_value - sell_value
                r_multiple = trade_pnl / (risk_amount * share_size)
                logging.info(
                    f"Trade completed - P&L: ${trade_pnl:.2f} ({r_multiple:.2f}R)"
                )
        logging.info("Trade management complete.")
