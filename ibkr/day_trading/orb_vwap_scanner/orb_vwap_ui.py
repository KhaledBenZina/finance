"""
Streamlit UI for 5min ORB + VWAP Setup Scanner
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import sys
from pathlib import Path
import os

# Disable asyncio to avoid conflicts with IBKR TWS
# Set environment variable before any asyncio imports
os.environ["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
os.environ["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import functions - they will handle ib_insync imports lazily
# DO NOT import ib_insync at module level - it causes asyncio issues
from orb_vwap_scanner import TICKERS

# Lazy import the functions that use ib_insync
def get_ib_connection_lazy(*args, **kwargs):
    """Lazy wrapper to avoid importing ib_insync at module level"""
    from orb_vwap_scanner import get_ib_connection
    return get_ib_connection(*args, **kwargs)

def scan_all_tickers_lazy(*args, **kwargs):
    """Lazy wrapper to avoid importing ib_insync at module level"""
    from orb_vwap_scanner import scan_all_tickers
    return scan_all_tickers(*args, **kwargs)

# Page configuration
st.set_page_config(
    page_title="5min ORB + VWAP Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .positive {
        color: #00cc00;
        font-weight: bold;
    }
    .negative {
        color: #ff3333;
        font-weight: bold;
    }
    .neutral {
        color: #ffaa00;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = None
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = pd.DataFrame()
if 'ib_connection' not in st.session_state:
    st.session_state.ib_connection = None

def format_breakout_direction(direction):
    """Format breakout direction with emoji"""
    if direction == 'BULLISH':
        return '🟢 BULLISH'
    elif direction == 'BEARISH':
        return '🔴 BEARISH'
    else:
        return '⚪ NONE'

def format_vwap_confirmed(confirmed, distance_pct):
    """Format VWAP confirmation status"""
    if confirmed:
        return '✅ Confirmed'
    elif abs(distance_pct) < 0.5:
        return '🟡 Close'
    else:
        return '❌ Not Confirmed'

def format_volume_status(volume_ok, volume_ratio):
    """Format volume status"""
    if volume_ok:
        return f'✅ {volume_ratio:.2f}x'
    elif volume_ratio >= 1.0:
        return f'🟡 {volume_ratio:.2f}x'
    else:
        return f'❌ {volume_ratio:.2f}x'

def format_score(score):
    """Format setup score with color"""
    if score >= 70:
        return f'<span class="positive">{score:.1f}</span>'
    elif score >= 40:
        return f'<span class="neutral">{score:.1f}</span>'
    else:
        return f'<span class="negative">{score:.1f}</span>'

# Main app
st.markdown('<div class="main-header">5min ORB + VWAP Setup Scanner</div>', unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.header("⚙️ Controls")
    
    # IBKR Connection Settings
    st.subheader("IBKR Connection")
    ib_host = st.text_input("TWS Host", value="127.0.0.1")
    ib_port = st.number_input("TWS Port", value=7497, min_value=1, max_value=65535)
    ib_client_id = st.number_input("Client ID", value=1, min_value=1, max_value=100)
    
    # Connection status
    if st.session_state.ib_connection is None:
        st.warning("⚠️ Not connected to IBKR TWS")
        if st.button("🔌 Connect to IBKR"):
            try:
                ib = get_ib_connection_lazy(host=ib_host, port=ib_port, client_id=ib_client_id)
                # Verify connection is active
                if ib.isConnected():
                    st.session_state.ib_connection = ib
                    st.success("✅ Connected to IBKR TWS")
                    st.rerun()
                else:
                    st.error("❌ Connection established but not active")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")
                import traceback
                st.code(traceback.format_exc())
    else:
        # Check if connection is still valid
        try:
            if st.session_state.ib_connection.isConnected():
                st.success("✅ Connected to IBKR TWS")
            else:
                st.warning("⚠️ Connection lost - please reconnect")
                st.session_state.ib_connection = None
        except:
            st.warning("⚠️ Connection invalid - please reconnect")
            st.session_state.ib_connection = None
        
        if st.button("🔌 Disconnect"):
            try:
                if st.session_state.ib_connection and st.session_state.ib_connection.isConnected():
                    st.session_state.ib_connection.disconnect()
            except:
                pass
            st.session_state.ib_connection = None
            st.rerun()
    
    st.divider()
    
    # Auto-refresh toggle
    auto_refresh = st.checkbox("🔄 Auto-refresh (30s)", value=False)
    refresh_interval = 30 if auto_refresh else 0
    
    # Filters
    st.header("🔍 Filters")
    
    min_score = st.slider(
        "Minimum Setup Score",
        min_value=0,
        max_value=100,
        value=30,
        step=5
    )
    
    breakout_filter = st.selectbox(
        "Breakout Status",
        options=["All", "Breakout Only", "No Breakout"],
        index=0
    )
    
    direction_filter = st.selectbox(
        "Breakout Direction",
        options=["All", "Bullish", "Bearish"],
        index=0
    )
    
    vwap_filter = st.selectbox(
        "VWAP Confirmation",
        options=["All", "Confirmed", "Not Confirmed"],
        index=0
    )
    
    # Manual refresh button
    if st.button("🔄 Refresh Now", type="primary"):
        st.session_state.last_scan_time = None
        st.cache_data.clear()
    
    # Test connection button
    if st.session_state.ib_connection is not None:
        if st.button("🧪 Test Connection"):
            try:
                if st.session_state.ib_connection.isConnected():
                    # Try fetching one ticker
                    from orb_vwap_scanner import fetch_today_data as fetch_today_data_lazy
                    df = fetch_today_data_lazy("AAPL", st.session_state.ib_connection)
                    if df is not None and not df.empty:
                        st.success(f"✅ Connection test successful! Fetched {len(df)} bars for AAPL")
                    else:
                        st.warning("⚠️ Connection active but no data returned (might be outside market hours)")
                else:
                    st.error("❌ Connection is not active")
            except Exception as e:
                st.error(f"❌ Test failed: {e}")
                import traceback
                with st.expander("See error details"):
                    st.code(traceback.format_exc())

# Main content area
col1, col2, col3, col4 = st.columns(4)

# Status indicator
status_col = st.columns(1)[0]

# Scan button and results
results = pd.DataFrame()  # Initialize results to avoid NameError

if st.button("🔍 Scan All Tickers", type="primary") or st.session_state.last_scan_time is None:
    if st.session_state.ib_connection is None:
        st.error("⚠️ Please connect to IBKR TWS first (use sidebar)")
        results = pd.DataFrame()  # Ensure results is empty DataFrame
    else:
        # Verify connection before scanning
        try:
            if not st.session_state.ib_connection.isConnected():
                st.error("⚠️ Connection lost. Please reconnect to IBKR TWS.")
                st.session_state.ib_connection = None
                results = pd.DataFrame()
            else:
                with st.spinner("Scanning tickers from IBKR..."):
                    try:
                        results = scan_all_tickers_lazy(TICKERS, st.session_state.ib_connection)
                        st.session_state.scan_results = results
                        st.session_state.last_scan_time = datetime.now()
                    except Exception as e:
                        st.error(f"Error scanning: {e}")
                        import traceback
                        with st.expander("See error details"):
                            st.code(traceback.format_exc())
                        results = pd.DataFrame()
        except Exception as e:
            st.error(f"Connection error: {e}")
            st.session_state.ib_connection = None
            results = pd.DataFrame()
else:
    results = st.session_state.scan_results

# Apply filters
if not results.empty:
    filtered_results = results.copy()
    
    # Score filter
    filtered_results = filtered_results[filtered_results['setup_score'] >= min_score]
    
    # Breakout filter
    if breakout_filter == "Breakout Only":
        filtered_results = filtered_results[filtered_results['has_breakout'] == True]
    elif breakout_filter == "No Breakout":
        filtered_results = filtered_results[filtered_results['has_breakout'] == False]
    
    # Direction filter
    if direction_filter == "Bullish":
        filtered_results = filtered_results[filtered_results['breakout_direction'] == 'BULLISH']
    elif direction_filter == "Bearish":
        filtered_results = filtered_results[filtered_results['breakout_direction'] == 'BEARISH']
    
    # VWAP filter
    if vwap_filter == "Confirmed":
        filtered_results = filtered_results[filtered_results['vwap_confirmed'] == True]
    elif vwap_filter == "Not Confirmed":
        filtered_results = filtered_results[filtered_results['vwap_confirmed'] == False]
    
    # Display summary metrics
    total_setups = len(filtered_results)
    bullish_count = len(filtered_results[filtered_results['breakout_direction'] == 'BULLISH'])
    bearish_count = len(filtered_results[filtered_results['breakout_direction'] == 'BEARISH'])
    vwap_confirmed_count = len(filtered_results[filtered_results['vwap_confirmed'] == True])
    avg_score = filtered_results['setup_score'].mean() if not filtered_results.empty else 0
    
    with col1:
        st.metric("Total Setups", total_setups)
    with col2:
        st.metric("Bullish", bullish_count, delta=f"{bearish_count} Bearish")
    with col3:
        st.metric("VWAP Confirmed", vwap_confirmed_count)
    with col4:
        st.metric("Avg Score", f"{avg_score:.1f}")
    
    # Last scan time
    if st.session_state.last_scan_time:
        time_diff = (datetime.now() - st.session_state.last_scan_time).total_seconds()
        status_col.info(f"Last scan: {st.session_state.last_scan_time.strftime('%H:%M:%S')} ({time_diff:.0f}s ago)")
    
    # Display results table
    if not filtered_results.empty:
        st.header("📊 Ranked Setups")
        
        # Prepare display dataframe
        display_df = filtered_results.copy()
        
        # Create formatted columns
        display_df['Ticker'] = display_df['ticker']
        display_df['Score'] = display_df['setup_score'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        display_df['Direction'] = display_df['breakout_direction'].apply(format_breakout_direction)
        display_df['Price'] = display_df['current_price'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")
        display_df['ORB High'] = display_df['orb_high'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")
        display_df['ORB Low'] = display_df['orb_low'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")
        display_df['ORB Range %'] = display_df['orb_range_pct'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        display_df['VWAP Status'] = display_df.apply(
            lambda row: format_vwap_confirmed(row['vwap_confirmed'], row['vwap_distance_pct']),
            axis=1
        )
        display_df['VWAP Dist %'] = display_df['vwap_distance_pct'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        display_df['Volume'] = display_df.apply(
            lambda row: format_volume_status(row['volume_ok'], row['volume_ratio']),
            axis=1
        )
        display_df['Vol Ratio'] = display_df['volume_ratio'].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
        display_df['Breakout'] = display_df['has_breakout'].apply(lambda x: '✅' if x else '❌')
        
        # Select and order columns for display
        display_columns = [
            'Ticker', 'Score', 'Direction', 'Price', 'ORB High', 'ORB Low', 
            'ORB Range %', 'VWAP Status', 'VWAP Dist %', 'Volume', 'Vol Ratio', 'Breakout'
        ]
        
        display_df = display_df[display_columns]
        
        # Display the table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=600
        )
        
        # Download button
        csv = filtered_results.to_csv(index=False)
        st.download_button(
            label="📥 Download Results (CSV)",
            data=csv,
            file_name=f"orb_vwap_setups_{selected_date.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("No setups match the current filters. Try adjusting your filter criteria.")
else:
    st.info("👆 Click 'Scan All Tickers' to start analyzing setups")

# Auto-refresh logic
if auto_refresh and refresh_interval > 0:
    time.sleep(refresh_interval)
    st.rerun()

