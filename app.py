"""Router / entry point for the Fixed-wing UAV explorer — LIMITED EDITION.

v1.0.0-limited (2026): Public release for student / academic use.
- Only 3 tabs: Dataset Overview, Compare Two Filters, Design-Space Explorer
- Half-dataset (stratified sample, 710 of 1,344 rows)
- Data download / row tables removed from all pages
- Licensed AGPL-3.0 (code) + CC BY-NC 4.0 (data)
- Copyright © 2026 Moatasem B Momtaz

For full version + commercial inquiries see CITATION.cff in repo root.
"""
import streamlit as st

st.set_page_config(
    page_title="Fixed-wing UAV Explorer (Limited Edition)",
    page_icon="✈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Only 3 pages in the limited edition.
pages = [
    st.Page("pages/1_Dataset_Overview.py",
            title="Dataset Overview",
            icon="📊", default=True),
    st.Page("pages/3_Compare_filters.py",
            title="Compare Two Filters",
            icon="⚖️"),
    st.Page("pages/6_Design_space.py",
            title="Design-Space Explorer",
            icon="📈"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
