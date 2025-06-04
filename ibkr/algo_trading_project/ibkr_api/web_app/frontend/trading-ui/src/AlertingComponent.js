import React, { useState } from "react";

function AlertingComponent({ ws, connectionStatus }) {
    const [watchlist, setWatchlist] = useState([
        { symbol: "NVDA", active: true, vwap: true, prevClose: true, volume: false },
        { symbol: "AAPL", active: false, vwap: true, prevClose: true, volume: false },
        { symbol: "MSFT", active: false, vwap: true, prevClose: true, volume: false },
        { symbol: "TSLA", active: false, vwap: true, prevClose: true, volume: false },
        { symbol: "AMZN", active: false, vwap: true, prevClose: true, volume: false },
        { symbol: "GOOG", active: false, vwap: true, prevClose: true, volume: false },
        { symbol: "META", active: false, vwap: true, prevClose: true, volume: false },
    ]);

    const [alerts, setAlerts] = useState([]);
    const [customSymbol, setCustomSymbol] = useState("");
    const [isMonitoring, setIsMonitoring] = useState(false);

    // Toggle which symbols to monitor
    const toggleSymbol = (index) => {
        const newWatchlist = [...watchlist];
        newWatchlist[index].active = !newWatchlist[index].active;
        setWatchlist(newWatchlist);
    };

    // Toggle which alert conditions to use
    const toggleCondition = (index, condition) => {
        const newWatchlist = [...watchlist];
        newWatchlist[index][condition] = !newWatchlist[index][condition];
        setWatchlist(newWatchlist);
    };

    // Add a custom symbol to the watchlist
    const addCustomSymbol = () => {
        if (customSymbol && !watchlist.some(item => item.symbol === customSymbol)) {
            setWatchlist([
                ...watchlist,
                {
                    symbol: customSymbol.toUpperCase(),
                    active: true,
                    vwap: true,
                    prevClose: true,
                    volume: false
                }
            ]);
            setCustomSymbol("");
        }
    };

    // Start/stop monitoring process
    const toggleMonitoring = () => {
        const activeSymbols = watchlist.filter(item => item.active);

        if (!isMonitoring && activeSymbols.length > 0) {
            // Start monitoring
            if (ws && ws.current && ws.current.readyState === WebSocket.OPEN) {
                ws.current.send(JSON.stringify({
                    type: "start_alerting",
                    symbols: activeSymbols
                }));
                setIsMonitoring(true);

                // Add initial monitoring message
                const timestamp = new Date().toLocaleTimeString();
                setAlerts([
                    {
                        time: timestamp,
                        type: "info",
                        message: `Started monitoring ${activeSymbols.length} symbols`
                    },
                    ...alerts
                ]);
            }
        } else if (isMonitoring) {
            // Stop monitoring
            if (ws && ws.current && ws.current.readyState === WebSocket.OPEN) {
                ws.current.send(JSON.stringify({
                    type: "stop_alerting"
                }));
                setIsMonitoring(false);

                // Add stopping message
                const timestamp = new Date().toLocaleTimeString();
                setAlerts([
                    {
                        time: timestamp,
                        type: "info",
                        message: "Stopped price monitoring"
                    },
                    ...alerts
                ]);
            }
        }
    };

    // Clear all alerts
    const clearAlerts = () => {
        setAlerts([]);
    };

    // Handle incoming alerts (this should be called from the parent component when alert messages arrive)
    const handleNewAlert = (alertData) => {
        const timestamp = new Date().toLocaleTimeString();
        setAlerts([
            {
                time: timestamp,
                type: alertData.alertType || "price",
                message: alertData.message
            },
            ...alerts
        ]);
    };

    return (
        <div className="card">
            <div className="card-header">
                <h2>Price Alerts</h2>
                <div>
                    <button
                        onClick={toggleMonitoring}
                        className={`btn ${isMonitoring ? "btn-danger" : "btn-success"}`}
                        disabled={connectionStatus !== "Connected" ||
                            (watchlist.filter(item => item.active).length === 0 && !isMonitoring)}
                    >
                        {isMonitoring ? "Stop Monitoring" : "Start Monitoring"}
                    </button>
                </div>
            </div>

            <div className="watchlist-section">
                <h3>Watchlist</h3>
                <div className="watchlist-controls">
                    <div className="form-group">
                        <input
                            type="text"
                            className="form-control"
                            placeholder="Add symbol..."
                            value={customSymbol}
                            onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
                        />
                    </div>
                    <button
                        className="btn btn-secondary"
                        onClick={addCustomSymbol}
                        disabled={!customSymbol}
                    >
                        Add
                    </button>
                </div>

                <table className="watchlist-table">
                    <thead>
                        <tr>
                            <th>Active</th>
                            <th>Symbol</th>
                            <th>VWAP</th>
                            <th>Prev Close</th>
                            <th>Volume Spike</th>
                        </tr>
                    </thead>
                    <tbody>
                        {watchlist.map((item, index) => (
                            <tr key={index}>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={item.active}
                                        onChange={() => toggleSymbol(index)}
                                    />
                                </td>
                                <td>{item.symbol}</td>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={item.vwap}
                                        onChange={() => toggleCondition(index, "vwap")}
                                    />
                                </td>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={item.prevClose}
                                        onChange={() => toggleCondition(index, "prevClose")}
                                    />
                                </td>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={item.volume}
                                        onChange={() => toggleCondition(index, "volume")}
                                    />
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="alerts-section">
                <div className="alerts-header">
                    <h3>Alert Messages</h3>
                    <button
                        className="btn btn-secondary"
                        onClick={clearAlerts}
                        disabled={alerts.length === 0}
                    >
                        Clear
                    </button>
                </div>

                <div className="alerts-container">
                    {alerts.length > 0 ? (
                        <div className="alerts-list">
                            {alerts.map((alert, index) => (
                                <div key={index} className={`alert-item ${alert.type}`}>
                                    <span className="alert-time">{alert.time}</span>
                                    <span className="alert-message">{alert.message}</span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="no-alerts">No alerts yet.</p>
                    )}
                </div>
            </div>
        </div>
    );
}

export default AlertingComponent;