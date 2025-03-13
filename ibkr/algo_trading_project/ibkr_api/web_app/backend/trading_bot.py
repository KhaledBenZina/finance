import asyncio
import json
import math
import logging
import nest_asyncio
import time
import sys
from aiohttp import web
from ib_insync import *

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize IB connection
ib = IB()
connected_clients = set()
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds


async def connect_ib_with_retry():
    """Connect to Interactive Brokers with retry logic"""
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            if not ib.isConnected():
                logger.info(
                    f"Connection attempt {attempt}/{MAX_RETRY_ATTEMPTS} to Interactive Brokers..."
                )

                # Verify TWS/Gateway settings
                host = "127.0.0.1"
                port = (
                    7497  # 7497 for TWS paper trading, 7496 for Gateway paper trading
                )
                clientId = 1

                logger.info(f"Connecting to {host}:{port} with clientId {clientId}")

                # Set a timeout for the connection
                ib.connect(host, port, clientId=clientId, timeout=15)

                # Verify connection is established
                if ib.isConnected():
                    logger.info("Successfully connected to Interactive Brokers")

                    # Check if we can retrieve account information
                    # This is a good test to validate the connection is working properly
                    try:
                        accounts = ib.managedAccounts()
                        logger.info(f"Available accounts: {accounts}")
                    except Exception as e:
                        logger.warning(
                            f"Connected but couldn't retrieve account info: {e}"
                        )

                    return True
                else:
                    logger.error("Connection failed despite no errors")
            else:
                logger.info("Already connected to Interactive Brokers")
                return True

        except Exception as e:
            logger.error(f"Connection attempt {attempt} failed: {e}")

            # Provide more helpful messages based on common errors
            if "timeout" in str(e).lower():
                logger.error(
                    """
                CONNECTION TIMEOUT: Please check that:
                1. TWS or IB Gateway is running
                2. API connections are enabled in TWS/Gateway settings
                3. Auto-restart for API connections is enabled
                4. The correct port is being used (7496 for Gateway, 7497 for TWS paper trading)
                """
                )
            elif "permission denied" in str(e).lower():
                logger.error(
                    """
                PERMISSION DENIED: Please check that:
                1. You've accepted API connections in TWS/Gateway
                2. The clientId (1) is not being used by another application
                """
                )

            if attempt < MAX_RETRY_ATTEMPTS:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"All {MAX_RETRY_ATTEMPTS} connection attempts failed")
                return False

    return False


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Add this client to our set of connected clients
    connected_clients.add(ws)
    logger.info(f"Client connected. Total clients: {len(connected_clients)}")

    # Ensure IB is connected
    if not await connect_ib_with_retry():
        # Send connection error message to client
        await ws.send_json(
            {
                "type": "error",
                "message": "Failed to connect to Interactive Brokers. Please check that TWS/Gateway is running.",
            }
        )

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    logger.info(f"Received message: {data}")

                    # Check if we're still connected
                    if not ib.isConnected():
                        logger.warning("IB connection lost, attempting to reconnect...")
                        if not await connect_ib_with_retry():
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "message": "Lost connection to Interactive Brokers and failed to reconnect.",
                                }
                            )
                            continue

                    if data["type"] == "market_data":
                        symbol = data["symbol"]
                        await send_market_data(ws, symbol)

                    elif data["type"] == "trade":
                        symbol = data["symbol"]
                        direction = data["direction"]
                        quantity = int(data["quantity"])
                        await execute_trade(ws, symbol, direction, quantity)

                    elif data["type"] == "positions":
                        await send_positions(ws)

                    elif data["type"] == "connection_test":
                        # Simple endpoint to test if IB is connected
                        if ib.isConnected():
                            await ws.send_json(
                                {"type": "connection_test", "status": "connected"}
                            )
                        else:
                            await ws.send_json(
                                {"type": "connection_test", "status": "disconnected"}
                            )

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await ws.send_json({"type": "error", "message": str(e)})

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(
                    f"WebSocket connection closed with exception {ws.exception()}"
                )

    finally:
        # Remove this client from connected clients
        connected_clients.remove(ws)
        logger.info(f"Client disconnected. Remaining clients: {len(connected_clients)}")

    return ws


