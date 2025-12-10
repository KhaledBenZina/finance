"""
5min ORB (Opening Range Breakout) Scanner with VWAP Confirmation
Analyzes tickers for the best ORB setups with VWAP confirmation
Fetches live data from IBKR TWS API
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Global IB connection (same pattern as fetch_ibkr.py)
ib = None

# TICKERS list
TICKERS = [
    "AAPL",
    "TSLA",
    "NVDA",
    "AMD",
    "PLTR",
    "META",
    "GOOGL",
    "AMZN",
    "MSFT",
    "NFLX",
    "TSM",
]


def get_ib_connection(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    timeout: int = 10,
):
    """
    Get or create IBKR connection (same pattern as fetch_ibkr.py)
    Patches asyncio event loop policy to handle Streamlit threading issues
    """
    global ib
    import asyncio

    if ib is None:
        # Patch the event loop policy to handle RuntimeError in Streamlit
        # eventkit calls get_event_loop_policy().get_event_loop() directly
        original_policy = asyncio.get_event_loop_policy()
        original_get_event_loop = original_policy.get_event_loop

        def patched_get_event_loop():
            try:
                return original_get_event_loop()
            except RuntimeError:
                # No event loop in this thread - create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop

        # Patch the policy's get_event_loop method
        original_policy.get_event_loop = patched_get_event_loop

        try:
            # Now import ib_insync - it should work
            from ib_insync import IB

            ib = IB()
            ib.connect(host, port, clientId=client_id, timeout=timeout)
        finally:
            # Restore original method
            original_policy.get_event_loop = original_get_event_loop

    return ib


def fetch_today_data(ticker: str, ib_connection=None) -> Optional[pd.DataFrame]:
    """
    Fetch today's 1-minute data for a ticker from IBKR TWS
    Uses the same pattern as fetch_ibkr.py
    """
    from ib_insync import Stock, util

    if ib_connection is None:
        ib_connection = get_ib_connection()

    # Verify connection is still valid
    if not ib_connection.isConnected():
        raise ConnectionError("IBKR connection is not active. Please reconnect.")

    try:
        # Create contract (same as fetch_ibkr.py)
        contract = Stock(ticker, "SMART", "USD")

        # Request today's data - empty endDateTime means "now"
        # Use "1 D" duration to get today's data (same pattern as fetch_ibkr.py)
        bars = ib_connection.reqHistoricalData(
            contract,
            endDateTime="",  # Empty means current time
            durationStr="1 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True,  # Regular trading hours only
            formatDate=1,
            keepUpToDate=False,
        )

        if not bars:
            return None

        # Convert to DataFrame
        df = util.df(bars)

        if df.empty:
            return None

        # Rename date column to datetime
        if "date" in df.columns:
            df.rename(columns={"date": "datetime"}, inplace=True)

        # Ensure datetime is datetime type and set as index
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()

        # Filter to regular trading hours (9:30 AM - 4:00 PM ET)
        df = df.between_time("09:30", "16:00")

        # Return only OHLCV columns
        required_cols = ["open", "high", "low", "close", "volume"]
        if all(col in df.columns for col in required_cols):
            return df[required_cols]
        else:
            return None

    except Exception as e:
        print(f"Error fetching data for {ticker} from IBKR: {e}")
        return None


def resample_to_5min(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-minute data to 5-minute bars"""
    if df.empty:
        return df

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    df_5min = df.resample("5T").agg(agg).dropna()
    return df_5min


def compute_vwap(
    df: pd.DataFrame, anchor_time: Optional[pd.Timestamp] = None
) -> pd.Series:
    """
    Compute VWAP anchored from market open or specified anchor time
    Uses typical price: (high + low + close) / 3
    """
    if df.empty:
        return pd.Series(dtype=float)

    # Determine anchor point
    if anchor_time is None:
        anchor_time = df.index[0] if len(df) > 0 else None

    if anchor_time is None:
        return pd.Series(dtype=float)

    # Filter data from anchor onwards
    df_anchor = df.loc[df.index >= anchor_time].copy()

    if df_anchor.empty:
        return pd.Series(dtype=float)

    # Calculate typical price
    df_anchor["typ_price"] = (
        df_anchor["high"] + df_anchor["low"] + df_anchor["close"]
    ) / 3.0

    # Cumulative calculations
    df_anchor["cum_typ_vol"] = (df_anchor["typ_price"] * df_anchor["volume"]).cumsum()
    df_anchor["cum_vol"] = df_anchor["volume"].cumsum()

    # VWAP = cumulative (typical price * volume) / cumulative volume
    vwap = df_anchor["cum_typ_vol"] / df_anchor["cum_vol"]

    # Merge back to full dataframe (NaN before anchor)
    result = pd.Series(index=df.index, dtype=float)
    result.loc[df_anchor.index] = vwap

    return result


