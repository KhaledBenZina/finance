# Import necessary libraries
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime

# Create a Dash app
app = dash.Dash(__name__)

# App layout
app.layout = html.Div(
    [
        html.H1("Stock Price Visualization"),
        html.Div(
            [
                html.Label("Enter Stock Symbol:"),
                dcc.Input(id="stock-symbol", type="text", value="AAPL"),
                dcc.DatePickerRange(
                    id="date-range",
                    start_date="2023-07-01",
                    end_date="2023-10-05",
                    display_format="YYYY-MM-DD",
                ),
                html.Button("Submit", id="submit-button"),
            ]
        ),
        dcc.Graph(id="stock-graph"),
    ]
)


# Callback function to update the graph
@app.callback(
    Output("stock-graph", "figure"),
    Input("submit-button", "n_clicks"),
    Input("stock-symbol", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def update_graph(n_clicks, symbol, start_date, end_date):
    # Fetch stock data from Yahoo Finance
    df = yf.download(symbol, start=start_date, end=end_date)

    # Create a candlestick chart
    trace = go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name=symbol,
    )

    layout = {
        "title": f"{symbol} Stock Price",
        "xaxis": {"rangeslider": {"visible": True}},
        "yaxis": {"title": "Price"},
    }

    return {"data": [trace], "layout": layout}


# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
