"""
login.py
Renders the login form and stores the token + user info in session_state
on success. Nothing downstream should read a raw password — only the
token and user role/org_id ever get stored.
"""

import streamlit as st
from api_client import login


def render_login():
    st.title("AI Project OS — Login")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        if not email or not password:
            st.error("Please enter both email and password.")
            return

        data, error = login(email, password)

        if error:
            st.error(f"Login failed: {error}")
        else:
            st.session_state["access_token"] = data["access_token"]
            st.session_state["user"] = data["user"]
            st.rerun()