def calculate_orb_range(df_5min: pd.DataFrame) -> Optional[Dict]:
    """
    Calculate 5-minute opening range (first 5-minute bar: 9:30-9:35)
    Returns: dict with orb_high, orb_low, orb_range, orb_mid
    """
    if df_5min.empty or len(df_5min) < 1:
        return None

    # First 5-minute bar (9:30-9:35)
    first_bar = df_5min.iloc[0]

    orb_high = first_bar["high"]
    orb_low = first_bar["low"]
    orb_range = orb_high - orb_low
    orb_mid = (orb_high + orb_low) / 2

    return {
        "orb_high": orb_high,
        "orb_low": orb_low,
        "orb_range": orb_range,
        "orb_range_pct": (orb_range / orb_mid * 100) if orb_mid > 0 else 0,
        "orb_mid": orb_mid,
    }


def check_breakout(
    df_5min: pd.DataFrame, orb_high: float, orb_low: float
) -> Optional[Dict]:
    """
    Check if there's been a breakout from the ORB range
    Returns: dict with breakout info
    """
    if df_5min.empty or len(df_5min) < 2:
        return None

    # Check bars after the first one (after 9:35)
    breakout_bars = df_5min.iloc[1:]

    # Check for bullish breakout (price breaks above ORB high)
    bullish_breakouts = breakout_bars[breakout_bars["high"] > orb_high]
    # Check for bearish breakout (price breaks below ORB low)
    bearish_breakouts = breakout_bars[breakout_bars["low"] < orb_low]

    latest_bar = df_5min.iloc[-1]
    current_price = latest_bar["close"]

    # Determine breakout status
    has_bullish_breakout = not bullish_breakouts.empty
    has_bearish_breakout = not bearish_breakouts.empty

    breakout_direction = None
    breakout_time = None
    breakout_price = None

    if has_bullish_breakout:
        first_bullish = bullish_breakouts.iloc[0]
        breakout_direction = "BULLISH"
        breakout_time = first_bullish.name
        breakout_price = first_bullish["high"]
    elif has_bearish_breakout:
        first_bearish = bearish_breakouts.iloc[0]
        breakout_direction = "BEARISH"
        breakout_time = first_bearish.name
        breakout_price = first_bearish["low"]

    # Current position relative to ORB
    if current_price > orb_high:
        position = "ABOVE_HIGH"
    elif current_price < orb_low:
        position = "BELOW_LOW"
    else:
        position = "INSIDE_RANGE"

    return {
        "has_breakout": has_bullish_breakout or has_bearish_breakout,
        "breakout_direction": breakout_direction,
        "breakout_time": breakout_time,
        "breakout_price": breakout_price,
        "current_price": current_price,
        "position": position,
        "distance_from_high": (
            ((current_price - orb_high) / orb_high * 100) if orb_high > 0 else 0
        ),
        "distance_from_low": (
            ((current_price - orb_low) / orb_low * 100) if orb_low > 0 else 0
        ),
    }


def check_vwap_confirmation(
    df_5min: pd.DataFrame, vwap: pd.Series, breakout_direction: Optional[str]
) -> Dict:
    """
    Check VWAP confirmation for the breakout
    Returns: dict with VWAP confirmation metrics
    """
    if df_5min.empty or vwap.empty:
        return {
            "vwap_confirmed": False,
            "vwap_distance_pct": 0,
            "vwap_above_below": None,
            "current_vwap": None,
        }

    latest_bar = df_5min.iloc[-1]
    current_price = latest_bar["close"]
    current_vwap = vwap.iloc[-1]

    if pd.isna(current_vwap):
        return {
            "vwap_confirmed": False,
            "vwap_distance_pct": 0,
            "vwap_above_below": None,
            "current_vwap": None,
        }

    price_above_vwap = current_price > current_vwap
    price_below_vwap = current_price < current_vwap
    vwap_distance_pct = (
        ((current_price - current_vwap) / current_vwap * 100) if current_vwap > 0 else 0
    )

    # VWAP confirmation logic:
    # - Bullish breakout confirmed if price is above VWAP
    # - Bearish breakout confirmed if price is below VWAP
    vwap_confirmed = False
    if breakout_direction == "BULLISH" and price_above_vwap:
        vwap_confirmed = True
    elif breakout_direction == "BEARISH" and price_below_vwap:
        vwap_confirmed = True

    return {
        "vwap_confirmed": vwap_confirmed,
        "vwap_distance_pct": vwap_distance_pct,
        "vwap_above_below": (
            "ABOVE" if price_above_vwap else "BELOW" if price_below_vwap else "AT"
        ),
        "current_vwap": current_vwap,
        "current_price": current_price,
    }


