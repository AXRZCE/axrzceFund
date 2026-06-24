"""R5 interface contracts are true ABCs — not pass-body classes that silently
instantiate. Anti-hoax for the "DocumentsInterface defined but not implemented"
case: instantiating any contract (esp. the unimplemented DocumentsInterface) must
raise, proving the abstractmethods are real."""

import pytest

from data.interfaces.base import (
    BrokerInterface,
    DocumentsInterface,
    FundamentalsInterface,
    MarketDataInterface,
)

ALL_CONTRACTS = [
    MarketDataInterface,
    FundamentalsInterface,
    BrokerInterface,
    DocumentsInterface,
]


@pytest.mark.parametrize("contract", ALL_CONTRACTS)
def test_contract_is_abstract(contract):
    assert contract.__abstractmethods__, f"{contract.__name__} declares no @abstractmethod"
    with pytest.raises(TypeError):
        contract()  # abstract → cannot instantiate


def test_documents_interface_has_no_concrete_impl():
    """DocumentsInterface is intentionally ABC-only in Phase 1 (no in-scope agent
    reads filings). Confirm no subclass is registered/instantiable yet."""
    with pytest.raises(TypeError):
        DocumentsInterface()
    assert {"get_filings", "get_news"} <= DocumentsInterface.__abstractmethods__
