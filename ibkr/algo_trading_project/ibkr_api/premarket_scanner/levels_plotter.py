#!/usr/bin/env python3
"""
Support and Resistance Levels Plotter for TWS (Synchronous Version)
Automatically plots key trading levels on Interactive Brokers charts

Requirements:
pip install ib_insync pandas numpy
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import logging
from typing import List, Dict, Tuple, Optional
import time

from ib_insync import *

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class LevelsPlotter:
    def __init__(self, host='127.0.0.1', port=7497, client_id=2):
        """
        Initialize the levels plotter

        Args:
            host: TWS/Gateway host
            port: TWS/Gateway port
            client_id: Base client ID
        """
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.connected = False

        # Chart configuration
        self.chart_id = None
        self.drawn_lines = []  # Track drawn lines for cleanup

        # Level colors (RGB format)
        self.colors = {
            'pivot': (255, 215, 0),  # Gold
            'support': (0, 255, 0),  # Green
            'resistance': (255, 0, 0),  # Red
            'vwap': (138, 43, 226),  # Blue Violet
            'moving_avg': (255, 165, 0),  # Orange
            'fibonacci': (255, 20, 147),  # Deep Pink
            'previous': (169, 169, 169),  # Dark Gray
            'volume_level': (0, 255, 255)  # Cyan
        }

    def connect(self):
        """Connect to TWS/Gateway"""
        try:
            # Try to disconnect first if already connected
            if self.ib.isConnected():
                self.ib.disconnect()
                time.sleep(1)

            # Find available client ID
            for attempt in range(10):
                try:
                    self.ib.connect(self.host, self.port, clientId=self.client_id + attempt)
                    self.connected = True
                    logger.info(
                        f"Connected to TWS at {self.host}:{self.port} with client ID {self.client_id + attempt}")
                    return True
                except Exception as e:
                    if "already connected" in str(e).lower() or "duplicate" in str(e).lower():
                        continue
                    else:
                        logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                        time.sleep(1)

            logger.error("Failed to connect after 10 attempts")
            return False

        except Exception as e:
            logger.error(f"Failed to connect to TWS: {e}")
            return False

    def disconnect(self):
        """Properly disconnect from TWS"""
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info("Disconnected from TWS")
            self.connected = False
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")

    def get_historical_data(self, contract: Contract, duration: str = '30 D',
                            bar_size: str = '1 day') -> pd.DataFrame:
        """Get historical data for calculations"""
        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )

            if not bars:
                logger.error(f"No historical data received for {contract.symbol}")
                return pd.DataFrame()

            df = util.df(bars)
            df['date'] = pd.to_datetime(df['date'])
            return df

        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            return pd.DataFrame()

    def calculate_pivot_points(self, high: float, low: float, close: float) -> Dict[str, float]:
        """Calculate standard pivot points"""
        pivot = (high + low + close) / 3

        levels = {
            'PP': pivot,  # Pivot Point
            'R1': 2 * pivot - low,
            'R2': pivot + (high - low),
            'R3': high + 2 * (pivot - low),
            'S1': 2 * pivot - high,
            'S2': pivot - (high - low),
            'S3': low - 2 * (high - pivot)
        }

        return levels

    def calculate_camarilla_pivots(self, high: float, low: float, close: float) -> Dict[str, float]:
        """Calculate Camarilla pivot points"""
        range_hl = high - low

        levels = {
            'PP': close,
            'R1': close + range_hl * 1.1 / 12,
            'R2': close + range_hl * 1.1 / 6,
            'R3': close + range_hl * 1.1 / 4,
            'R4': close + range_hl * 1.1 / 2,
            'S1': close - range_hl * 1.1 / 12,
            'S2': close - range_hl * 1.1 / 6,
            'S3': close - range_hl * 1.1 / 4,
            'S4': close - range_hl * 1.1 / 2
        }

        return levels

    def get_previous_day_levels(self, df: pd.DataFrame) -> Dict[str, float]:
        """Get previous day's key horizontal levels"""
        levels = {}

        if len(df) >= 2:
            # Previous day levels
            prev_day = df.iloc[-2]
            levels['Prev_High'] = prev_day['high']
            levels['Prev_Low'] = prev_day['low']
            levels['Prev_Close'] = prev_day['close']
            levels['Prev_Open'] = prev_day['open']

            # Previous day mid-point
            levels['Prev_Mid'] = (prev_day['high'] + prev_day['low']) / 2

        return levels

    def get_period_highs_lows(self, df: pd.DataFrame) -> Dict[str, float]:
        """Get key period highs and lows (horizontal levels only)"""
        levels = {}

        if len(df) >= 5:
            # Previous week high/low (5 trading days)
            week_data = df.tail(6)[:-1]  # Exclude current day
            levels['Week_High'] = week_data['high'].max()
            levels['Week_Low'] = week_data['low'].min()

        if len(df) >= 20:
            # Previous month high/low (20 trading days)
            month_data = df.tail(21)[:-1]  # Exclude current day
            levels['Month_High'] = month_data['high'].max()
            levels['Month_Low'] = month_data['low'].min()

        if len(df) >= 50:
            # 50-day high/low
            data_50d = df.tail(51)[:-1]  # Exclude current day
            levels['50D_High'] = data_50d['high'].max()
            levels['50D_Low'] = data_50d['low'].min()

        return levels

    def calculate_all_levels(self, symbol: str) -> Dict[str, Dict[str, float]]:
        """Calculate horizontal support/resistance levels for a symbol"""
        # Create contract
        contract = Stock(symbol, 'SMART', 'USD')

        # Get historical data
        daily_df = self.get_historical_data(contract, '60 D', '1 day')
        if daily_df.empty:
            logger.error(f"No daily data for {symbol}")
            return {}

        # Use latest daily data for pivot calculations
        latest = daily_df.iloc[-1]
        prev_day = daily_df.iloc[-2] if len(daily_df) > 1 else latest

        all_levels = {}

        # 1. Camarilla Pivot Points (Primary focus)
        cam_pivots = self.calculate_camarilla_pivots(
            prev_day['high'], prev_day['low'], prev_day['close']
        )
        all_levels['Camarilla_Pivots'] = cam_pivots

        # 2. Previous Day Levels (Essential horizontal levels)
        prev_levels = self.get_previous_day_levels(daily_df)
        all_levels['Previous_Day_Levels'] = prev_levels

        # 3. Standard Pivot Points (Secondary)
        pivots = self.calculate_pivot_points(
            prev_day['high'], prev_day['low'], prev_day['close']
        )
        all_levels['Standard_Pivots'] = pivots

        # 4. Previous Week/Month Highs/Lows (Key horizontal levels)
        period_levels = self.get_period_highs_lows(daily_df)
        if period_levels:
            all_levels['Period_Levels'] = period_levels

        return all_levels

    def create_horizontal_line(self, price: float, label: str, color: Tuple[int, int, int],
                               line_style: str = 'SOLID') -> None:
        """Create a horizontal line on the chart (placeholder for TWS implementation)"""
        # Note: TWS API doesn't directly support drawing lines programmatically
        # This would need to be implemented using TWS's chart annotation features
        # or by using the Chart API if available

        logger.info(f"Would draw line at {price:.2f} - {label} ({color})")

        # In a real implementation, you would use:
        # 1. TWS Chart API if available
        # 2. Send drawing commands to TWS
        # 3. Use TWS automation tools

        # For now, we'll store the line data
        line_data = {
            'price': price,
            'label': label,
            'color': color,
            'style': line_style,
            'timestamp': datetime.now()
        }

        self.drawn_lines.append(line_data)

    def clear_all_lines(self):
        """Clear all drawn lines"""
        self.drawn_lines.clear()
        logger.info("Cleared all drawn lines")

    def plot_levels_for_symbol(self, symbol: str, level_types: List[str] = None):
        """Plot horizontal levels for a given symbol"""
        if level_types is None:
            # Default to horizontal levels only
            level_types = ['Camarilla_Pivots', 'Previous_Day_Levels', 'Standard_Pivots', 'Period_Levels']

        logger.info(f"Plotting horizontal levels for {symbol}")

        # Calculate all levels
        all_levels = self.calculate_all_levels(symbol)
        if not all_levels:
            logger.error(f"No levels calculated for {symbol}")
            return

        # Clear existing lines
        self.clear_all_lines()

        # Plot each type of level
        for level_type in level_types:
            if level_type not in all_levels:
                continue

            levels = all_levels[level_type]
            color = self.get_color_for_level_type(level_type)

            for level_name, price in levels.items():
                if pd.isna(price) or price <= 0:
                    continue

                label = f"{level_type}: {level_name}"
                self.create_horizontal_line(price, label, color)

        logger.info(f"Plotted {len(self.drawn_lines)} horizontal levels for {symbol}")

        # Print summary
        self.print_levels_summary(symbol, all_levels)

    def get_color_for_level_type(self, level_type: str) -> Tuple[int, int, int]:
        """Get color for a specific level type"""
        color_map = {
            'Camarilla_Pivots': self.colors['pivot'],  # Gold - Primary pivots
            'Previous_Day_Levels': self.colors['previous'],  # Dark Gray - Previous day
            'Standard_Pivots': self.colors['support'],  # Green - Standard pivots
            'Period_Levels': self.colors['resistance']  # Red - Weekly/Monthly levels
        }

        return color_map.get(level_type, self.colors['support'])

    def print_levels_summary(self, symbol: str, all_levels: Dict):
        """Print a summary of all calculated levels"""
        print(f"\n{'=' * 60}")
        print(f"SUPPORT/RESISTANCE LEVELS FOR {symbol}")
        print(f"{'=' * 60}")
        print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        for level_type, levels in all_levels.items():
            print(f"📊 {level_type.replace('_', ' ').upper()}")
            print("-" * 40)

            sorted_levels = sorted(levels.items(), key=lambda x: x[1], reverse=True)

            for name, price in sorted_levels:
                if pd.isna(price) or price <= 0:
                    continue

                level_char = "🔴" if "R" in name or "High" in name else "🟢" if "S" in name or "Low" in name else "🔵"
                print(f"  {level_char} {name:<15}: ${price:>8.2f}")

            print()

    def export_levels_to_csv(self, symbol: str, all_levels: Dict):
        """Export levels to CSV file"""
        data = []

        for level_type, levels in all_levels.items():
            for name, price in levels.items():
                if pd.isna(price) or price <= 0:
                    continue

                data.append({
                    'Symbol': symbol,
                    'Level_Type': level_type,
                    'Level_Name': name,
                    'Price': price,
                    'Timestamp': datetime.now()
                })

        if data:
            df = pd.DataFrame(data)
            filename = f"levels_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(filename, index=False)
            logger.info(f"Levels exported to {filename}")


