"""Vendor interface adapters — api-data-sources.md R5.

The ONLY place in the codebase permitted to import a vendor SDK (`alpaca`,
`nasdaqdatalink`). No agent, protocol, ingestion, or ops code calls a vendor SDK
directly; everything goes through the abstract contracts here. Enforced by
tests/test_no_vendor_leakage.py.
"""

from data.interfaces.base import (
    MarketDataInterface,
    FundamentalsInterface,
    BrokerInterface,
    DocumentsInterface,
)
from data.interfaces.sharadar import SharadarData
from data.interfaces.alpaca import AlpacaMarketData, AlpacaBroker

__all__ = [
    "MarketDataInterface",
    "FundamentalsInterface",
    "BrokerInterface",
    "DocumentsInterface",
    "SharadarData",
    "AlpacaMarketData",
    "AlpacaBroker",
]
