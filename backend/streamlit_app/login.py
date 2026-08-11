"""
login.py
Real login screen — calls POST /auth/login and stores the JWT + user info
in st.session_state, which every other page then reads to know who's
logged in and what role they have.
"""

import streamlit as st
from api_client import login


def render_login():
    st.set_page_config(
        page_title="Affordable AI — Sign In",
        page_icon="🔺",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    # ------------------------------------------------------------------
    # Styling — dark purple background, glass card, gradient accents
    # ------------------------------------------------------------------
    st.markdown(
        """
        <style>
            /* display:none removes the element AND its reserved space.
               visibility:hidden was leaving a blank bordered box at the
               top because the header's height/border were still there. */
            #MainMenu, header, footer { display: none !important; }

            html, body, [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at 15% 20%, rgba(124, 58, 237, 0.22), transparent 40%),
                    radial-gradient(circle at 85% 80%, rgba(124, 58, 237, 0.20), transparent 40%),
                    #0a0713;
            }

            [data-testid="stAppViewContainer"] > .main {
                display: flex;
                justify-content: center;
            }

            /* Reduced top padding since the header is now fully gone,
               not just hidden-with-space */
            .block-container {
                max-width: 620px;
                padding-top: 2rem;
            }

            .login-card {
                background: rgba(20, 14, 32, 0.75);
                border: 1px solid rgba(139, 92, 246, 0.25);
                border-radius: 20px;
                padding: 44px 48px 30px 48px;
                box-shadow: 0 0 60px rgba(124, 58, 237, 0.15);
                backdrop-filter: blur(10px);
                margin-bottom: 24px;
            }

            .logo-wrap {
                display: flex;
                justify-content: center;
                margin-bottom: 6px;
            }

            .logo-circle {
                width: 74px;
                height: 74px;
                border-radius: 50%;
                background: linear-gradient(135deg, #8b5cf6, #6d28d9);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 34px;
                font-weight: 800;
                color: white;
                box-shadow: 0 0 30px rgba(139, 92, 246, 0.55);
            }

            .brand-name {
                text-align: center;
                letter-spacing: 6px;
                font-weight: 700;
                font-size: 22px;
                color: #f5f3ff;
                margin-top: 14px;
            }

            .brand-sub {
                text-align: center;
                color: #a1a1aa;
                font-size: 14px;
                margin-top: 2px;
                margin-bottom: 22px;
            }

            .welcome-title {
                text-align: center;
                color: white;
                font-size: 26px;
                font-weight: 700;
                margin-bottom: 4px;
            }

            .welcome-sub {
                text-align: center;
                color: #9ca3af;
                font-size: 14px;
                margin-bottom: 26px;
            }

            .field-label {
                color: #e5e7eb;
                font-size: 13px;
                font-weight: 600;
                margin-bottom: 6px;
            }

            /* Text input — dark background, light text. Multiple selector
               paths used because Streamlit's base theme (config.toml) can
               inject its own input styling after this block; hitting the
               same element through several selectors + !important ensures
               ours wins regardless of source order or Streamlit version. */
            div[data-testid="stTextInput"] input,
            div[data-testid="stTextInput"] div[data-baseweb="input"] input,
            div[data-testid="stTextInput"] input[type="text"],
            div[data-testid="stTextInput"] input[type="password"] {
                background: #1e1430 !important;
                background-color: #1e1430 !important;
                border: 1px solid rgba(139, 92, 246, 0.35) !important;
                border-radius: 10px !important;
                color: #f3f4f6 !important;
                -webkit-text-fill-color: #f3f4f6 !important;
                caret-color: #f3f4f6 !important;
                padding: 12px 14px !important;
            }
            div[data-testid="stTextInput"] input::placeholder {
                color: #9ca3af !important;
                -webkit-text-fill-color: #9ca3af !important;
                opacity: 1 !important;
            }
            div[data-testid="stTextInput"] div[data-baseweb="input"],
            div[data-testid="stTextInput"] div[data-baseweb="base-input"],
            div[data-testid="stTextInput"] > div {
                background: transparent !important;
                background-color: transparent !important;
            }
            /* Autofill / saved-password override (Chrome/Edge force their
               own white box + dark text via UA stylesheet on autofilled
               fields — this beats normal !important rules unless matched
               with :-webkit-autofill directly). */
            div[data-testid="stTextInput"] input:-webkit-autofill,
            div[data-testid="stTextInput"] input:-webkit-autofill:hover,
            div[data-testid="stTextInput"] input:-webkit-autofill:focus,
            div[data-testid="stTextInput"] input:-webkit-autofill:active {
                -webkit-text-fill-color: #f3f4f6 !important;
                caret-color: #f3f4f6 !important;
                box-shadow: 0 0 0px 1000px #1e1430 inset !important;
                -webkit-box-shadow: 0 0 0px 1000px #1e1430 inset !important;
                transition: background-color 5000s ease-in-out 0s;
            }
            /* Focus state — keep the dark background, don't let Streamlit's
               focus-ring styling swap it back to light. */
            div[data-testid="stTextInput"] input:focus {
                background: #1e1430 !important;
                background-color: #1e1430 !important;
                color: #f3f4f6 !important;
                -webkit-text-fill-color: #f3f4f6 !important;
                border-color: #8b5cf6 !important;
                box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.5) !important;
            }

            /* Checkbox — force the purple theme instead of the browser's
               default red accent color */
            div[data-testid="stCheckbox"] label p {
                color: #d4d4d8 !important;
                font-size: 14px !important;
            }
            div[data-testid="stCheckbox"] input[type="checkbox"] {
                accent-color: #8b5cf6 !important;
            }
            div[data-testid="stCheckbox"] svg {
                fill: #8b5cf6 !important;
            }
            div[data-testid="stCheckbox"] > label > div[data-testid="stMarkdownContainer"] {
                color: #d4d4d8 !important;
            }
            div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > div:first-child {
                background-color: transparent !important;
                border-color: #8b5cf6 !important;
            }
            div[data-testid="stCheckbox"] [aria-checked="true"] > div:first-child {
                background-color: #8b5cf6 !important;
                border-color: #8b5cf6 !important;
            }

            div[data-testid="stFormSubmitButton"] button {
                background: linear-gradient(90deg, #7c3aed, #a855f7) !important;
                border: none !important;
                border-radius: 10px !important;
                color: white !important;
                font-weight: 700 !important;
                padding: 12px 0 !important;
                font-size: 16px !important;
                box-shadow: 0 8px 24px rgba(124, 58, 237, 0.35);
                transition: transform 0.1s ease-in-out;
            }
            div[data-testid="stFormSubmitButton"] button:hover {
                transform: translateY(-1px);
                box-shadow: 0 10px 28px rgba(124, 58, 237, 0.5);
            }

            .secure-row {
                text-align: center;
                color: #8b8b96;
                font-size: 12px;
                margin-top: 18px;
                border-top: 1px solid rgba(139, 92, 246, 0.15);
                padding-top: 14px;
            }

            .footer-copy {
                text-align: center;
                color: #6b6b76;
                font-size: 12px;
                margin-top: 10px;
            }

            .forgot-link {
                text-align: right;
                font-size: 13px;
                color: #a78bfa;
                margin-top: -6px;
            }

            /* Force Streamlit's native alert boxes (error/success/info) to stay
               readable on this page's dark background — config.toml's light-theme
               textColor would otherwise make these messages invisible here. */
            div[data-testid="stAlert"] {
                background: rgba(255, 255, 255, 0.06) !important;
                border: 1px solid rgba(139, 92, 246, 0.3) !important;
                border-radius: 10px !important;
            }
            div[data-testid="stAlert"] * {
                color: #f3f4f6 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # Card header — logo, brand, welcome copy
    # ------------------------------------------------------------------
    st.markdown('<div class="login-card">', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="logo-wrap"><div class="logo-circle">ai</div></div>
        <div class="brand-name">AFFORDABLE AI</div>
        <div class="brand-sub">Enterprise Project OS</div>
        <div class="welcome-title">Welcome Back</div>
        <div class="welcome-sub">Sign in to continue to your workspace</div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # Login form — real logic, calls api_client.login()
    # ------------------------------------------------------------------
    with st.form("login_form"):
        st.markdown('<div class="field-label">📧 Email Address</div>', unsafe_allow_html=True)
        email = st.text_input("Email", placeholder="Enter your email", label_visibility="collapsed")

        st.markdown('<div class="field-label">🔒 Password</div>', unsafe_allow_html=True)
        password = st.text_input(
            "Password", type="password", placeholder="Enter your password", label_visibility="collapsed"
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            remember = st.checkbox("Remember me", value=True)
        with col2:
            st.markdown('<div class="forgot-link">Forgot Password?</div>', unsafe_allow_html=True)

        submitted = st.form_submit_button("Sign In", width="stretch")

        if submitted:
            data, error = login(email, password)
            if error:
                st.error(f"Login failed: {error}")
            else:
                st.session_state["access_token"] = data["access_token"]
                st.session_state["user"] = data["user"]
                st.session_state["remember_me"] = remember
                st.success(f"Welcome, {data['user']['name']} ({data['user']['role']})")
                st.rerun()

    st.markdown('<div class="secure-row">🛡️ Secure Access</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)  # close .login-card

    st.markdown('<div class="footer-copy">© 2025 Affordable AI. All rights reserved.</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Session status (dev helper)
    # ------------------------------------------------------------------
    if "user" in st.session_state:
        st.info(f"Logged in as {st.session_state['user']['email']} — role: {st.session_state['user']['role']}")