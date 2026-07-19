"""Cross-page company profile navigation tests."""

from components import navigation


def test_company_profile_button_sets_ticker_and_opens_profile(monkeypatch) -> None:
    opened: list[str] = []
    query_params: dict[str, str] = {}
    session_state: dict[str, str] = {}

    monkeypatch.setattr(navigation.st, "button", lambda *args, **kwargs: True)
    monkeypatch.setattr(navigation.st, "query_params", query_params)
    monkeypatch.setattr(navigation.st, "session_state", session_state)
    monkeypatch.setattr(navigation.st, "switch_page", opened.append)

    navigation.company_profile_button("5801.T", "企業カルテを開く", "profile")

    assert query_params["ticker"] == "5801.T"
    assert session_state[navigation.COMPANY_PROFILE_REQUESTED_TICKER] == "5801.T"
    assert opened == ["pages/9_企業カルテ.py"]
