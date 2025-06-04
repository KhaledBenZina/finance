import React, { useState, useEffect, useRef } from "react";
import "./App.css";
import AlertingComponent from "./AlertingComponent";

function App() {
    // Basic trade state
    const [symbol, setSymbol] = useState("NVDA");
    const [quantity, setQuantity] = useState(100);
    const [tradeStatus, setTradeStatus] = useState("");
    const [marketPrice, setMarketPrice] = useState(null);
    const [positions, setPositions] = useState([]);
    const [connectionStatus, setConnectionStatus] = useState("Disconnected");
    const [errorMessage, setErrorMessage] = useState("");

    // 3R Strategy specific state
    const [tradeType, setTradeType] = useState("standard");
    const [timeframe, setTimeframe] = useState(5);
    const [lookback, setLookback] = useState(20);
    const [tradeUpdates, setTradeUpdates] = useState([]);
    const [tradeActive, setTradeActive] = useState(false);

    // Trade execution info
    const [rValue, setRValue] = useState(null);
    const [entryPrice, setEntryPrice] = useState(null);
    const [stopPrice, setStopPrice] = useState(null);
    const [target1, setTarget1] = useState(null);
    const [target2, setTarget2] = useState(null);
    const [currentTradePrice, setCurrentTradePrice] = useState(null);

    // Reference to the alerts component to pass new alerts
    const alertsComponentRef = useRef(null);

    const ws = useRef(null);
    const updatesContainerRef = useRef(null);

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
            } else if (data.type === "3r_trade_update") {
                // Handle 3R strategy updates
                const timestamp = new Date().toLocaleTimeString();
                const update = {
                    time: timestamp,
                    status: data.status,
                    message: data.message
                };

                setTradeUpdates(prev => [...prev, update]);

                // Set strategy-specific data if available
                if (data.r_value) setRValue(data.r_value);
                if (data.entry_price) setEntryPrice(data.entry_price);
                if (data.stop_price) setStopPrice(data.stop_price);
                if (data.target1) setTarget1(data.target1);
                if (data.target2) setTarget2(data.target2);
                if (data.current_price) setCurrentTradePrice(data.current_price);

                // Update trade active status
                if (data.status === "Entering trade" || data.status === "Trade entered") {
                    setTradeActive(true);
                } else if (data.status === "Closed" || data.status === "Monitoring complete") {
                    setTradeActive(false);
                }
            } else if (data.type === "alert") {
                // Pass the alert to the AlertingComponent
                if (alertsComponentRef.current && alertsComponentRef.current.handleNewAlert) {
                    alertsComponentRef.current.handleNewAlert(data);
                }
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
        };
    }, []); // Empty dependency array means this effect runs once on mount

    // Scroll to bottom of updates container when new updates arrive
    useEffect(() => {
        if (updatesContainerRef.current) {
            updatesContainerRef.current.scrollTop = updatesContainerRef.current.scrollHeight;
        }
    }, [tradeUpdates]);

    // Request market data when symbol changes
    useEffect(() => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            requestMarketData(symbol);
        }
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
            // Reset trade-specific data when starting a new trade
            if (tradeType === "3r_volatility") {
                setRValue(null);
                setEntryPrice(null);
                setStopPrice(null);
                setTarget1(null);
                setTarget2(null);
                setCurrentTradePrice(null);
                setTradeUpdates([]);
            }

            ws.current.send(JSON.stringify({
                type: "trade",
                symbol: symbol,
                direction: direction,
                quantity: quantity,
                tradeType: tradeType,
                timeframe: timeframe,
                lookback: lookback
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

                <div className="form-group">
                    <label>Trade Type:</label>
                    <select
                        value={tradeType}
                        onChange={(e) => setTradeType(e.target.value)}
                        className="form-control"
                    >
                        <option value="standard">Standard Market Order</option>
                        <option value="3r_volatility">3R Partials Based on Volatility</option>
                    </select>
                </div>

                {tradeType === "3r_volatility" && (
                    <div className="strategy-params">
                        <div className="form-group">
                            <label>Timeframe (minutes):</label>
                            <select
                                value={timeframe}
                                onChange={(e) => setTimeframe(parseInt(e.target.value))}
                                className="form-control"
                            >
                                <option value="1">1</option>
                                <option value="5">5</option>
                                <option value="15">15</option>
                                <option value="30">30</option>
                                <option value="60">60</option>
                            </select>
                        </div>

                        <div className="form-group">
                            <label>Lookback Periods:</label>
                            <input
                                type="number"
                                className="form-control"
                                value={lookback}
                                min="10"
                                max="100"
                                onChange={(e) => setLookback(parseInt(e.target.value) || 20)}
                            />
                        </div>
                    </div>
                )}

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

                {tradeStatus && tradeType === "standard" && (
                    <p className="trade-status">{tradeStatus}</p>
                )}

                <div className="button-group">
                    <button
                        onClick={() => placeTrade("long")}
                        className="btn btn-success"
                        disabled={tradeActive}
                    >
                        Buy
                    </button>
                    <button
                        onClick={() => placeTrade("short")}
                        className="btn btn-danger"
                        disabled={tradeActive}
                    >
                        Sell
                    </button>
                </div>
            </div>

            {tradeType === "3r_volatility" && (
                <div className="card">
                    <h2>3R Strategy Information</h2>

                    {rValue ? (
                        <div className="strategy-info">
                            <div className="info-grid">
                                <div className="info-item">
                                    <span className="info-label">R Value:</span>
                                    <span className="info-value">${rValue}</span>
                                </div>

                                {entryPrice && (
                                    <div className="info-item">
                                        <span className="info-label">Entry Price:</span>
                                        <span className="info-value">${entryPrice}</span>
                                    </div>
                                )}

                                {stopPrice && (
                                    <div className="info-item">
                                        <span className="info-label">Stop Loss:</span>
                                        <span className="info-value">${stopPrice}</span>
                                    </div>
                                )}

                                {target1 && (
                                    <div className="info-item">
                                        <span className="info-label">Target 1 (1R):</span>
                                        <span className="info-value">${target1}</span>
                                    </div>
                                )}

                                {target2 && (
                                    <div className="info-item">
                                        <span className="info-label">Target 2 (2R):</span>
                                        <span className="info-value">${target2}</span>
                                    </div>
                                )}

                                {currentTradePrice && (
                                    <div className="info-item">
                                        <span className="info-label">Current Price:</span>
                                        <span className="info-value">${currentTradePrice}</span>
                                    </div>
                                )}
                            </div>

                            <div className="trade-progress">
                                {stopPrice && entryPrice && target1 && target2 && currentTradePrice && (
                                    <div className="progress-bar-container">
                                        <div className="price-labels">
                                            <span>Stop: ${stopPrice}</span>
                                            <span>Entry: ${entryPrice}</span>
                                            <span>1R: ${target1}</span>
                                            <span>2R: ${target2}</span>
                                        </div>

                                        <div className="progress-bar">
                                            <div className="progress-marker stop" style={{ left: '0%' }}></div>
                                            <div className="progress-marker entry" style={{ left: '33%' }}></div>
                                            <div className="progress-marker target1" style={{ left: '67%' }}></div>
                                            <div className="progress-marker target2" style={{ left: '100%' }}></div>

                                            {/* Position the current price marker */}
                                            <div className="progress-marker current"
                                                style={{
                                                    left: `${Math.min(Math.max((currentTradePrice - stopPrice) / (target2 - stopPrice) * 100, 0), 100)}%`
                                                }}>
                                                <span>${currentTradePrice}</span>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    ) : (
                        <p className="no-data">Strategy information will appear here once a trade is initiated.</p>
                    )}

                    <h3>Trade Updates</h3>
                    <div className="updates-container" ref={updatesContainerRef}>
                        {tradeUpdates.length > 0 ? (
                            <div className="updates-list">
                                {tradeUpdates.map((update, index) => (
                                    <div key={index} className={`update-item ${update.status.toLowerCase().replace(/\s+/g, '-')}`}>
                                        <span className="update-time">{update.time}</span>
                                        <span className="update-status">{update.status}</span>
                                        <span className="update-message">{update.message}</span>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="no-updates">No updates yet.</p>
                        )}
                    </div>
                </div>
            )}

            {/* Add the new AlertingComponent */}
            <AlertingComponent
                ref={alertsComponentRef}
                ws={ws}
                connectionStatus={connectionStatus}
            />

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
                                <th>Avg Cost</th>
                                <th>Unrealized P/L</th>
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
                                    <td className={pos.marketValue >= 0 ? "positive" : "negative"}>
                                        ${pos.marketValue.toFixed(2)}
                                    </td>
                                    <td>${pos.averageCost.toFixed(2)}</td>
                                    <td className={pos.unrealizedPNL >= 0 ? "positive" : "negative"}>
                                        ${pos.unrealizedPNL.toFixed(2)}
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