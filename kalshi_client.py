"""
kalshi_client.py - Kalshi API Client

This module handles all communication with the Kalshi API.
It acts as the DATA LAYER of our application.

DATA FLOW:
    Kalshi API (Internet) 
        → HTTP Request (requests library)
        → JSON Response 
        → Python Dictionary 
        → Processed Data (list of market dicts)
        → Return to app.py

The Kalshi API is a REST API that returns JSON data.
We don't need authentication for public market data.
"""

import requests
from typing import Optional
from dataclasses import dataclass

# =============================================================================
# CONFIGURATION
# =============================================================================

# Base URL for all Kalshi API requests
# Note: Despite "elections" in the URL, this serves ALL markets (crypto, economics, etc.)
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Request timeout in seconds
REQUEST_TIMEOUT = 30


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MarketOption:
    """
    Represents a single option/outcome within an event.
    
    For example, for "Who will Trump nominate as Fed Chair?":
    - Option 1: Kevin Warsh (96%)
    - Option 2: Judy Shelton (3%)
    - Option 3: Rick Rieder (0%)
    """
    name: str           # Option name (e.g., "Kevin Warsh")
    probability: int    # Probability percentage (0-100)
    volume_24h: int     # 24h volume for this option
    ticker: str         # Market ticker
    price_change_24h: int = 0  # Price change in last 24h (percentage points)
    series_ticker: str = ""    # Series ticker for API calls


@dataclass
class EventData:
    """
    Represents an event with ALL its market options.
    
    This groups all options for a single question together,
    so you can see: "Fed Chair: Kevin Warsh 96%, Judy Shelton 3%, ..."
    """
    event_ticker: str           # Unique event identifier
    title: str                  # Event question (e.g., "Who will Trump nominate as Fed Chair?")
    category: str               # Category (Politics, Economics, etc.)
    options: list[MarketOption] # All options with their probabilities
    total_volume: int           # Total 24h volume across all options
    num_markets: int            # Number of options/markets
    max_price_change: int = 0   # Maximum absolute price change among all options
    series_ticker: str = ""     # Series ticker
    
    def get_top_options(self, n: int = 5) -> list[MarketOption]:
        """Get top N options sorted by probability."""
        return sorted(self.options, key=lambda x: x.probability, reverse=True)[:n]


@dataclass
class MarketData:
    """
    Represents a single market from Kalshi.
    
    A 'market' is a specific yes/no question users can trade on.
    For example: "Will the Fed raise rates in March 2026?"
    
    The price represents the market's implied probability.
    A price of $0.75 means the market thinks there's a 75% chance of YES.
    
    SENTIMENT INTERPRETATION:
    - Price near 90-100%: Strong consensus that YES will happen
    - Price near 50%: Uncertainty, market is split
    - Price near 0-10%: Strong consensus that NO will happen
    """
    ticker: str              # Unique market identifier (e.g., "FEDMAR26-HOLD")
    event_ticker: str        # Parent event identifier
    event_title: str         # Event question (e.g., "Fed decision in March?")
    title: str               # Human-readable market title
    yes_sub_title: str       # Short description of the YES outcome
    no_sub_title: str        # Short description of the NO outcome
    
    # Prices are in dollars (e.g., "0.7500" = 75 cents = 75% probability)
    yes_price: float         # Current YES price (bid)
    yes_ask: float           # Current YES ask price
    last_price: float        # Last traded price
    previous_price: float    # Price 24 hours ago
    
    # Volume and liquidity (indicates market activity/interest)
    volume_24h: int          # Number of contracts traded in last 24h
    open_interest: int       # Total outstanding contracts
    
    # Status
    status: str              # Market status (active, closed, etc.)
    category: str            # Market category (Economics, Politics, etc.)
    
    @property
    def probability_pct(self) -> int:
        """Convert price to percentage probability (= market sentiment)."""
        return int(self.yes_price * 100)
    
    @property
    def price_change_pct(self) -> float:
        """Calculate 24-hour price change as percentage points."""
        if self.previous_price > 0:
            return (self.last_price - self.previous_price) * 100
        return 0.0
    
    @property
    def sentiment(self) -> str:
        """
        Interpret market probability as sentiment.
        
        Returns human-readable sentiment based on the probability.
        """
        prob = self.probability_pct
        if prob >= 80:
            return "Very Likely"
        elif prob >= 60:
            return "Likely"
        elif prob >= 40:
            return "Uncertain"
        elif prob >= 20:
            return "Unlikely"
        else:
            return "Very Unlikely"


