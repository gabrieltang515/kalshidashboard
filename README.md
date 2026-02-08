# Kalshi Markets Dashboard

A Streamlit dashboard that displays the top 10 prediction markets from Kalshi across Economics, Crypto, and Politics categories.

## 🏗️ Project Structure

```
kalshidashboard/
├── app.py              # Main Streamlit application (Frontend)
├── kalshi_client.py    # Kalshi API client (Backend/Data Layer)
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## 📊 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER'S BROWSER                                │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    Streamlit Dashboard                          │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │  │
│   │  │Economics │  │  Crypto  │  │ Politics │  ← Tabs              │  │
│   │  └──────────┘  └──────────┘  └──────────┘                      │  │
│   │                                                                 │  │
│   │  ┌─────────────────────────────────────────────────────────┐   │  │
│   │  │ Market Card: Fed Decision March 2026                    │   │  │
│   │  │ Probability: 90%  |  24h Volume: 50,000  |  Change: +2% │   │  │
│   │  └─────────────────────────────────────────────────────────┘   │  │
│   └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ HTML/CSS/JS
                                    │ (Streamlit renders automatically)
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                         app.py (Frontend Logic)                         │
│                                                                         │
│  1. st.set_page_config()     → Configure page settings                 │
│  2. render_sidebar()          → Create settings panel                   │
│  3. fetch_markets_for_category() → Get data (with caching)             │
│  4. display_market_card()     → Create UI components                    │
│  5. st.metric(), st.columns() → Render visual elements                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ List[MarketData] objects
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                    kalshi_client.py (Data Layer)                        │
│                                                                         │
│  KalshiClient class:                                                    │
│  1. get_events()              → Fetch events from API                   │
│  2. get_top_markets_by_category() → Filter & sort markets              │
│  3. _parse_market()           → Convert JSON to MarketData objects     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ HTTP GET Request
                                    │ (using 'requests' library)
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                         Kalshi REST API                                 │
│                                                                         │
│  Base URL: https://api.elections.kalshi.com/trade-api/v2               │
│                                                                         │
│  Endpoints Used:                                                        │
│  • GET /events     → Returns all events with optional nested markets   │
│  • GET /markets    → Returns all markets with prices and volume        │
│  • GET /series     → Returns series (templates for recurring events)   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ JSON Response
                                    │
┌─────────────────────────────────────────────────────────────────────────┐
│                         Kalshi Exchange                                 │
│                                                                         │
│  Real prediction markets where users trade on future events:           │
│  • Economics: Fed rates, inflation, jobs reports                       │
│  • Crypto: Bitcoin/Ethereum price predictions                          │
│  • Politics: Election outcomes, policy decisions                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Navigate to the project directory
cd kalshidashboard

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 2. Run the Dashboard

```bash
streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501`

## 📖 Understanding the Code

### kalshi_client.py - The Data Layer

This file handles all communication with the Kalshi API:

| Function | Purpose |
|----------|---------|
| `get_events()` | Fetches events (groups of related markets) |
| `get_markets()` | Fetches individual markets with prices |
| `get_top_markets_by_category()` | **Main function** - filters and sorts markets |
| `_parse_market()` | Converts raw JSON to `MarketData` objects |

**Key Concept: MarketData Class**
```python
@dataclass
class MarketData:
    ticker: str           # "FEDMAR26-HOLD"
    yes_sub_title: str    # "Fed maintains rate"
    yes_price: float      # 0.90 (90% probability)
    volume_24h: int       # 50000 (contracts traded)
    ...
```

### app.py - The Frontend

This file creates the web interface using Streamlit:

| Function | Purpose |
|----------|---------|
| `fetch_markets_for_category()` | Calls API with caching (60s TTL) |
| `display_market_card()` | Renders one market as a card |
| `display_category_section()` | Shows all markets for a category |
| `render_sidebar()` | Creates the settings panel |
| `main()` | Entry point - orchestrates everything |

**Key Concept: Caching**
```python
@st.cache_data(ttl=60)  # Cache results for 60 seconds
def fetch_markets_for_category(category: str):
    # This only makes an API call once per minute
    # Subsequent calls return cached data instantly
    ...
```

## 🔑 Key Kalshi API Concepts

### Events vs Markets

- **Event**: A real-world occurrence (e.g., "Fed March 2026 Meeting")
- **Market**: A specific tradeable outcome within an event (e.g., "Fed maintains rate")

### Price = Probability

- Market prices range from $0.01 to $0.99
- Price = market's implied probability of YES
- Example: Price of $0.75 = 75% chance of YES

### Key API Fields

| Field | Description |
|-------|-------------|
| `yes_bid_dollars` | Current best bid price for YES |
| `last_price_dollars` | Most recent trade price |
| `previous_price_dollars` | Price 24 hours ago |
| `volume_24h` | Contracts traded in last 24h |
| `open_interest` | Total outstanding contracts |

## 🔧 Customization

### Adding More Categories

1. Open `app.py`
2. Find the `categories_config` list
3. Add your new category:

```python
categories_config = [
    ("Economics", "Economics", "💰"),
    ("Crypto", "Crypto", "₿"),
    ("Politics", "Politics", "🏛️"),
    ("Sports", "Sports", "⚽"),  # Add this line
]
```

### Changing Refresh Rate

In `app.py`, modify the cache TTL:

```python
@st.cache_data(ttl=30)  # Change to 30 seconds
def fetch_markets_for_category(...):
```

### Adding Authentication (for WebSocket real-time updates)

See [Kalshi API Keys documentation](https://docs.kalshi.com/getting_started/api_keys)

## 📚 Further Reading

- [Kalshi API Documentation](https://docs.kalshi.com)
- [Streamlit Documentation](https://docs.streamlit.io)
- [Python Requests Library](https://requests.readthedocs.io)

## ⚠️ Disclaimer

This is an educational project. Market data is for informational purposes only.
This is not financial advice. Trade responsibly.
