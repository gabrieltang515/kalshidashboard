"""
app.py - Kalshi Markets Dashboard (Streamlit Frontend)

Displays prediction market questions with ALL their polling options.
For example: "Who will Trump nominate as Fed Chair?"
  - Kevin Warsh: 96%
  - Judy Shelton: 3%
  - Rick Rieder: 0%
"""

import streamlit as st
from datetime import datetime
from kalshi_client import get_client, EventData, MarketOption


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Kalshi Markets Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# =============================================================================
# CUSTOM CSS STYLING
# =============================================================================

st.markdown("""
<style>
    /* Option row styling */
    .option-row {
        display: flex;
        justify-content: space-between;
        padding: 8px 0;
        border-bottom: 1px solid #333;
    }
    
    /* Progress bar colors */
    .stProgress > div > div > div > div {
        background-color: #00C853;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA FETCHING WITH CACHING
# =============================================================================

@st.cache_data(ttl=60)
def fetch_events_for_category(category: str, top_n: int = 10, sort_by: str = "volume") -> list[EventData]:
    """
    Fetch top events (with all their options) for a category.
    
    Returns EventData objects that contain ALL polling options for each question.
    
    Args:
        category: Category to fetch (Economics, Crypto, Politics)
        top_n: Number of events to return
        sort_by: Sort criteria - "volume" (24h volume) or "price_change" (biggest movers)
    """
    client = get_client()
    return client.get_top_events_by_category(category, top_n=top_n, sort_by=sort_by)


# =============================================================================
# UI COMPONENTS
# =============================================================================

def display_event_card(event: EventData, index: int, show_price_change: bool = False):
    """
    Display an event (question) with ALL its polling options.
    
    Example output:
    ┌─────────────────────────────────────────────────────────┐
    │ #1  Who will Trump nominate as Fed Chair?              │
    │     Total Volume: 3,275,000  |  6 options              │
    │─────────────────────────────────────────────────────────│
    │     Kevin Warsh          ████████████████████░░░  96%  │
    │     Judy Shelton         █░░░░░░░░░░░░░░░░░░░░░░   3%  │
    │     Rick Rieder          ░░░░░░░░░░░░░░░░░░░░░░░   0%  │
    │     Christopher Waller   ░░░░░░░░░░░░░░░░░░░░░░░   0%  │
    └─────────────────────────────────────────────────────────┘
    """
    with st.container():
        # Header: Question title
        col_rank, col_title = st.columns([0.5, 6])
        
        with col_rank:
            st.markdown(f"### #{index}")
        
        with col_title:
            st.markdown(f"### {event.title}")
            
            # Show different info based on sort mode
            if show_price_change and event.max_price_change != 0:
                change_str = f"+{event.max_price_change}" if event.max_price_change > 0 else str(event.max_price_change)
                change_color = "green" if event.max_price_change > 0 else "red"
                st.caption(
                    f"📈 Max 24h Change: **:{change_color}[{change_str}%]**  |  "
                    f"📊 Volume: **{event.total_volume:,}**  |  {event.num_markets} options"
                )
            else:
                st.caption(f"📊 Total Volume: **{event.total_volume:,}** contracts  |  {event.num_markets} options")
        
        # Display all options with their percentages
        for option in event.options:
            display_option_row(option, show_price_change=show_price_change)
        
        st.divider()


def display_option_row(option: MarketOption, show_price_change: bool = False):
    """
    Display a single option with its percentage as a progress bar.
    
    Example: Kevin Warsh  ████████████████████░░░  96%  +5%
    """
    if show_price_change:
        col_name, col_bar, col_pct, col_change = st.columns([2.5, 3, 0.8, 1.2])
    else:
        col_name, col_bar, col_pct, col_vol = st.columns([2.5, 3, 0.8, 1.2])
    
    with col_name:
        st.write(option.name)
    
    with col_bar:
        # Progress bar shows the probability visually
        st.progress(option.probability / 100)
    
    with col_pct:
        # Large percentage display
        st.markdown(f"**{option.probability}%**")
    
    if show_price_change:
        with col_change:
            # Show price change with color
            if option.price_change_24h != 0:
                change_str = f"+{option.price_change_24h}" if option.price_change_24h > 0 else str(option.price_change_24h)
                color = "green" if option.price_change_24h > 0 else "red"
                st.markdown(f":{color}[{change_str}%]")
            else:
                st.caption("—")
    else:
        with col_vol:
            # Volume for this option
            if option.volume_24h > 0:
                st.caption(f"Vol: {option.volume_24h:,}")


def display_summary(categories_data: dict):
    """Display summary metrics across all categories."""
    total_events = sum(len(events) for events in categories_data.values())
    total_volume = sum(
        event.total_volume 
        for events in categories_data.values() 
        for event in events
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Questions", total_events)
    
    with col2:
        st.metric("Total 24h Volume", f"{total_volume:,}")
    
    with col3:
        st.metric("Last Updated", datetime.now().strftime("%H:%M:%S"))


# =============================================================================
# SIDEBAR
# =============================================================================

def render_sidebar() -> dict:
    """Render settings sidebar."""
    with st.sidebar:
        st.title("⚙️ Settings")
        st.markdown("---")
        
        top_n = st.slider(
            "Questions per category",
            min_value=5,
            max_value=20,
            value=10,
            step=5,
            help="Number of top questions to display"
        )
        
        st.markdown("---")
        
        sort_by = st.selectbox(
            "Sort by",
            options=["volume", "price_change"],
            format_func=lambda x: {
                "volume": "📊 24h Volume",
                "price_change": "📈 Biggest Movers (24h)"
            }.get(x, x),
            help="Volume = most traded. Price Change = biggest percentage point changes in last 24h."
        )
        
        if sort_by == "price_change":
            st.caption("Extra API call, slower loading")
        
        st.markdown("---")
        
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        st.caption(f"Rendered: {datetime.now().strftime('%H:%M:%S')}")
        
        return {"top_n": top_n, "sort_by": sort_by}


# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    """Main application."""
    settings = render_sidebar()
    top_n = settings["top_n"]
    sort_by = settings["sort_by"]
    
    # Title
    st.title("📊 Kalshi Markets")
    st.markdown("""
    See what the crowd predicts for key questions in **Economics** and **Politics**.
    
    Each question shows all available options with their current probability based on market trades.
    """)
    
    st.markdown("---")
    
    # Fetch data for all categories
    categories_config = [
        ("Economics", "Economics", "💰"),
        ("Politics", "Politics", "🏛️"),
    ]
    
    categories_data = {}
    
    loading_msg = "Loading market data..."
    if sort_by == "price_change":
        loading_msg = "Loading market data and fetching 24h price changes"
    
    with st.spinner(loading_msg):
        for category, display_name, _ in categories_config:
            try:
                events = fetch_events_for_category(category, top_n=top_n, sort_by=sort_by)
                categories_data[category] = events
            except Exception as e:
                st.error(f"Error fetching {category}: {e}")
                categories_data[category] = []
    
    # Summary metrics
    st.markdown("### 📈 Overview")
    display_summary(categories_data)
    
    st.markdown("---")
    
    # Tabs for each category
    tab_economics, tab_politics = st.tabs([
        "💰 Economics",
        "🏛️ Politics"
    ])
    
    # Economics Tab
    with tab_economics:
        events = categories_data.get("Economics", [])
        if events:
            for i, event in enumerate(events, 1):
                display_event_card(event, i, show_price_change=(sort_by == "price_change"))
        else:
            st.info("No Economics questions found.")
    
    # Politics Tab
    with tab_politics:
        events = categories_data.get("Politics", [])
        if events:
            for i, event in enumerate(events, 1):
                display_event_card(event, i, show_price_change=(sort_by == "price_change"))
        else:
            st.info("No Politics questions found.")
    
    # Footer
    st.markdown("---")
    st.caption(
        "Data from [Kalshi API](https://docs.kalshi.com). "
        "Percentages = market-implied probabilities. "
        "Not financial advice."
    )


if __name__ == "__main__":
    main()
