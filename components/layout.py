"""Shared responsive layout adjustments for operational pages."""

from __future__ import annotations

import streamlit as st

from components.ui import density_padding


def apply_responsive_styles(density: str = "標準") -> None:
    """Apply the shared color system, density, and narrow-screen safeguards."""
    padding = density_padding(density)
    st.markdown(
        f"""
        <style>
        :root {{
          --orekabu-positive: #ff626b;
          --orekabu-negative: #35c98b;
          --orekabu-warning: #f4c84a;
          --orekabu-info: #55a7ff;
          --orekabu-muted: #98a2b3;
          --orekabu-surface: rgba(255, 255, 255, 0.035);
        }}
        [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {{ overflow-wrap: anywhere; }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
          border-radius: 6px;
        }}
        .orekabu-badge {{
          display: inline-flex;
          align-items: center;
          min-height: 1.55rem;
          padding: 0.15rem 0.5rem;
          border-radius: 4px;
          color: white;
          font-size: 0.78rem;
          font-weight: 700;
        }}
        .orekabu-positive {{ background: var(--orekabu-positive); color: #18181b; }}
        .orekabu-negative {{ background: var(--orekabu-negative); color: #071a12; }}
        .orekabu-urgent, .orekabu-danger {{ background: var(--orekabu-warning); color: #171717; }}
        .orekabu-today, .orekabu-warning {{ background: var(--orekabu-warning); color: #171717; }}
        .orekabu-later, .orekabu-info {{ background: var(--orekabu-info); }}
        .orekabu-success {{ background: var(--orekabu-info); }}
        .orekabu-muted {{ background: var(--orekabu-muted); }}
        .orekabu-text-positive {{ color: var(--orekabu-positive); }}
        .orekabu-text-negative {{ color: var(--orekabu-negative); }}
        .orekabu-text-warning {{ color: var(--orekabu-warning); }}
        .orekabu-text-info {{ color: var(--orekabu-info); }}
        .orekabu-text-muted {{ color: var(--orekabu-muted); }}
        .orekabu-market-metric {{
          min-height: 5rem;
          padding: 0.65rem 0;
        }}
        .orekabu-market-label {{
          color: var(--orekabu-muted);
          font-size: 0.875rem;
          line-height: 1.25;
        }}
        .orekabu-market-value {{
          margin-top: 0.2rem;
          font-size: 1.75rem;
          font-weight: 650;
          line-height: 1.2;
        }}
        .orekabu-market-inline {{
          display: block;
          margin: 0.2rem 0;
        }}
        .orekabu-empty {{
          padding: {padding};
          border: 1px dashed rgba(128, 128, 128, 0.45);
          border-radius: 6px;
          color: var(--orekabu-muted);
          background: var(--orekabu-surface);
        }}
        [data-testid="stMetricDelta"] {{
          font-weight: 700;
        }}
        [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) {{
          color: var(--orekabu-positive);
        }}
        [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) {{
          color: var(--orekabu-negative);
        }}
        [data-testid="stVerticalBlockBorderWrapper"] > div {{
          padding-top: {padding};
          padding-bottom: {padding};
        }}
        [data-testid="stMain"] button {{
          min-height: 2.75rem;
          white-space: normal;
        }}
        @media (max-width: 640px) {{
          [data-testid="stHorizontalBlock"] {{ gap: 0.5rem; }}
          .stButton button, .stLinkButton a {{ min-height: 2.75rem; width: 100%; white-space: normal; }}
          [data-testid="stMetric"] {{ min-width: 0; }}
          [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {{ overflow-wrap: anywhere; }}
          .orekabu-market-value {{ font-size: 1.45rem; }}
          [data-testid="stDataFrame"] {{ max-width: 100%; overflow-x: auto; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
