"""Adapter behavior-preservation (the load-bearing WP0 proof, re-runnable).

Each R5 adapter must return EXACTLY what the raw vendor SDK returns for the same
call — catching any silent row-order / dtype / serialization drift introduced at
the boundary. This file deliberately imports the vendor SDK to compare against;
it is the ONE allowlisted exception in tests/test_no_vendor_leakage.py (integration
tests may reference raw vendors by their nature) and lives under tests/integration/.

Gated `@pytest.mark.integration` (excluded from the default `pytest` run via
addopts) and skipped without credentials — so it stays out of default CI but is
re-runnable on demand:  pytest -m integration

Replaces the deleted one-off `_equiv_check.py`: the repo must be able to re-run its
own evidence, including this proof.
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()  # pick up .env so creds are present when running on a configured host

pytestmark = pytest.mark.integration

_NDL_KEY = os.environ.get("NASDAQ_DATA_LINK_API_KEY")
_needs_sharadar = pytest.mark.skipif(not _NDL_KEY, reason="NASDAQ_DATA_LINK_API_KEY not set")


@_needs_sharadar
def test_sharadar_sep_adapter_byte_identical_to_raw_sdk():
    """SEP historical bars: SharadarData.get_daily_bars == raw nasdaqdatalink call."""
    import nasdaqdatalink as ndl
    import pandas as pd

    from data.interfaces import SharadarData

    ndl.ApiConfig.api_key = _NDL_KEY
    from datetime import datetime, timedelta, timezone
    d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    raw = ndl.get_table("SHARADAR/SEP", ticker=["AAPL"], date={"gte": d}, paginate=True)
    adp = SharadarData().get_daily_bars(tickers=["AAPL"], window_days=7)

    pd.testing.assert_frame_equal(adp.reset_index(drop=True), raw.reset_index(drop=True))


@_needs_sharadar
def test_sharadar_sp500_adapter_byte_identical_to_raw_sdk():
    """Index constituents (a fully stable historical table): adapter == raw call."""
    import nasdaqdatalink as ndl
    import pandas as pd

    from data.interfaces import SharadarData

    ndl.ApiConfig.api_key = _NDL_KEY
    raw = ndl.get_table("SHARADAR/SP500", paginate=True)
    adp = SharadarData().get_index_constituents("SP500")

    pd.testing.assert_frame_equal(adp.reset_index(drop=True), raw.reset_index(drop=True))


@pytest.mark.skipif(
    not (os.environ.get("APCA_API_KEY_ID") and os.environ.get("APCA_API_SECRET_KEY")),
    reason="Alpaca keys not set")
def test_alpaca_iex_adapter_contract():
    """The IEX adapter builds the bars DataFrame itself (no SDK df to byte-compare),
    so this asserts its output contract: expected columns, float OHLC dtypes, and
    rows for the requested symbol — proving it returns real, well-formed bars."""
    from data.interfaces import AlpacaMarketData

    df = AlpacaMarketData().get_daily_bars(["AAPL"], window_days=14)
    assert list(df.columns) == ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) > 0 and set(df["symbol"]) == {"AAPL"}
    for col in ("open", "high", "low", "close"):
        assert str(df[col].dtype) == "float64"
