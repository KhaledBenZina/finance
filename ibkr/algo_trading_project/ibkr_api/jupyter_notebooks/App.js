import React, { useState, useEffect } from "react";
import axios from "axios";
import { io } from "socket.io-client";

const socket = io("http://127.0.0.1:5000");

const App = () => {
  const [symbol, setSymbol] = useState("NVDA");
  const [quantity, setQuantity] = useState(100);
  const [tradeStatus, setTradeStatus] = useState("");
  const [marketPrice, setMarketPrice] = useState(null);
  const [positions, setPositions] = useState([]);

  useEffect(() => {
    fetchPositions();
    // Request market data when component mounts
    const fetchMarketData = async () => {
      try {
        const response = await axios.get(`http://127.0.0.1:5000/marketdata?symbol=${symbol}`);
        setMarketPrice(response.data.price);
      } catch (error) {
        console.error("Error fetching market data:", error);
        setMarketPrice("Error");
      }
    };

    fetchMarketData();

    // Listen for the market data update from the server
    socket.on("market_data", (data) => {
      if (data.symbol === symbol) {
        setMarketPrice(data.price);
      }
    });

    // Listen for trade updates
    socket.on("trade_update", (data) => {
      setTradeStatus(`${data.symbol} - ${data.status}`);
    });

    // Cleanup when component unmounts
    return () => {
      socket.off("trade_update");
      socket.off("market_data");
    };
  }, [symbol]);

  const fetchPositions = async () => {
    const response = await axios.get("http://127.0.0.1:5000/positions");
    setPositions(response.data);
  };

  const placeTrade = async (direction) => {
    await axios.post("http://127.0.0.1:5000/trade", { symbol, direction, quantity });
    fetchPositions();
  };

  return (
    <div style={{ maxWidth: "400px", margin: "auto", padding: "20px", fontFamily: "Arial" }}>
      <h2>Trade Execution</h2>

      <label>Stock Symbol:</label>
      <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
        <option value="NVDA">NVDA</option>
        <option value="AAPL">AAPL</option>
        <option value="TSLA">TSLA</option>
        <option value="MSFT">MSFT</option>
      </select>

      <br />

      <label>Quantity:</label>
      <input
        type="number"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
      />

      <br />

      <button onClick={() => placeTrade("long")} style={{ backgroundColor: "green", color: "white", margin: "5px" }}>
        Buy
      </button>
      <button onClick={() => placeTrade("short")} style={{ backgroundColor: "red", color: "white", margin: "5px" }}>
        Sell
      </button>

      <h3>Live Market Price: ${marketPrice || "Loading..."}</h3>
      <p>{tradeStatus}</p>

      <h3>Open Positions</h3>
      {positions.length > 0 ? (
        <ul>
          {positions.map((pos, index) => (
            <li key={index}>
              {pos.symbol} - {pos.quantity} shares @ ${pos.price}
            </li>
          ))}
        </ul>
      ) : (
        <p>No open positions</p>
      )}
    </div>
  );
};

export default App;