# =============================================================================
# API CLIENT CLASS
# =============================================================================

class KalshiClient:
    """
    Client for interacting with the Kalshi REST API.
    
    This class encapsulates all HTTP requests to Kalshi.
    It handles:
        - Making HTTP GET requests
        - Parsing JSON responses
        - Converting raw data to MarketData objects
        - Error handling
    
    Usage:
        client = KalshiClient()
        markets = client.get_markets_by_category("Economics")
    """
    
    def __init__(self, base_url: str = BASE_URL):
        """
        Initialize the client with the API base URL.
        
        Args:
            base_url: The Kalshi API base URL
        """
        self.base_url = base_url
        # Create a session for connection pooling (more efficient for multiple requests)
        self.session = requests.Session()
        # Set default headers
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
    
    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        Make an HTTP GET request to the Kalshi API.
        
        This is the core method that all other methods use.
        
        Args:
            endpoint: API endpoint (e.g., "/markets")
            params: Query parameters to include in the request
            
        Returns:
            JSON response as a Python dictionary
            
        Raises:
            requests.RequestException: If the request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            # Make the GET request
            response = self.session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            
            # Raise an exception for bad status codes (4xx, 5xx)
            response.raise_for_status()
            
            # Parse JSON and return
            return response.json()
            
        except requests.exceptions.Timeout:
            print(f"Request timed out: {url}")
            raise
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {url} - {e}")
            raise
    
    def get_events(
        self,
        status: str = "open",
        with_nested_markets: bool = True,
        limit: int = 200
    ) -> dict:
        """
        Fetch events from the Kalshi API.
        
        An 'event' is a real-world occurrence with multiple markets.
        For example, "Fed March 2026 Meeting" is an event that might have markets like:
            - "Will they raise rates?"
            - "Will they cut rates?"
            - "Will they hold rates?"
        
        Args:
            status: Filter by status ("open", "closed", "settled")
            with_nested_markets: If True, include market data within each event
            limit: Maximum number of events to return (max 200)
            
        Returns:
            Dictionary containing 'events' list and 'cursor' for pagination
        """
        params = {
            "status": status,
            "with_nested_markets": str(with_nested_markets).lower(),
            "limit": limit
        }
        
        return self._make_request("/events", params)
    
    def get_market_candlesticks(
        self,
        series_ticker: str,
        market_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int = 1440
    ) -> dict:
        """
        Fetch candlestick (historical price) data for a market.
        
        Args:
            series_ticker: Series ticker (e.g., "KXFED")
            market_ticker: Market ticker (e.g., "KXFED-26MAR19-T5.00")
            start_ts: Start Unix timestamp
            end_ts: End Unix timestamp
            period_interval: Candlestick period in minutes (1, 60, or 1440)
            
        Returns:
            Dictionary containing 'ticker' and 'candlesticks' list
        """
        endpoint = f"/series/{series_ticker}/markets/{market_ticker}/candlesticks"
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval
        }
        
        try:
            return self._make_request(endpoint, params)
        except Exception:
            # Return empty if candlesticks not available
            return {"candlesticks": []}
    
    def get_price_change_24h(self, series_ticker: str, market_ticker: str) -> int:
        """
        Calculate the 24-hour price change for a market.
        
        Returns the price change in percentage points (e.g., +5 means price went up 5%).
        """
        from datetime import datetime, timedelta
        
        end_ts = int(datetime.now().timestamp())
        start_ts = int((datetime.now() - timedelta(days=1)).timestamp())
        
        data = self.get_market_candlesticks(
            series_ticker=series_ticker,
            market_ticker=market_ticker,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=1440  # Daily candlestick
        )
        
        candlesticks = data.get("candlesticks", [])
        
        if candlesticks:
            # Get the most recent candlestick
            candle = candlesticks[-1]
            price = candle.get("price", {})
            
            # Calculate change from open to close, or use previous if available
            open_price = price.get("open", 0) or 0
            close_price = price.get("close", 0) or 0
            previous_price = price.get("previous", 0) or 0
            
            if previous_price:
                return close_price - previous_price
            elif open_price:
                return close_price - open_price
        
        return 0
    
    def get_markets(
        self,
        status: str = "open",
        limit: int = 1000,
        cursor: Optional[str] = None
    ) -> dict:
        """
        Fetch markets from the Kalshi API.
        
        This endpoint returns individual markets across all events.
        
        Args:
            status: Filter by status ("open", "closed", "settled")
            limit: Maximum number of markets to return (max 1000)
            cursor: Pagination cursor from previous request
            
        Returns:
            Dictionary containing 'markets' list and 'cursor' for pagination
        """
        params = {
            "status": status,
            "limit": limit
        }
        if cursor:
            params["cursor"] = cursor
            
        return self._make_request("/markets", params)
    
    def get_series(self, series_ticker: str) -> dict:
        """
        Fetch information about a specific series.
        
        A 'series' is a template for recurring events.
        For example, "Monthly Jobs Report" is a series that creates
        new events each month.
        
        Args:
            series_ticker: The series identifier (e.g., "KXFED")
            
        Returns:
            Dictionary containing series information
        """
        return self._make_request(f"/series/{series_ticker}")
    
    def get_series_list(self) -> dict:
        """
        Fetch all available series.
        
        Returns:
            Dictionary containing list of all series
        """
        return self._make_request("/series")
    
    def _parse_market(self, market_data: dict, event_title: str = "", category: str = "") -> MarketData:
        """
        Convert raw API response to a MarketData object.
        
        This method handles the transformation from raw JSON to our
        structured MarketData class.
        
        Args:
            market_data: Raw market dictionary from API
            event_title: Title of the parent event (provides context)
            category: Category of the market
            
        Returns:
            MarketData object
        """
        def safe_float(value, default=0.0):
            """Safely convert a value to float."""
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        def safe_int(value, default=0):
            """Safely convert a value to int."""
            if value is None:
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        
        return MarketData(
            ticker=market_data.get("ticker", ""),
            event_ticker=market_data.get("event_ticker", ""),
            event_title=event_title,
            title=market_data.get("title", ""),
            yes_sub_title=market_data.get("yes_sub_title", ""),
            no_sub_title=market_data.get("no_sub_title", ""),
            yes_price=safe_float(market_data.get("yes_bid_dollars")),
            yes_ask=safe_float(market_data.get("yes_ask_dollars")),
            last_price=safe_float(market_data.get("last_price_dollars")),
            previous_price=safe_float(market_data.get("previous_price_dollars")),
            volume_24h=safe_int(market_data.get("volume_24h")),
            open_interest=safe_int(market_data.get("open_interest")),
            status=market_data.get("status", ""),
            category=category
        )
    
    def get_top_markets_by_category(
        self,
        category: str,
        top_n: int = 10,
        sort_by: str = "volume"
    ) -> list[MarketData]:
        """
        Get the top N markets for a specific category, sorted by volume or open interest.
        
        This is the MAIN METHOD you'll use for the dashboard.
        
        HOW IT WORKS:
        1. Fetch all open events with nested markets
        2. Filter events by category using CATEGORY_MAPPING
        3. Extract all markets from matching events
        4. Sort by volume (most active) or open interest
        5. Return top N markets with sentiment data
        
        CATEGORY MAPPING (Kalshi's actual categories):
        - "Economics" → Financials (Fed decisions, inflation, rates, crypto prices)
        - "Crypto" → Financials (Bitcoin, Ethereum, etc.)
        - "Politics" → Politics + Elections
        
        Args:
            category: Category to filter by ("Economics", "Crypto", "Politics", etc.)
            top_n: Number of top markets to return
            sort_by: Sort criteria ("volume" or "open_interest")
            
        Returns:
            List of MarketData objects with sentiment interpretation
        """
        # =================================================================
        # CATEGORY MAPPING
        # =================================================================
        # Kalshi uses specific category names that may differ from common terms.
        # This mapping translates user-friendly names to Kalshi API categories.
        #
        # You can discover categories by running: client.get_all_categories()
        # Current Kalshi categories include:
        #   - Climate and Weather, Companies, Economics, Elections, Entertainment,
        #   - Financials, Health, Politics, Science and Technology, Social, 
        #   - Sports, Transportation, World
        
        CATEGORY_MAPPING = {
            # Economics: Include both "Economics" and "Financials" categories
            # Financials has Fed rates, inflation, crypto prices, etc.
            "economics": ["financials", "economics"],
            
            # Crypto: Maps to Financials where BTC/ETH markets live (with keyword filtering)
            "crypto": ["financials"],
            
            # Politics: Include both Politics and Elections
            "politics": ["politics", "elections"],
            
            # Direct mappings for other categories
            "elections": ["elections"],
            "financials": ["financials"],
            "sports": ["sports"],
            "entertainment": ["entertainment"],
            "climate": ["climate and weather"],
            "weather": ["climate and weather"],
            "health": ["health"],
            "science": ["science and technology"],
            "technology": ["science and technology"],
            "world": ["world"],
            "companies": ["companies"],
            "social": ["social"],
            "transportation": ["transportation"],
        }
        
        # Crypto-specific keywords to filter by title
        CRYPTO_KEYWORDS = [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
            "solana", "sol", "dogecoin", "doge", "xrp", "ripple", "cardano",
            "ada", "polkadot", "dot", "avalanche", "avax", "chainlink", "link",
            "polygon", "matic", "litecoin", "ltc", "uniswap", "uni", "shiba",
            "pepe", "memecoin", "altcoin", "defi", "nft", "web3", "binance",
            "coinbase", "stablecoin", "usdt", "usdc"
        ]
        
        # Step 1: Fetch all open events with their markets
        events_response = self.get_events(
            status="open",
            with_nested_markets=True,
            limit=200
        )
        
        events = events_response.get("events", [])
        
        # Step 2: Determine which Kalshi categories to search
        category_lower = category.lower()
        target_categories = CATEGORY_MAPPING.get(category_lower, [category_lower])
        
        # Step 3: Filter events by category and collect markets WITH context
        all_markets = []  # List of tuples: (market_dict, event_title, category)
        
        for event in events:
            event_category = event.get("category", "").lower()
            event_title = event.get("title", "")
            event_title_lower = event_title.lower()
            
            # Check if event category matches any of our target categories
            category_matches = any(
                target.lower() in event_category or event_category in target.lower()
                for target in target_categories
            )
            
            # Special handling for crypto: must match BOTH category AND keywords
            if category_lower == "crypto":
                keyword_matches = any(
                    keyword in event_title_lower for keyword in CRYPTO_KEYWORDS
                )
                matches = category_matches and keyword_matches
            else:
                # For non-crypto categories, exclude crypto-related events from economics
                if category_lower == "economics":
                    is_crypto = any(keyword in event_title_lower for keyword in CRYPTO_KEYWORDS)
                    matches = category_matches and not is_crypto
                else:
                    matches = category_matches
            
            if matches:
                # Extract markets from this event
                markets = event.get("markets", [])
                for market in markets:
                    # Only include active markets
                    if market.get("status") == "active":
                        all_markets.append({
                            "market": market,
                            "event_title": event_title,
                            "category": event.get("category", "")
                        })
        
        # Step 4: Sort markets by the specified criteria
        if sort_by == "volume":
            all_markets.sort(key=lambda m: m["market"].get("volume_24h", 0), reverse=True)
        elif sort_by == "open_interest":
            all_markets.sort(key=lambda m: m["market"].get("open_interest", 0), reverse=True)
        
        # Step 5: Take top N and convert to MarketData objects
        top_markets = all_markets[:top_n]
        
        return [
            self._parse_market(
                m["market"], 
                event_title=m["event_title"],
                category=m["category"]
            ) 
            for m in top_markets
        ]
    
    def get_all_categories(self) -> list[str]:
        """
        Get all unique categories from open events.
        
        Useful for discovering what categories are available.
        
        Returns:
            List of unique category names
        """
        events_response = self.get_events(status="open", with_nested_markets=False)
        events = events_response.get("events", [])
        
        categories = set()
        for event in events:
            category = event.get("category", "")
            if category:
                categories.add(category)
        
        return sorted(list(categories))
    
    def get_top_events_by_category(
        self,
        category: str,
        top_n: int = 10,
        sort_by: str = "volume"
    ) -> list[EventData]:
        """
        Get the top N EVENTS (with all their options) for a specific category.
        
        This groups all market options by their parent event, so you can see
        ALL options for a question like "Who will Trump nominate as Fed Chair?":
        - Kevin Warsh: 96%
        - Judy Shelton: 3%
        - Rick Rieder: 0%
        - etc.
        
        Args:
            category: Category to filter by ("Economics", "Crypto", "Politics", etc.)
            top_n: Number of top events to return
            sort_by: Sort criteria ("volume" or "num_markets")
            
        Returns:
            List of EventData objects, each containing all its market options
        """
        # Category mapping (same as get_top_markets_by_category)
        CATEGORY_MAPPING = {
            "economics": ["financials", "economics"],
            "crypto": ["financials"],  # Will also use keyword filtering
            "politics": ["politics", "elections"],
            "elections": ["elections"],
            "financials": ["financials"],
            "sports": ["sports"],
            "entertainment": ["entertainment"],
            "climate": ["climate and weather"],
            "weather": ["climate and weather"],
            "health": ["health"],
            "science": ["science and technology"],
            "technology": ["science and technology"],
            "world": ["world"],
            "companies": ["companies"],
            "social": ["social"],
            "transportation": ["transportation"],
        }
        
        # Crypto-specific keywords to filter by title
        # This ensures we only get actual crypto markets, not all financials
        CRYPTO_KEYWORDS = [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
            "solana", "sol", "dogecoin", "doge", "xrp", "ripple", "cardano",
            "ada", "polkadot", "dot", "avalanche", "avax", "chainlink", "link",
            "polygon", "matic", "litecoin", "ltc", "uniswap", "uni", "shiba",
            "pepe", "memecoin", "altcoin", "defi", "nft", "web3", "binance",
            "coinbase", "stablecoin", "usdt", "usdc"
        ]
        
        # Step 1: Fetch all open events with their markets
        events_response = self.get_events(
            status="open",
            with_nested_markets=True,
            limit=200
        )
        
        events = events_response.get("events", [])
        
        # Step 2: Determine which Kalshi categories to search
        category_lower = category.lower()
        target_categories = CATEGORY_MAPPING.get(category_lower, [category_lower])
        
        # Step 3: Filter events by category and build EventData objects
        all_events = []
        
        for event in events:
            event_category = event.get("category", "").lower()
            event_title = event.get("title", "").lower()
            
            # Check if event category matches any of our target categories
            category_matches = any(
                target.lower() in event_category or event_category in target.lower()
                for target in target_categories
            )
            
            # Special handling for crypto: must match BOTH category AND keywords
            if category_lower == "crypto":
                keyword_matches = any(
                    keyword in event_title for keyword in CRYPTO_KEYWORDS
                )
                matches = category_matches and keyword_matches
            else:
                # For non-crypto categories, exclude crypto-related events from economics
                if category_lower == "economics":
                    is_crypto = any(keyword in event_title for keyword in CRYPTO_KEYWORDS)
                    matches = category_matches and not is_crypto
                else:
                    matches = category_matches
            
            if not matches:
                continue
            
            # Get all markets (options) for this event
            markets = event.get("markets", [])
            active_markets = [m for m in markets if m.get("status") == "active"]
            
            if not active_markets:
                continue
            
            # Get series ticker for this event
            series_ticker = event.get("series_ticker", "")
            
            # Convert markets to MarketOption objects
            options = []
            total_volume = 0
            
            for market in active_markets:
                # Get probability from yes_bid_dollars (convert to percentage)
                yes_price = market.get("yes_bid_dollars", "0")
                try:
                    probability = int(float(yes_price) * 100)
                except (ValueError, TypeError):
                    probability = 0
                
                volume = market.get("volume_24h", 0) or 0
                total_volume += volume
                
                options.append(MarketOption(
                    name=market.get("yes_sub_title", "Unknown"),
                    probability=probability,
                    volume_24h=volume,
                    ticker=market.get("ticker", ""),
                    price_change_24h=0,  # Will be populated later if sorting by price_change
                    series_ticker=series_ticker
                ))
            
            # Sort options by probability (highest first)
            options.sort(key=lambda x: x.probability, reverse=True)
            
            # Create EventData object
            event_data = EventData(
                event_ticker=event.get("event_ticker", ""),
                title=event.get("title", ""),
                category=event.get("category", ""),
                options=options,
                total_volume=total_volume,
                num_markets=len(options),
                max_price_change=0,  # Will be populated later if sorting by price_change
                series_ticker=series_ticker
            )
            
            all_events.append(event_data)
        
        # Step 4: Sort events by the specified criteria
        if sort_by == "volume":
            all_events.sort(key=lambda e: e.total_volume, reverse=True)
        elif sort_by == "num_markets":
            all_events.sort(key=lambda e: e.num_markets, reverse=True)
        elif sort_by == "price_change":
            # Fetch price change data for each event's options
            # This makes additional API calls, so it's slower
            for event_data in all_events:
                max_change = 0
                for option in event_data.options:
                    if option.series_ticker and option.ticker:
                        try:
                            change = self.get_price_change_24h(
                                option.series_ticker, 
                                option.ticker
                            )
                            option.price_change_24h = change
                            if abs(change) > abs(max_change):
                                max_change = change
                        except Exception:
                            pass  # Skip if can't get price change
                event_data.max_price_change = max_change
            
            # Sort by absolute price change (biggest movers first)
            all_events.sort(key=lambda e: abs(e.max_price_change), reverse=True)
        
        # Step 5: Return top N events
        return all_events[:top_n]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_client() -> KalshiClient:
    """
    Factory function to create a KalshiClient instance.
    
    This makes it easy to create clients throughout the app.
    
    Returns:
        A new KalshiClient instance
    """
    return KalshiClient()


# =============================================================================
# TEST CODE (runs when you execute this file directly)
# =============================================================================

if __name__ == "__main__":
    # Test the client
    print("Testing Kalshi Client...")
    print("=" * 50)
    
    client = get_client()
    
    # Test getting categories
    print("\n1. Available Categories:")
    try:
        categories = client.get_all_categories()
        for cat in categories:
            print(f"   - {cat}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test getting top markets for Economics
    print("\n2. Top 5 Economics Markets (by volume):")
    try:
        markets = client.get_top_markets_by_category("Economics", top_n=5)
        for i, market in enumerate(markets, 1):
            print(f"   {i}. {market.yes_sub_title}")
            print(f"      Probability: {market.probability_pct}%")
            print(f"      24h Volume: {market.volume_24h:,}")
            print(f"      Change: {market.price_change_pct:+.1f}pp")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n" + "=" * 50)
    print("Test complete!")
