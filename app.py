"""Điểm vào Streamlit và điều hướng dùng chung."""
import streamlit as st

import ui_theme as ui

st.set_page_config(page_title="AI Architect Studio", page_icon=":material/architecture:",
                   layout="wide", initial_sidebar_state="auto")

pages = [
    st.Page("views/projects.py", title="Dự án", icon=":material/folder_open:", url_path="Du_an", default=True),
    st.Page("views/studio.py", title="Studio AI", icon=":material/layers:", url_path="Quan_ly_agent"),
    st.Page("views/agent_manager.py", title="Quản lý agent", icon=":material/smart_toy:", url_path="Agent"),
    st.Page("views/tasks.py", title="Công việc & Hiệu suất", icon=":material/bar_chart:", url_path="Cong_viec"),
    st.Page("views/results.py", title="Kết quả", icon=":material/image:", url_path="Ket_qua"),
    st.Page("views/settings.py", title="Cấu hình", icon=":material/tune:", url_path="Cau_hinh"),
]
legacy_project = st.Page("views/home.py", title="Dự án", url_path="Thiet_ke")
selected = st.navigation([*pages, legacy_project], position="hidden")
ui.inject()
with st.sidebar:
    ui.brand()
    for page in pages:
        nav_key = "nav_active" if page.url_path == selected.url_path else f"nav_{page.url_path}"
        with st.container(key=nav_key):
            st.page_link(page, width="stretch")
    with st.container(key="sidebar_art"):
        ui.html_block(ui.house_art())
selected.run()
