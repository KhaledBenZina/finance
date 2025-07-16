#!/usr/bin/env python3
"""
Pre-Market Stock Scanner for Day Trading
Identifies stocks with high volume and volatility potential

Requirements:
pip install ib_insync pandas numpy yfinance requests beautifulsoup4
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
from typing import List, Dict, Tuple
import yfinance as yf
import requests
from bs4 import BeautifulSoup

from ib_insync import *

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PreMarketScanner:
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        """
        Initialize the pre-market scanner

        Args:
            host: TWS/Gateway host
            port: TWS/Gateway port (7497 for TWS, 7496 for Gateway)
            client_id: Unique client ID
        """
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id

        # Scanner criteria
        self.min_price = 5.0
        self.max_price = 500.0
        self.min_market_cap = 1e9  # 1B minimum market cap
        self.min_avg_volume = 1e6  # 1M average volume
        self.min_relative_volume = 2.0  # 2x normal volume
        self.min_gap_percent = 2.0  # 2% gap minimum

    async def connect(self):
        """Connect to TWS/Gateway"""
        try:
            await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
            logger.info(f"Connected to TWS at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to TWS: {e}")
            return False

    def disconnect(self):
        """Disconnect from TWS"""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from TWS")

    async def get_market_scanner_data(self) -> List[Dict]:
        """Get stocks using IB's market scanner"""
        scanner = ScannerSubscription(
            instrument='STK',
            locationCode='STK.US.MAJOR',
            scanCode='TOP_PERC_GAIN'  # Top percentage gainers
        )

        scanner_data = await self.ib.reqScannerSubscriptionAsync(scanner)

        results = []
        for item in scanner_data[:50]:  # Limit to top 50
            contract = item.contractDetails.contract
            results.append({
                'symbol': contract.symbol,
                'price': item.marketDataSnapshot.last if item.marketDataSnapshot else None,
                'volume': item.marketDataSnapshot.volume if item.marketDataSnapshot else None,
                'change_pct': item.marketDataSnapshot.changePercent if item.marketDataSnapshot else None
            })

        return results

    def get_premarket_movers(self) -> List[str]:
        """Scrape pre-market movers from various sources"""
        symbols = set()

        try:
            # MarketWatch pre-market movers
            url = "https://www.marketwatch.com/tools/screener/premarket"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # Parse ticker symbols from the page
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/investing/stock/' in href:
                        symbol = href.split('/')[-1].upper()
                        if len(symbol) <= 5 and symbol.isalpha():
                            symbols.add(symbol)
        except Exception as e:
            logger.warning(f"Error scraping pre-market movers: {e}")

        # Add some common high-volume stocks
        common_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            'AMD', 'BABA', 'DIS', 'BA', 'JPM', 'GS', 'SHOP', 'SQ', 'ROKU',
            'ZOOM', 'PTON', 'GME', 'AMC', 'BB', 'NOK', 'PLTR', 'SPCE'
        ]
        symbols.update(common_tickers)

        return list(symbols)

    async def analyze_stock(self, symbol: str) -> Dict:
        """Analyze a single stock for day trading potential"""
        try:
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')

            # Get contract details
            contract_details = await self.ib.reqContractDetailsAsync(contract)
            if not contract_details:
                return None

            contract = contract_details[0].contract

            # Get current market data
            ticker = self.ib.reqMktData(contract, '', False, False)
            await asyncio.sleep(1)  # Wait for data

            # Get historical data for analysis
            bars = await self.ib.reqHistoricalDataAsync(
                contract,
                endDateTime='',
                durationStr='30 D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )

            if len(bars) < 10:
                return None

            # Calculate metrics
            df = util.df(bars)
            current_price = ticker.marketPrice() or ticker.close
            prev_close = df.iloc[-2]['close'] if len(df) > 1 else df.iloc[-1]['close']

            # Calculate average volume (20 days)
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = ticker.volume or 0
            relative_volume = current_volume / avg_volume if avg_volume > 0 else 0

            # Calculate gap percentage
            gap_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

            # Calculate ATR (14 days)
            df['high_low'] = df['high'] - df['low']
            df['high_close'] = abs(df['high'] - df['close'].shift(1))
            df['low_close'] = abs(df['low'] - df['close'].shift(1))
            df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
            atr = df['true_range'].rolling(14).mean().iloc[-1]

            # Calculate volatility score
            price_changes = df['close'].pct_change().dropna()
            volatility = price_changes.std() * 100

            # Volume profile analysis
            volume_profile = self.calculate_volume_profile(df)

            analysis = {
                'symbol': symbol,
                'current_price': round(current_price, 2),
                'prev_close': round(prev_close, 2),
                'gap_percent': round(gap_percent, 2),
                'current_volume': current_volume,
                'avg_volume': int(avg_volume),
                'relative_volume': round(relative_volume, 2),
                'atr': round(atr, 2),
                'atr_percent': round((atr / current_price) * 100, 2),
                'volatility': round(volatility, 2),
                'market_cap': self.estimate_market_cap(contract_details[0]),
                'volume_profile': volume_profile,
                'score': self.calculate_trading_score(gap_percent, relative_volume, volatility, atr, current_price)
            }

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None

    def calculate_volume_profile(self, df: pd.DataFrame) -> Dict:
        """Calculate volume profile for recent sessions"""
        if len(df) < 5:
            return {}

        recent_df = df.tail(5)

        # Calculate VWAP levels
        vwap = (recent_df['close'] * recent_df['volume']).sum() / recent_df['volume'].sum()

        # High volume areas
        max_volume_day = recent_df.loc[recent_df['volume'].idxmax()]

        return {
            'vwap': round(vwap, 2),
            'high_volume_price': round(max_volume_day['close'], 2),
            'high_volume_level': int(max_volume_day['volume'])
        }

    def estimate_market_cap(self, contract_details) -> float:
        """Estimate market cap from contract details"""
        # This is a simplified estimation
        # In practice, you'd want to get this from fundamental data
        return 1e9  # Default to 1B

    def calculate_trading_score(self, gap_percent: float, relative_volume: float,
                                volatility: float, atr: float, price: float) -> float:
        """Calculate a trading score based on multiple factors"""
        score = 0

        # Gap score (higher gaps = higher score)
        if abs(gap_percent) > 5:
            score += 30
        elif abs(gap_percent) > 3:
            score += 20
        elif abs(gap_percent) > 1:
            score += 10

        # Relative volume score
        if relative_volume > 3:
            score += 25
        elif relative_volume > 2:
            score += 15
        elif relative_volume > 1.5:
            score += 10

        # Volatility score
        if volatility > 5:
            score += 20
        elif volatility > 3:
            score += 15
        elif volatility > 2:
            score += 10

        # ATR score (prefer reasonable ATR)
        atr_percent = (atr / price) * 100
        if 2 <= atr_percent <= 8:
            score += 15
        elif 1 <= atr_percent < 2 or 8 < atr_percent <= 12:
            score += 10

        # Price range preference
        if 10 <= price <= 200:
            score += 10
        elif 5 <= price < 10 or 200 < price <= 300:
            score += 5

        return score

    async def scan_stocks(self, symbols: List[str] = None) -> pd.DataFrame:
        """Scan multiple stocks and return ranked results"""
        if symbols is None:
            symbols = self.get_premarket_movers()

        logger.info(f"Scanning {len(symbols)} stocks...")

        results = []
        for i, symbol in enumerate(symbols):
            try:
                analysis = await self.analyze_stock(symbol)
                if analysis and analysis['score'] > 20:  # Minimum score threshold
                    results.append(analysis)
                    logger.info(f"Analyzed {symbol} - Score: {analysis['score']}")

                # Rate limiting
                if i % 10 == 0:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue

        if not results:
            return pd.DataFrame()

        # Convert to DataFrame and sort by score
        df = pd.DataFrame(results)
        df = df.sort_values('score', ascending=False)

        # Filter by criteria
        df = df[
            (df['current_price'] >= self.min_price) &
            (df['current_price'] <= self.max_price) &
            (df['avg_volume'] >= self.min_avg_volume) &
            (df['relative_volume'] >= self.min_relative_volume) &
            (abs(df['gap_percent']) >= self.min_gap_percent)
            ]

        return df

    def print_results(self, df: pd.DataFrame):
        """Print formatted scan results"""
        if df.empty:
            print("No stocks found matching criteria")
            return

        print("\n" + "=" * 80)
        print("PRE-MARKET STOCK SCANNER RESULTS")
        print("=" * 80)
        print(f"Scan completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Found {len(df)} potential day trading candidates")
        print("\n")

        for _, row in df.head(20).iterrows():
            print(f"🎯 {row['symbol']:<6} | Score: {row['score']:>3.0f}")
            print(f"   Price: ${row['current_price']:>7.2f} | Gap: {row['gap_percent']:>+6.2f}%")
            print(f"   Volume: {row['relative_volume']:>4.1f}x avg | ATR: {row['atr_percent']:>4.1f}%")
            print(f"   VWAP: ${row['volume_profile'].get('vwap', 0):>7.2f}")
            print("-" * 50)


async def main():
    """Main function to run the scanner"""
    scanner = PreMarketScanner()

    # Connect to TWS
    if not await scanner.connect():
        print("Failed to connect to TWS. Make sure TWS/Gateway is running.")
        return

    try:
        # Run the scan
        results = await scanner.scan_stocks()
        scanner.print_results(results)

        # Save results to CSV
        if not results.empty:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"premarket_scan_{timestamp}.csv"
            results.to_csv(filename, index=False)
            print(f"\nResults saved to: {filename}")

    finally:
        scanner.disconnect()


if __name__ == "__main__":
    asyncio.run(main())