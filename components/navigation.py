"""Shared navigation controls for cross-page company links."""

from __future__ import annotations

import streamlit as st

COMPANY_PROFILE_REQUESTED_TICKER = "_company_profile_requested_ticker"


def company_profile_button(ticker: str, label: str, key: str) -> None:
    """Open the company profile while preserving the selected ticker."""
    if st.button(label, key=key):
        st.session_state[COMPANY_PROFILE_REQUESTED_TICKER] = ticker
        st.query_params["ticker"] = ticker
        st.switch_page("pages/9_企業カルテ.py")
