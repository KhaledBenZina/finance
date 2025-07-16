import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

# Note: You'll need to install: pip install ibapi pandas numpy
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.ticktype import TickTypeEnum

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradingSignal:
    symbol: str
    signal_type: SignalType
    confidence: float
    price: float
    reasoning: str
    timestamp: datetime
    indicators: Dict[str, float] = field(default_factory=dict)


@dataclass
class MarketData:
    symbol: str
    timestamp: datetime
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0


class TechnicalIndicators:
    """Calculate various technical indicators for trading decisions"""

    @staticmethod
    def sma(prices: List[float], period: int) -> Optional[float]:
        """Simple Moving Average"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    @staticmethod
    def ema(prices: List[float], period: int) -> Optional[float]:
        """Exponential Moving Average"""
        if len(prices) < period:
            return None

        alpha = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema

    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """Relative Strength Index"""
        if len(prices) < period + 1:
            return None

        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def bollinger_bands(
        prices: List[float], period: int = 20, std_dev: float = 2
    ) -> Optional[Tuple[float, float, float]]:
        """Bollinger Bands (upper, middle, lower)"""
        if len(prices) < period:
            return None

        recent_prices = prices[-period:]
        sma = sum(recent_prices) / period
        variance = sum((p - sma) ** 2 for p in recent_prices) / period
        std = variance**0.5

        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)

        return upper, sma, lower

    @staticmethod
    def macd(
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> Optional[Tuple[float, float, float]]:
        """MACD (MACD line, Signal line, Histogram)"""
        if len(prices) < slow_period:
            return None

        ema_fast = TechnicalIndicators.ema(prices, fast_period)
        ema_slow = TechnicalIndicators.ema(prices, slow_period)

        if ema_fast is None or ema_slow is None:
            return None

        macd_line = ema_fast - ema_slow

        # For signal line, we'd need historical MACD values
        # Simplified version here
        signal_line = macd_line * 0.8  # Simplified
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram


class TradingStrategy:
    """Main trading strategy logic"""

    def __init__(self, risk_tolerance: float = 0.02):
        self.risk_tolerance = risk_tolerance
        self.min_confidence = 0.65

    def analyze_market_data(
        self,
        symbol: str,
        price_history: List[float],
        current_data: MarketData,
        level2_data: Dict = None,
    ) -> TradingSignal:
        """Analyze market data and generate trading signals"""

        if len(price_history) < 50:  # Need enough data for analysis
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                price=current_data.last,
                reasoning="Insufficient data for analysis",
                timestamp=datetime.now(),
            )

        # Calculate technical indicators
        sma_20 = TechnicalIndicators.sma(price_history, 20)
        sma_50 = TechnicalIndicators.sma(price_history, 50)
        ema_12 = TechnicalIndicators.ema(price_history, 12)
        rsi = TechnicalIndicators.rsi(price_history)
        bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(
            price_history
        ) or (0, 0, 0)

        # Current price
        current_price = current_data.last

        # Initialize signal components
        signals = []
        confidence_factors = []
        reasoning_parts = []

        # Moving Average Crossover Strategy
        if sma_20 and sma_50:
            if sma_20 > sma_50 and current_price > sma_20:
                signals.append(SignalType.BUY)
                confidence_factors.append(0.3)
                reasoning_parts.append("MA crossover bullish")
            elif sma_20 < sma_50 and current_price < sma_20:
                signals.append(SignalType.SELL)
                confidence_factors.append(0.3)
                reasoning_parts.append("MA crossover bearish")

        # RSI Strategy
        if rsi:
            if rsi < 30:  # Oversold
                signals.append(SignalType.BUY)
                confidence_factors.append(0.25)
                reasoning_parts.append(f"RSI oversold ({rsi:.1f})")
            elif rsi > 70:  # Overbought
                signals.append(SignalType.SELL)
                confidence_factors.append(0.25)
                reasoning_parts.append(f"RSI overbought ({rsi:.1f})")

        # Bollinger Bands Strategy
        if bb_upper and bb_lower:
            if current_price <= bb_lower:
                signals.append(SignalType.BUY)
                confidence_factors.append(0.2)
                reasoning_parts.append("Price at lower Bollinger Band")
            elif current_price >= bb_upper:
                signals.append(SignalType.SELL)
                confidence_factors.append(0.2)
                reasoning_parts.append("Price at upper Bollinger Band")

        # Volume Analysis
        if current_data.volume > 0:
            # Simple volume spike detection (you'd want historical volume data for better analysis)
            if current_data.volume > 100000:  # High volume threshold
                confidence_factors = [cf * 1.1 for cf in confidence_factors]
                reasoning_parts.append("High volume confirmation")

        # Level 2 Data Analysis (if available)
        if level2_data:
            bid_ask_spread = current_data.ask - current_data.bid
            if bid_ask_spread > 0:
                spread_pct = bid_ask_spread / current_price
                if spread_pct < 0.001:  # Tight spread
                    confidence_factors = [cf * 1.05 for cf in confidence_factors]
                    reasoning_parts.append("Tight bid-ask spread")

        # Determine overall signal
        if not signals:
            final_signal = SignalType.HOLD
            final_confidence = 0.0
            final_reasoning = "No clear signals"
        else:
            # Count signal types
            buy_count = signals.count(SignalType.BUY)
            sell_count = signals.count(SignalType.SELL)

            if buy_count > sell_count:
                final_signal = SignalType.BUY
                final_confidence = min(sum(confidence_factors), 1.0)
            elif sell_count > buy_count:
                final_signal = SignalType.SELL
                final_confidence = min(sum(confidence_factors), 1.0)
            else:
                final_signal = SignalType.HOLD
                final_confidence = 0.0
                reasoning_parts.append("Conflicting signals")

            final_reasoning = "; ".join(reasoning_parts)

        # Create indicators dict
        indicators = {
            "sma_20": sma_20 or 0,
            "sma_50": sma_50 or 0,
            "ema_12": ema_12 or 0,
            "rsi": rsi or 0,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "current_price": current_price,
            "volume": current_data.volume,
        }

        return TradingSignal(
            symbol=symbol,
            signal_type=final_signal,
            confidence=final_confidence,
            price=current_price,
            reasoning=final_reasoning,
            timestamp=datetime.now(),
            indicators=indicators,
        )


class IBTradingClient(EWrapper, EClient):
    """Interactive Brokers API Client"""

    def __init__(self, symbols: List[str]):
        EClient.__init__(self, self)

        self.symbols = symbols
        self.market_data = {}
        self.price_history = {}
        self.level2_data = {}
        self.strategy = TradingStrategy()

        # Initialize data structures
        for symbol in symbols:
            self.market_data[symbol] = MarketData(
                symbol=symbol, timestamp=datetime.now()
            )
            self.price_history[symbol] = deque(maxlen=200)  # Keep last 200 prices
            self.level2_data[symbol] = {}

        self.req_id = 1000
        self.contract_ids = {}

    def error(self, reqId, errorCode, errorString):
        logger.error(f"Error {errorCode}: {errorString}")

    def tickPrice(self, reqId, tickType, price, attrib):
        """Handle tick price updates"""
        symbol = self.get_symbol_from_req_id(reqId)
        if not symbol:
            return

        current_data = self.market_data[symbol]
        current_data.timestamp = datetime.now()

        if tickType == TickTypeEnum.BID:
            current_data.bid = price
        elif tickType == TickTypeEnum.ASK:
            current_data.ask = price
        elif tickType == TickTypeEnum.LAST:
            current_data.last = price
            self.price_history[symbol].append(price)

            # Generate trading signal when we get a new last price
            if len(self.price_history[symbol]) >= 20:
                self.generate_trading_signal(symbol)
        elif tickType == TickTypeEnum.HIGH:
            current_data.high = price
        elif tickType == TickTypeEnum.LOW:
            current_data.low = price
        elif tickType == TickTypeEnum.OPEN:
            current_data.open = price

    def tickSize(self, reqId, tickType, size):
        """Handle tick size updates"""
        symbol = self.get_symbol_from_req_id(reqId)
        if not symbol:
            return

        if tickType == TickTypeEnum.VOLUME:
            self.market_data[symbol].volume = size

    def get_symbol_from_req_id(self, req_id: int) -> Optional[str]:
        """Get symbol from request ID"""
        for symbol, stored_req_id in self.contract_ids.items():
            if stored_req_id == req_id:
                return symbol
        return None

    def create_contract(self, symbol: str, exchange: str = "SMART") -> Contract:
        """Create a contract for the given symbol"""
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = "USD"
        return contract

    def start_data_feeds(self):
        """Start market data feeds for all symbols"""
        for symbol in self.symbols:
            contract = self.create_contract(symbol)
            req_id = self.req_id
            self.contract_ids[symbol] = req_id

            # Request market data
            self.reqMktData(req_id, contract, "", False, False, [])

            # Request level 2 data
            self.reqMktDepth(req_id + 1000, contract, 10, False, [])

            self.req_id += 1

            logger.info(f"Started data feed for {symbol} with req_id {req_id}")

    def generate_trading_signal(self, symbol: str):
        """Generate and print trading signal"""
        price_list = list(self.price_history[symbol])
        current_data = self.market_data[symbol]
        level2 = self.level2_data.get(symbol, {})

        signal = self.strategy.analyze_market_data(
            symbol, price_list, current_data, level2
        )

        if signal.confidence >= self.strategy.min_confidence:
            self.print_trading_decision(signal)

    def print_trading_decision(self, signal: TradingSignal):
        """Print trading decision to console"""
        print("\n" + "=" * 80)
        print(f"🚨 TRADING SIGNAL: {signal.symbol}")
        print(f"⏰ Time: {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 Signal: {signal.signal_type.value}")
        print(f"💪 Confidence: {signal.confidence:.2%}")
        print(f"💰 Price: ${signal.price:.2f}")
        print(f"📝 Reasoning: {signal.reasoning}")
        print(f"📈 Indicators:")
        for key, value in signal.indicators.items():
            if isinstance(value, float):
                print(f"   {key}: {value:.2f}")
            else:
                print(f"   {key}: {value}")
        print("=" * 80)

        # Add emoji based on signal type
        if signal.signal_type == SignalType.BUY:
            print("🟢 RECOMMENDATION: Consider BUYING")
        elif signal.signal_type == SignalType.SELL:
            print("🔴 RECOMMENDATION: Consider SELLING")
        else:
            print("⚪ RECOMMENDATION: HOLD")

        print("=" * 80 + "\n")


def main():
    """Main function to run the trading system"""

    # Configuration
    SYMBOLS = ["AAPL", "GOOGL", "MSFT", "TSLA", "SPY"]  # Add your preferred symbols
    IB_HOST = "127.0.0.1"
    IB_PORT = 7497  # Use 7496 for live trading, 7497 for paper trading
    CLIENT_ID = 1

    print("🚀 Starting Live Trading Decision System...")
    print(f"📊 Monitoring symbols: {', '.join(SYMBOLS)}")
    print(f"🔗 Connecting to IB TWS at {IB_HOST}:{IB_PORT}")
    print("=" * 80)

    # Create and start the trading client
    app = IBTradingClient(SYMBOLS)

    try:
        # Connect to IB
        app.connect(IB_HOST, IB_PORT, CLIENT_ID)

        # Start the socket in a separate thread
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()

        # Wait for connection
        time.sleep(2)

        # Start data feeds
        app.start_data_feeds()

        print("✅ System started successfully!")
        print("💡 Trading signals will appear below when conditions are met...")
        print("❌ Press Ctrl+C to stop the system")
        print("=" * 80)

        # Keep the main thread alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping trading system...")
        app.disconnect()
        print("✅ System stopped successfully!")

    except Exception as e:
        logger.error(f"Error in main: {e}")
        app.disconnect()


if __name__ == "__main__":
    main()
