import logging
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from typing import List
import queue
import threading
import time


class NewsAPIClient(EWrapper, EClient):
    def __init__(self, host="127.0.0.1", port=7497):
        """
        Initialize the TWS News API Client

        Args:
            host (str): TWS connection host (default localhost)
            port (int): TWS connection port (default paper trading port)
        """
        EClient.__init__(self, self)

        # Logging setup
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s: %(message)s"
        )
        self.logger = logging.getLogger(__name__)

        # Connection parameters
        self.host = host
        self.port = port

        # News queue for storing incoming news
        self.news_queue = queue.Queue()

        # Connection status flag
        self.is_connected = False

        # Tracking news subscriptions
        self.subscribed_symbols = set()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
        """
        Handle API errors

        Args:
            reqId (int): Request ID
            errorCode (int): Error code
            errorString (str): Error description
        """
        self.logger.error(f"Error {errorCode}: {errorString}")

    def newsProviders(self, newsProviders):
        """
        Log available news providers

        Args:
            newsProviders (List): List of available news providers
        """
        self.logger.info("Available News Providers:")
        for provider in newsProviders:
            # Dynamically print available attributes
            provider_info = {
                attr: getattr(provider, attr, "N/A")
                for attr in dir(provider)
                if not attr.startswith("_")
            }
            self.logger.info(f"Provider Details: {provider_info}")

    def historicalNewsEnd(self, reqId, startDateTime, endDateTime):
        """
        Indicates the end of historical news retrieval
        """
        self.logger.info(f"Historical news retrieval completed for reqId {reqId}")

    def historicalNews(self, reqId, time, providerCode, articleId, headline):
        """
        Process historical news

        Args:
            reqId (int): Request ID
            time (str): News timestamp
            providerCode (str): News provider code
            articleId (str): Article ID
            headline (str): Article headline
        """
        news_item = {
            "reqId": reqId,
            "time": time,
            "providerCode": providerCode,
            "articleId": articleId,
            "headline": headline,
        }
        self.news_queue.put(news_item)
        self.logger.info(f"Historical news received: {headline}")

    def create_stock_contract(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ):
        """
        Create a stock contract for a given symbol

        Args:
            symbol (str): Stock ticker symbol
            exchange (str): Trading exchange
            currency (str): Trading currency

        Returns:
            Contract: IB Contract object
        """
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency
        return contract

    def connect_to_tws(self):
        """
        Establish connection to TWS
        """
        try:
            self.connect(self.host, self.port, clientId=1)
            threading.Thread(target=self.run, daemon=True).start()

            # Wait for connection
            self.is_connected = True
            self.logger.info(f"Connected to TWS at {self.host}:{self.port}")

            # Request news providers
            self.reqNewsProviders()
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.is_connected = False

    def disconnect_from_tws(self):
        """
        Disconnect from TWS
        """
        if self.is_connected:
            self.disconnect()
            self.is_connected = False
            self.logger.info("Disconnected from TWS")

    def request_news_for_symbol(self, symbol: str, nr_articles: int = 10):
        """
        Request news for a specific stock symbol

        Args:
            symbol (str): Stock ticker symbol
            nr_articles (int): Number of articles to retrieve
        """
        if not self.is_connected:
            self.logger.error("Not connected to TWS")
            return

        contract = self.create_stock_contract(symbol)

        # Attempt to get contract details
        self.reqContractDetails(1, contract)

        # Correct method signature for reqHistoricalNews
        self.reqHistoricalNews(
            reqId=len(self.subscribed_symbols),
            contractId=0,  # Set to 0 if using symbol
            providerCodes="BRFG,RNTD",  # Bloomberg, Reuters
            startDateTime="",
            endDateTime="",
            totalResults=nr_articles,
        )

        self.subscribed_symbols.add(symbol)
        self.logger.info(f"Requested news for {symbol}")

    def contractDetails(self, reqId, contractDetails):
        """
        Receive contract details
        """
        self.logger.info(
            f"Contract Details for reqId {reqId}: {contractDetails.contract}"
        )

    def contractDetailsEnd(self, reqId):
        """
        Indicates end of contract details retrieval
        """
        self.logger.info(f"Contract Details retrieval completed for reqId {reqId}")

    def retrieve_news_articles(self, timeout: float = 10.0):
        """
        Retrieve news articles from the queue

        Args:
            timeout (float): Queue retrieval timeout

        Returns:
            List[dict]: List of news articles
        """
        articles = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                article = self.news_queue.get(timeout=1)
                articles.append(article)
            except queue.Empty:
                break

        return articles


def main():
    # Big cap US stocks to monitor
    big_cap_stocks = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

    # Initialize news client
    news_client = NewsAPIClient()

    try:
        # Connect to TWS
        news_client.connect_to_tws()

        # Wait a moment for connection to establish
        time.sleep(2)

        # Request news for big cap stocks
        for symbol in big_cap_stocks:
            news_client.request_news_for_symbol(symbol)

        # Wait for news to be retrieved
        time.sleep(10)

        # Retrieve news articles
        articles = news_client.retrieve_news_articles()

        # Process and print articles
        for article in articles:
            print(f"Article Details: {article}")

    except Exception as e:
        print(f"Error in main execution: {e}")

    finally:
        # Disconnect from TWS
        news_client.disconnect_from_tws()


if __name__ == "__main__":
    main()