async def send_market_data(ws, symbol):
    try:
        stock = Stock(symbol, "SMART", "USD")

        # Cancel previous market data subscription if exists
        # contracts_to_cancel = []
        # for contract in ib.reqMktData():
        #     if contract.symbol == symbol:
        #         contracts_to_cancel.append(contract)

        # for contract in contracts_to_cancel:
        #     ib.cancelMktData(contract)

        # Request market data with error handling
        try:
            market_data = ib.reqMktData(stock)
        except Exception as e:
            logger.error(f"Failed to request market data: {e}")
            await ws.send_json(
                {
                    "type": "market_data",
                    "symbol": symbol,
                    "price": "Error requesting data",
                }
            )
            return

        # Wait for data to be populated (with timeout)
        timeout = 5  # seconds
        price = None

        # Use a non-blocking approach to wait for data
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if market_data.last is not None and not math.isnan(market_data.last):
                price = market_data.last
                break
            await asyncio.sleep(0.1)

        # If we didn't get a last price, try marketPrice as fallback
        if (
            price is None
            and market_data.marketPrice is not None
            and not math.isnan(market_data.marketPrice)
        ):
            price = market_data.marketPrice

        # If still no price, try bid/ask midpoint
        if (
            price is None
            and market_data.bid is not None
            and market_data.ask is not None
        ):
            if not math.isnan(market_data.bid) and not math.isnan(market_data.ask):
                price = (market_data.bid + market_data.ask) / 2

        # Send the data
        await ws.send_json(
            {
                "type": "market_data",
                "symbol": symbol,
                "price": price if price is not None else "No Data",
            }
        )

    except Exception as e:
        logger.error(f"Error sending market data: {e}")
        await ws.send_json({"type": "error", "message": str(e)})


async def execute_trade(ws, symbol, direction, quantity):
    try:
        stock = Stock(symbol, "SMART", "USD")
        order_type = "BUY" if direction == "long" else "SELL"
        order = MarketOrder(order_type, quantity)

        # Place the order
        try:
            trade = ib.placeOrder(stock, order)
            logger.info(f"Order placed: {order_type} {quantity} {symbol}")

            # Send confirmation
            await ws.send_json(
                {"type": "trade_update", "symbol": symbol, "status": "Order Placed"}
            )

            # Wait for order status updates
            timeout = 5  # seconds
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                ib.waitOnUpdate(timeout=0.2)
                if trade.orderStatus.status:
                    await ws.send_json(
                        {
                            "type": "trade_update",
                            "symbol": symbol,
                            "status": trade.orderStatus.status,
                        }
                    )
                    break
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            await ws.send_json(
                {"type": "error", "message": f"Failed to place order: {e}"}
            )

    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        await ws.send_json({"type": "error", "message": str(e)})


async def send_positions(ws):
    try:
        # Make sure we're connected before trying to get portfolio
        if not ib.isConnected():
            await ws.send_json(
                {"type": "error", "message": "Not connected to Interactive Brokers"}
            )
            return

        # Get portfolio data
        try:
            portfolio = ib.portfolio()

            positions = [
                {
                    "symbol": pos.contract.symbol,
                    "quantity": pos.position,
                    "price": pos.marketPrice if not math.isnan(pos.marketPrice) else 0,
                    "marketValue": (
                        pos.marketValue if not math.isnan(pos.marketValue) else 0
                    ),
                    "averageCost": (
                        pos.averageCost if not math.isnan(pos.averageCost) else 0
                    ),
                    "unrealizedPNL": (
                        pos.unrealizedPNL if not math.isnan(pos.unrealizedPNL) else 0
                    ),
                }
                for pos in portfolio
            ]

            # Send positions data
            await ws.send_json({"type": "positions", "positions": positions})

        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            await ws.send_json(
                {"type": "error", "message": f"Failed to get portfolio: {e}"}
            )

    except Exception as e:
        logger.error(f"Error sending positions: {e}")
        await ws.send_json({"type": "error", "message": str(e)})


async def start_background_tasks(app):
    """Background task to keep connection alive"""
    try:
        # Initialize connection
        if not await connect_ib_with_retry():
            logger.error(
                "Failed to establish initial connection to Interactive Brokers"
            )
            # We'll continue running to allow retry attempts later
    except Exception as e:
        logger.error(f"Error in startup: {e}")


async def cleanup_background_tasks(app):
    """Cleanup task to disconnect properly"""
    try:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from Interactive Brokers")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def main():
    # Initialize the aiohttp web application
    app = web.Application()

    # Add WebSocket route
    app.router.add_get("/ws", websocket_handler)

    # Add startup and cleanup handlers
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)

    # Run the server
    logger.info("Starting WebSocket server on http://0.0.0.0:8765/ws")
    try:
        web.run_app(app, host="0.0.0.0", port=8765)
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Ensure IB is disconnected
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from Interactive Brokers")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
