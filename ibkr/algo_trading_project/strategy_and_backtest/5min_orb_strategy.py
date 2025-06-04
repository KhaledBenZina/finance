#!/usr/bin/env python3
"""
Run NVDA Opening Range Breakout strategy backtest
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
from datetime import datetime
from nvda_backtest import OpeningRangeBreakoutBacktest


def run_single_backtest(
    db_config,
    symbol,
    start_date,
    end_date,
    account_size,
    risk_percent,
    reward_risk_ratio,
    vwap_threshold,
    volume_increase_threshold,
    transaction_fee,
):
    """
    Run a single backtest with specified parameters
    """
    # Initialize backtest
    backtest = OpeningRangeBreakoutBacktest(
        db_params=db_config,
        symbol=symbol,
        account_size=account_size,
        risk_percent=risk_percent,
        reward_risk_ratio=reward_risk_ratio,
        vwap_threshold=vwap_threshold,
        volume_increase_threshold=volume_increase_threshold,
        transaction_fee=transaction_fee,
    )

    # Run backtest
    results = backtest.run_backtest(start_date, end_date)

    # Print results
    if "error" in results:
        print(f"Error: {results['error']}")
        return None

    print("\n=== Backtest Results ===")
    print(f"Symbol: {symbol}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Parameters:")
    print(f"  - Risk: {risk_percent*100:.1f}%")
    print(f"  - Reward/Risk: {reward_risk_ratio:.1f}")
    print(f"  - VWAP Threshold: {vwap_threshold*100:.1f}%")
    print(f"  - Volume Increase: {volume_increase_threshold*100:.1f}%")
    print(f"  - Transaction Fee: ${transaction_fee:.2f}")
    print("\n=== Performance ===")
    print(f"Total Trades: {results['stats']['total_trades']}")
    print(f"Win Rate: {results['stats']['win_rate']*100:.2f}%")
    print(f"Profit Factor: {results['stats']['profit_factor']:.2f}")
    print(f"Net Profit: ${results['stats']['net_profit']:.2f}")
    print(f"ROI: {results['stats']['roi_percent']:.2f}%")
    print(f"Max Drawdown: {results['stats']['max_drawdown']*100:.2f}%")
    print(f"Total Fees: ${results['stats']['total_transaction_fees']:.2f}")

    # Plot basic results
    fig, axes = backtest.plot_results()
    plt.savefig(f"{symbol}_backtest_results.png")
    plt.close()

    # Additional analysis if we have trades
    if results["trades"] and len(results["trades"]) > 0:
        trades_df = pd.DataFrame(results["trades"])

        # Convert date columns to datetime
        trades_df["entry_date"] = pd.to_datetime(trades_df["entry_date"])
        trades_df["exit_date"] = pd.to_datetime(trades_df["exit_date"])

        # Add derived columns for analysis
        trades_df["trade_duration"] = (
            trades_df["exit_date"] - trades_df["entry_date"]
        ).dt.total_seconds() / 60  # in minutes
        trades_df["entry_hour"] = (
            trades_df["entry_date"].dt.hour + trades_df["entry_date"].dt.minute / 60
        )
        trades_df["day_of_week"] = trades_df["entry_date"].dt.day_name()
        trades_df["month"] = trades_df["entry_date"].dt.month_name()

        # Plot trade PnL by exit reason
        plt.figure(figsize=(10, 6))
        sns.boxplot(x="exit_reason", y="pnl", data=trades_df)
        plt.title("Trade PnL by Exit Reason")
        plt.axhline(y=0, color="r", linestyle="--")
        plt.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"{symbol}_pnl_by_exit_reason.png")
        plt.close()

        # Plot trade PnL by day of week
        plt.figure(figsize=(10, 6))
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        sns.boxplot(x="day_of_week", y="pnl", data=trades_df, order=day_order)
        plt.title("Trade PnL by Day of Week")
        plt.axhline(y=0, color="r", linestyle="--")
        plt.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"{symbol}_pnl_by_day.png")
        plt.close()

        # Plot trade duration vs PnL
        plt.figure(figsize=(10, 6))
        plt.scatter(trades_df["trade_duration"], trades_df["pnl"], alpha=0.6)
        plt.title("Trade Duration vs PnL")
        plt.xlabel("Trade Duration (minutes)")
        plt.ylabel("Profit/Loss ($)")
        plt.axhline(y=0, color="r", linestyle="--")
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"{symbol}_duration_vs_pnl.png")
        plt.close()

        # Plot entry time vs PnL
        plt.figure(figsize=(10, 6))
        plt.scatter(trades_df["entry_hour"], trades_df["pnl"], alpha=0.6)
        plt.title("Entry Time vs PnL")
        plt.xlabel("Entry Hour")
        plt.ylabel("Profit/Loss ($)")
        plt.axhline(y=0, color="r", linestyle="--")
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"{symbol}_entry_time_vs_pnl.png")
        plt.close()

        # Monthly performance
        monthly_pnl = trades_df.groupby("month")["pnl"].agg(["sum", "count", "mean"])
        month_order = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        monthly_pnl = monthly_pnl.reindex(month_order)

        plt.figure(figsize=(12, 6))
        ax = monthly_pnl["sum"].plot(
            kind="bar", color=np.where(monthly_pnl["sum"] >= 0, "green", "red")
        )
        plt.title("Monthly Performance")
        plt.xlabel("Month")
        plt.ylabel("Net Profit/Loss ($)")
        plt.axhline(y=0, color="black", linestyle="-")
        plt.grid(axis="y", alpha=0.3)

        # Add trade count as text on bars
        for i, v in enumerate(monthly_pnl["count"]):
            if not np.isnan(v) and v > 0:
                ax.text(i, 0, f"{int(v)}", ha="center", va="bottom", fontweight="bold")

        plt.tight_layout()
        plt.savefig(f"{symbol}_monthly_performance.png")
        plt.close()

        # Save trade data to CSV
        trades_df.to_csv(f"{symbol}_trades.csv", index=False)
        print(f"Trade data saved to {symbol}_trades.csv")

    return results


def main():
    """Main function to parse arguments and run backtest"""
    parser = argparse.ArgumentParser(
        description="Run NVDA Opening Range Breakout Strategy Backtest"
    )

    # Add arguments
    parser.add_argument("--host", type=str, default="localhost", help="Database host")
    parser.add_argument(
        "--database", type=str, default="stock_db", help="Database name"
    )
    parser.add_argument("--user", type=str, default="postgres", help="Database user")
    parser.add_argument("--password", type=str, required=True, help="Database password")
    parser.add_argument("--symbol", type=str, default="NVDA", help="Stock symbol")
    parser.add_argument(
        "--start_date", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end_date", type=str, default="2023-12-31", help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--account_size", type=float, default=15000, help="Account size in USD"
    )
    parser.add_argument(
        "--risk_percent", type=float, default=0.01, help="Risk percentage per trade"
    )
    parser.add_argument(
        "--reward_risk", type=float, default=2.0, help="Reward to risk ratio"
    )
    parser.add_argument(
        "--vwap_threshold", type=float, default=0.005, help="VWAP threshold"
    )
    parser.add_argument(
        "--volume_threshold", type=float, default=1.5, help="Volume increase threshold"
    )
    parser.add_argument(
        "--fee", type=float, default=1.0, help="Transaction fee per trade"
    )

    args = parser.parse_args()

    # Configure database connection
    db_config = {
        "host": args.host,
        "database": args.database,
        "user": args.user,
        "password": args.password,
    }

    # Run the backtest
    run_single_backtest(
        db_config=db_config,
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        account_size=args.account_size,
        risk_percent=args.risk_percent,
        reward_risk_ratio=args.reward_risk,
        vwap_threshold=args.vwap_threshold,
        volume_increase_threshold=args.volume_threshold,
        transaction_fee=args.fee,
    )


if __name__ == "__main__":
    main()
