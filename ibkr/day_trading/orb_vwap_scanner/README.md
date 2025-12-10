# 5min ORB + VWAP Setup Scanner

A real-time scanner that ranks the best 5-minute Opening Range Breakout (ORB) setups with VWAP confirmation. **Fetches live data directly from IBKR TWS API**.

## Features

- **5-Minute ORB Detection**: Identifies opening range breakouts from the first 5-minute bar (9:30-9:35)
- **VWAP Confirmation**: Calculates anchored VWAP from market open and confirms breakouts
- **Volume Analysis**: Validates breakouts with volume confirmation
- **Quality Scoring**: Ranks setups by a composite score (0-100)
- **Interactive UI**: Streamlit-based dashboard with filtering and real-time updates
- **Live IBKR Data**: Fetches real-time data directly from IBKR TWS (no database required)

## Setup

### Requirements

First, activate the `perso` conda environment:

```bash
source /home/khaled/mambaforge/bin/activate perso
```

Then install the required packages:

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install streamlit pandas numpy ib-insync
```

**Important**: Make sure streamlit is installed in the `perso` environment. The script uses `python -m streamlit` to ensure it uses the conda environment's Python and packages.

### IBKR TWS Connection

The scanner fetches **live data** from Interactive Brokers Trader Workstation (TWS) or IB Gateway.

**Prerequisites:**
1. TWS or IB Gateway must be running
2. API connections must be enabled in TWS settings
3. Default connection settings:
   - Host: `127.0.0.1` (localhost)
   - Port: `7497` (paper trading) or `7496` (live trading)
   - Client ID: `1` (can be changed in UI)

**TWS Settings:**
- Go to Configure → API → Settings
- Enable "Enable ActiveX and Socket Clients"
- Add trusted IP: `127.0.0.1` if needed
- Set socket port (default 7497 for paper, 7496 for live)

## Usage

### Run the UI

```bash
# Option 1: Use the shell script
./run_orb_scanner.sh

# Option 2: Run directly with Streamlit
cd /home/khaled/spec_proj/finance/ibkr/day_trading/orb_vwap_scanner
source /home/khaled/mambaforge/bin/activate perso
python -m streamlit run orb_vwap_ui.py --server.port 8501
```

### Connection Steps

1. **Start TWS/IB Gateway**: Make sure IBKR TWS or IB Gateway is running
2. **Open the UI**: Run the scanner using the script above
3. **Connect**: In the sidebar, configure connection settings and click "🔌 Connect to IBKR"
4. **Scan**: Once connected, click "🔍 Scan All Tickers" to analyze setups

## How It Works

### ORB Calculation
1. Identifies the first 5-minute bar (9:30-9:35) as the opening range
2. Monitors for price breakouts above (bullish) or below (bearish) the range

### VWAP Confirmation
- VWAP is calculated anchored from market open (9:30)
- Bullish breakouts are confirmed when price is above VWAP
- Bearish breakouts are confirmed when price is below VWAP

### Setup Score Components
- **Breakout (40 points)**: Has a breakout occurred?
- **VWAP Confirmation (30 points)**: Is VWAP confirming the breakout?
- **Volume (20 points)**: Is volume above average?
- **ORB Range Quality (10 points)**: Size of the opening range

### Filters
- Minimum setup score threshold
- Breakout status (All / Breakout Only / No Breakout)
- Direction (All / Bullish / Bearish)
- VWAP confirmation status

## Output

The scanner displays:
- Ranked list of setups sorted by quality score
- Current price, ORB levels, VWAP distance
- Volume confirmation status
- Breakout direction and confirmation status
- Export to CSV functionality

## Notes

- **Live Data**: Fetches real-time data directly from IBKR TWS (no database required)
- **Market Hours**: Works best during regular trading hours (9:30 AM - 4:00 PM ET)
- **Connection**: Requires active IBKR TWS/IB Gateway connection
- **Data Source**: Uses 1-minute bars from IBKR, resampled to 5-minute bars for ORB analysis
- **Asyncio**: Uses lazy imports to avoid asyncio conflicts with Streamlit

## Troubleshooting

### Connection Issues
- Ensure TWS/IB Gateway is running
- Check that API connections are enabled in TWS settings
- Verify the port number matches your TWS configuration
- Try different Client IDs if you have multiple connections

### Import Errors
- Make sure `ib-insync` is installed: `pip install ib-insync`
- Ensure you're using the `perso` conda environment

### No Data Returned
- Check if market is open (9:30 AM - 4:00 PM ET)
- Verify ticker symbols are valid
- Check TWS connection status