def check_volume_confirmation(df_5min: pd.DataFrame) -> Dict:
    """
    Check volume confirmation - compare breakout volume to average
    Returns: dict with volume metrics
    """
    if df_5min.empty or len(df_5min) < 2:
        return {
            "volume_ok": False,
            "volume_ratio": 0,
            "avg_volume": 0,
            "breakout_volume": 0,
        }

    # First bar is ORB, check volume on subsequent bars
    orb_volume = df_5min.iloc[0]["volume"]
    breakout_bars = df_5min.iloc[1:]

    if breakout_bars.empty:
        return {
            "volume_ok": False,
            "volume_ratio": 0,
            "avg_volume": orb_volume,
            "breakout_volume": 0,
        }

    avg_volume = breakout_bars["volume"].mean()
    latest_volume = breakout_bars.iloc[-1]["volume"]

    # Volume should be above average for confirmation
    volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0
    volume_ok = volume_ratio >= 1.2  # At least 20% above average

    return {
        "volume_ok": volume_ok,
        "volume_ratio": volume_ratio,
        "avg_volume": avg_volume,
        "breakout_volume": latest_volume,
        "orb_volume": orb_volume,
    }


def calculate_setup_score(
    orb_info: Dict, breakout_info: Dict, vwap_info: Dict, volume_info: Dict
) -> float:
    """
    Calculate a quality score for the setup (0-100)
    Higher score = better setup
    """
    score = 0.0

    # Must have a breakout (40 points)
    if breakout_info and breakout_info.get("has_breakout", False):
        score += 40

        # VWAP confirmation (30 points)
        if vwap_info.get("vwap_confirmed", False):
            score += 30
        else:
            # Partial credit if VWAP is close
            vwap_dist = abs(vwap_info.get("vwap_distance_pct", 100))
            if vwap_dist < 0.5:  # Within 0.5% of VWAP
                score += 15
            elif vwap_dist < 1.0:  # Within 1% of VWAP
                score += 10

        # Volume confirmation (20 points)
        if volume_info.get("volume_ok", False):
            score += 20
        else:
            # Partial credit based on volume ratio
            vol_ratio = volume_info.get("volume_ratio", 0)
            if vol_ratio >= 1.0:
                score += 10
            elif vol_ratio >= 0.8:
                score += 5

        # ORB range quality (10 points) - larger range = better
        orb_range_pct = orb_info.get("orb_range_pct", 0)
        if orb_range_pct > 0.5:  # Range > 0.5%
            score += 10
        elif orb_range_pct > 0.3:
            score += 7
        elif orb_range_pct > 0.1:
            score += 5
    else:
        # No breakout yet, but check if setup is forming
        if orb_info:
            orb_range_pct = orb_info.get("orb_range_pct", 0)
            if orb_range_pct > 0.3:  # Good range forming
                score += 10

    return min(100.0, score)


def analyze_ticker(ticker: str, ib_connection=None) -> Optional[Dict]:
    """
    Analyze a single ticker for 5min ORB setup with VWAP confirmation
    Fetches live data from IBKR TWS
    Returns: dict with all analysis results
    """
    # Fetch today's data from IBKR
    df_1min = fetch_today_data(ticker, ib_connection)
    if df_1min is None or df_1min.empty:
        return None

    # Resample to 5-minute bars
    df_5min = resample_to_5min(df_1min)
    if df_5min.empty or len(df_5min) < 1:
        return None

    # Calculate ORB range (first 5 minutes)
    orb_info = calculate_orb_range(df_5min)
    if orb_info is None:
        return None

    # Check for breakout
    breakout_info = check_breakout(df_5min, orb_info["orb_high"], orb_info["orb_low"])

    # Calculate VWAP (anchored from market open)
    market_open = df_5min.index[0]
    vwap = compute_vwap(df_5min, anchor_time=market_open)

    # Check VWAP confirmation
    vwap_info = check_vwap_confirmation(
        df_5min, vwap, breakout_info["breakout_direction"] if breakout_info else None
    )

    # Check volume confirmation
    volume_info = check_volume_confirmation(df_5min)

    # Calculate setup score
    setup_score = calculate_setup_score(
        orb_info, breakout_info or {}, vwap_info, volume_info
    )

    # Compile results
    result = {
        "ticker": ticker,
        "orb_high": orb_info["orb_high"],
        "orb_low": orb_info["orb_low"],
        "orb_range_pct": orb_info["orb_range_pct"],
        "current_price": (
            breakout_info["current_price"]
            if breakout_info
            else df_5min.iloc[-1]["close"]
        ),
        "has_breakout": breakout_info["has_breakout"] if breakout_info else False,
        "breakout_direction": breakout_info.get("breakout_direction", "NONE"),
        "vwap_confirmed": vwap_info["vwap_confirmed"],
        "vwap_distance_pct": vwap_info["vwap_distance_pct"],
        "current_vwap": vwap_info["current_vwap"],
        "volume_ok": volume_info["volume_ok"],
        "volume_ratio": volume_info["volume_ratio"],
        "setup_score": setup_score,
        "last_update": df_5min.index[-1],
        "bars_count": len(df_5min),
    }

    return result


