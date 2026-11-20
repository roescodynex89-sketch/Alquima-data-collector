"""RSS feed list for Card 5. (category, source name, url).
A feed that fails or changes URL is logged and skipped; the rest still work."""
from urllib.parse import quote_plus

_GN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def gnews(query):
    return _GN.format(q=quote_plus(query))


FEEDS = [
    # Crypto + crypto-related US law
    ("CRYPTO", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CRYPTO", "Cointelegraph", "https://cointelegraph.com/rss"),
    ("CRYPTO", "Decrypt", "https://decrypt.co/feed"),
    ("CRYPTO", "Google News: bitcoin ETF", gnews("bitcoin ETF inflows when:1d")),
    ("US_LAW_CLARITY", "Google News: crypto law", gnews('"CLARITY Act" OR "crypto regulation" OR "SEC crypto" when:1d')),
    # US macro
    ("US_MACRO", "CNBC Economy", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("US_MACRO", "CNBC Finance", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("US_MACRO", "Google News: Fed/inflation", gnews("Federal Reserve rate cut inflation CPI PCE Powell when:1d")),
    # Crypto stocks
    ("CRYPTO_STOCKS", "Yahoo Finance MSTR", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=MSTR&region=US&lang=en-US"),
    ("CRYPTO_STOCKS", "Yahoo Finance STRC", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=STRC&region=US&lang=en-US"),
    ("CRYPTO_STOCKS", "Yahoo Finance COIN", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=COIN&region=US&lang=en-US"),
    # War / geopolitics
    ("WAR_GEOPOLITICS", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("WAR_GEOPOLITICS", "Google News: US military/war", gnews("US military OR war OR sanctions OR Iran OR Russia OR Taiwan when:1d")),
]