class MultiSymbolLevelsPlotter:
    """Plot levels for multiple symbols"""

    def __init__(self, host='127.0.0.1', port=7497, client_id=2):
        self.plotter = LevelsPlotter(host, port, client_id)
        self.watchlist = []

    def add_symbols_from_scanner_results(self, csv_file: str):
        """Add symbols from pre-market scanner results"""
        try:
            df = pd.read_csv(csv_file)
            symbols = df['symbol'].head(10).tolist()  # Top 10 from scanner
            self.watchlist.extend(symbols)
            logger.info(f"Added {len(symbols)} symbols from scanner results")
        except Exception as e:
            logger.error(f"Error reading scanner results: {e}")

    def add_symbols(self, symbols: List[str]):
        """Add symbols manually"""
        self.watchlist.extend(symbols)

    def plot_all_symbols(self):
        """Plot levels for all symbols in watchlist"""
        if not self.plotter.connect():
            logger.error("Failed to connect to TWS")
            return

        try:
            for symbol in self.watchlist:
                logger.info(f"Processing {symbol}...")
                self.plotter.plot_levels_for_symbol(symbol)
                time.sleep(1)  # Small delay between symbols

        finally:
            self.plotter.disconnect()


def main():
    """Main function"""
    # Example usage
    plotter = LevelsPlotter()

    if not plotter.connect():
        print("Failed to connect to TWS. Make sure TWS/Gateway is running.")
        return

    try:
        # Plot levels for a specific symbol
        symbol = input("Enter symbol to plot levels (default: AAPL): ").strip().upper()
        if not symbol:
            symbol = "AAPL"

        plotter.plot_levels_for_symbol(symbol)

        # Export to CSV
        all_levels = plotter.calculate_all_levels(symbol)
        if all_levels:
            plotter.export_levels_to_csv(symbol, all_levels)

        # Multi-symbol example
        print("\nFor multiple symbols from watchlist:")
        multi_plotter = MultiSymbolLevelsPlotter()

        # Add some popular day trading stocks
        multi_plotter.add_symbols(['TSLA', 'AMD', 'NVDA', 'SPY', 'QQQ'])

        # Plot all
        multi_plotter.plot_all_symbols()

    finally:
        plotter.disconnect()


if __name__ == "__main__":
    main()