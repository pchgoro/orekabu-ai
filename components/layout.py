"""Shared responsive layout adjustments for operational pages."""

from __future__ import annotations

import streamlit as st


def apply_responsive_styles() -> None:
    """Keep controls readable and tappable on narrow screens."""
    st.markdown(
        """
        <style>
        [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] { overflow-wrap: anywhere; }
        @media (max-width: 640px) {
          [data-testid="stHorizontalBlock"] { gap: 0.5rem; }
          .stButton button, .stLinkButton a { min-height: 2.75rem; width: 100%; white-space: normal; }
          [data-testid="stMetric"] { min-width: 0; }
          [data-testid="stMetricLabel"], [data-testid="stMetricValue"] { overflow-wrap: anywhere; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