def scan_all_tickers(tickers: List[str], ib_connection=None) -> pd.DataFrame:
    """
    Scan all tickers and return ranked results
    Fetches live data from IBKR TWS
    """
    # Get IB connection if not provided
    if ib_connection is None:
        ib_connection = get_ib_connection()

    # Verify connection is still valid
    if not ib_connection.isConnected():
        raise ConnectionError("IBKR connection is not active. Please reconnect.")

    results = []

    for ticker in tickers:
        try:
            analysis = analyze_ticker(ticker, ib_connection)
            if analysis:
                results.append(analysis)
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
            continue

    if not results:
        return pd.DataFrame()

    # Convert to DataFrame and sort by setup score
    df = pd.DataFrame(results)
    df = df.sort_values("setup_score", ascending=False)

    return df


if __name__ == "__main__":
    """
    Test script to verify IBKR connection and data fetching
    """
    print("=" * 60)
    print("Testing IBKR Connection and Data Fetching")
    print("=" * 60)

    # Test connection
    print("\n1. Testing IBKR connection...")
    try:
        ib = get_ib_connection(host="127.0.0.1", port=7497, client_id=1)
        print(f"   ✅ Connected to IBKR TWS")
        print(f"   Connection status: {ib.isConnected()}")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        exit(1)

    # Test fetching data for one ticker
    print("\n2. Testing data fetch for AAPL...")
    try:
        df = fetch_today_data("AAPL", ib)
        if df is not None and not df.empty:
            print(f"   ✅ Successfully fetched {len(df)} bars")
            print(f"   Date range: {df.index.min()} to {df.index.max()}")
            print(f"   Columns: {list(df.columns)}")
            print(f"\n   Sample data (last 5 bars):")
            print(df.tail())
        else:
            print("   ⚠️  No data returned (might be outside market hours)")
    except Exception as e:
        print(f"   ❌ Data fetch failed: {e}")
        import traceback

        traceback.print_exc()

    # Test analyzing one ticker
    print("\n3. Testing ORB analysis for AAPL...")
    try:
        result = analyze_ticker("AAPL", ib)
        if result:
            print(f"   ✅ Analysis successful")
            print(f"   Ticker: {result['ticker']}")
            print(f"   Current Price: ${result['current_price']:.2f}")
            print(f"   ORB High: ${result['orb_high']:.2f}")
            print(f"   ORB Low: ${result['orb_low']:.2f}")
            print(f"   ORB Range: {result['orb_range_pct']:.2f}%")
            print(f"   Breakout: {result['has_breakout']}")
            print(f"   Direction: {result['breakout_direction']}")
            print(f"   VWAP Confirmed: {result['vwap_confirmed']}")
            print(f"   Setup Score: {result['setup_score']:.1f}/100")
        else:
            print("   ⚠️  No analysis result (insufficient data)")
    except Exception as e:
        print(f"   ❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()

    # Test scanning multiple tickers
    print(f"\n4. Testing scan for {len(TICKERS)} tickers...")
    try:
        results_df = scan_all_tickers(TICKERS, ib)
        if not results_df.empty:
            print(f"   ✅ Successfully scanned {len(results_df)} tickers")
            print(f"\n   Top 5 setups:")
            print(
                results_df[
                    [
                        "ticker",
                        "setup_score",
                        "breakout_direction",
                        "vwap_confirmed",
                        "current_price",
                    ]
                ].head()
            )
        else:
            print("   ⚠️  No results returned")
    except Exception as e:
        print(f"   ❌ Scan failed: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
