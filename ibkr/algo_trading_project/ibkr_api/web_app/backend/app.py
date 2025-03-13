from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from ib_insync import *
import asyncio
import math

# Initialize Flask & SocketIO
app = Flask(__name__)
CORS(app)  # Enable cross-origin requests for React
socketio = SocketIO(app, cors_allowed_origins="*")

# Connect to IB API
ib = IB()
if ib.isConnected():
    ib.disconnect()
ib.connect("127.0.0.1", 7497, clientId=1)


@app.route("/trade", methods=["POST"])
def trade():
    data = request.json
    stock_symbol = data["symbol"]
    direction = data["direction"]
    quantity = int(data["quantity"])

    stock = Stock(stock_symbol, "SMART", "USD")
    order_type = "BUY" if direction == "long" else "SELL"
    order = MarketOrder(order_type, quantity)

    # Run the order in a background task
    socketio.start_background_task(place_order, ib, stock, order, stock_symbol)

    return jsonify(
        {"message": "Trade executed", "symbol": stock_symbol, "quantity": quantity}
    )


def place_order(ib, stock, order, stock_symbol):
    trade = ib.placeOrder(stock, order)
    socketio.emit("trade_update", {"symbol": stock_symbol, "status": "Order Placed"})


@app.route("/positions", methods=["GET"])
def get_positions():
    positions = [
        {
            "symbol": pos.contract.symbol,
            "quantity": pos.position,
            "price": pos.marketPrice,
        }
        for pos in ib.portfolio()
    ]
    return jsonify(positions)


@app.route("/marketdata", methods=["GET"])
def get_market_data():
    symbol = request.args.get("symbol", "NVDA")
    stock = Stock(symbol, "SMART", "USD")

    # Start the background task to fetch market data
    socketio.start_background_task(fetch_market_data, stock)
    return jsonify({"symbol": symbol, "status": "Market data request started."})


import time


def fetch_market_data(stock):
    # Ensure we use the correct event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        # Fetch market data
        market_data = ib.reqMktData(stock)

        print("Market Data Object:", market_data)

        # Wait for the data to come in (max 5 seconds)
        for _ in range(5):
            time.sleep(1)
            if market_data.last is not None and not math.isnan(market_data.last):
                break  # Stop waiting if valid price is found

        # Handle cases where data is still invalid
        if market_data.last is None or math.isnan(market_data.last):
            price = "No Data"
        else:
            price = market_data.last

        print(f"Market Data for {stock.symbol}: {price}")


if __name__ == "__main__":
    socketio.run(app, debug=False, port=5000)
