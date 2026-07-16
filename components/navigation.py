"""Shared navigation controls for cross-page company links."""

from __future__ import annotations

import streamlit as st


def company_profile_button(ticker: str, label: str, key: str) -> None:
    """Open the company profile while preserving the selected ticker."""
    if st.button(label, key=key):
        st.query_params["ticker"] = ticker
        st.switch_page("pages/9_企業カルテ.py")
