import React, { useState, useEffect, useRef } from "react";
import "./App.css";

function App() {
    const [symbol, setSymbol] = useState("NVDA");
    const [quantity, setQuantity] = useState(100);
    const [tradeStatus, setTradeStatus] = useState("");
    const [marketPrice, setMarketPrice] = useState(null);
    const [positions, setPositions] = useState([]);
    const [connectionStatus, setConnectionStatus] = useState("Disconnected");
    const [errorMessage, setErrorMessage] = useState("");

    const ws = useRef(null);
    const timerRef = useRef(null); // Reference to store the timer ID

    // Initialize WebSocket connection
    useEffect(() => {
        // Close previous connection if exists
        if (ws.current) {
            ws.current.close();
        }

        // Create new WebSocket connection
        ws.current = new WebSocket("ws://localhost:8765/ws");

        // Connection opened
        ws.current.onopen = () => {
            setConnectionStatus("Connected");
            setErrorMessage("");

            // Request positions
            ws.current.send(JSON.stringify({ type: "positions" }));

            // Request market data for current symbol
            requestMarketData(symbol);
        };

        // Handle messages from server
        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === "market_data") {
                setMarketPrice(data.price);
            } else if (data.type === "trade_update") {
                setTradeStatus(`${data.symbol} - ${data.status}`);
            } else if (data.type === "positions") {
                setPositions(data.positions);
            } else if (data.type === "error") {
                setErrorMessage(data.message);
            }
        };

        // Handle connection close
        ws.current.onclose = () => {
            setConnectionStatus("Disconnected");
        };

        // Handle connection error
        ws.current.onerror = (error) => {
            setConnectionStatus("Error");
            setErrorMessage("WebSocket connection error");
            console.error("WebSocket error:", error);
        };

        // Cleanup function
        return () => {
            if (ws.current) {
                ws.current.close();
            }
            // Clear any existing timer on unmount
            if (timerRef.current) {
                clearInterval(timerRef.current);
            }
        };
    }, []); // Empty dependency array means this effect runs once on mount

    // Request market data when symbol changes
    useEffect(() => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            requestMarketData(symbol);

            // Clear any existing timer when symbol changes
            if (timerRef.current) {
                clearInterval(timerRef.current);
            }

            // Set up new timer for auto-refresh of the current symbol
            timerRef.current = setInterval(() => {
                if (ws.current && ws.current.readyState === WebSocket.OPEN) {
                    requestMarketData(symbol);
                }
            }, 5000); // Update every 5 seconds (adjust as needed)
        }

        // Cleanup timer when symbol changes
        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
            }
        };
    }, [symbol]);

    // Function to request market data
    const requestMarketData = (symbol) => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({
                type: "market_data",
                symbol: symbol
            }));
        }
    };

    // Function to place a trade
    const placeTrade = (direction) => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({
                type: "trade",
                symbol: symbol,
                direction: direction,
                quantity: quantity
            }));
        }
    };

    // Function to refresh positions
    const refreshPositions = () => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({
                type: "positions"
            }));
        }
    };

    return (
        <div className="container">
            <h1>IB Trading Bot</h1>

            <div className="status-bar">
                <span className={`connection-status ${connectionStatus.toLowerCase()}`}>
                    {connectionStatus}
                </span>
                {errorMessage && <span className="error-message">{errorMessage}</span>}
            </div>

            <div className="card">
                <h2>Trade Execution</h2>

                <div className="form-group">
                    <label>Stock Symbol:</label>
                    <select
                        value={symbol}
                        onChange={(e) => setSymbol(e.target.value)}
                        className="form-control"
                    >
                        <option value="AAPL">AAPL</option>
                        <option value="MSFT">MSFT</option>
                        <option value="NVDA">NVDA</option>
                        <option value="TSLA">TSLA</option>
                        <option value="AMZN">AMZN</option>
                        <option value="GOOG">GOOG</option>
                        <option value="META">META</option>
                    </select>
                </div>

                <div className="form-group">
                    <label>Quantity:</label>
                    <input
                        type="number"
                        className="form-control"
                        value={quantity}
                        min="1"
                        onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
                    />
                </div>

                <div className="button-group">
                    <button
                        onClick={() => placeTrade("long")}
                        className="btn btn-success"
                    >
                        Buy
                    </button>
                    <button
                        onClick={() => placeTrade("short")}
                        className="btn btn-danger"
                    >
                        Sell
                    </button>
                </div>

                <div className="market-price">
                    <h3>
                        Live Market Price:
                        <span className="price">
                            {marketPrice ? `$${marketPrice}` : "Loading..."}
                        </span>
                    </h3>
                    <button
                        onClick={() => requestMarketData(symbol)}
                        className="btn btn-secondary"
                    >
                        Refresh Price
                    </button>
                </div>

                {tradeStatus && <p className="trade-status">{tradeStatus}</p>}
            </div>

            <div className="card">
                <div className="card-header">
                    <h2>Open Positions</h2>
                    <button
                        onClick={refreshPositions}
                        className="btn btn-secondary"
                    >
                        Refresh
                    </button>
                </div>

                {positions.length > 0 ? (
                    <table className="positions-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Quantity</th>
                                <th>Price</th>
                                <th>Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            {positions.map((pos, index) => (
                                <tr key={index}>
                                    <td>{pos.symbol}</td>
                                    <td className={pos.quantity >= 0 ? "positive" : "negative"}>
                                        {pos.quantity}
                                    </td>
                                    <td>${pos.price}</td>
                                    <td className={pos.quantity * pos.price >= 0 ? "positive" : "negative"}>
                                        ${(pos.quantity * pos.price).toFixed(2)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <p className="no-positions">No open positions</p>
                )}
            </div>
        </div>
    );
}

export default App;