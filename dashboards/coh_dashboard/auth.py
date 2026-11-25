import time

import streamlit as st

from config import APP_ENV, AUTH_DISABLED, DASHBOARD_NAME
from render_html import render_footer


def require_entra_login() -> None:
    if AUTH_DISABLED:
        if APP_ENV != "local":
            raise RuntimeError(
                "AUTH_DISABLED is only permitted when APP_ENV=local."
            )
        return

    if not st.user.is_logged_in:
        st.title(DASHBOARD_NAME)
        st.info("Please sign in with your MoJ account to continue.")

        if st.button(
            "Sign in with Microsoft",
            type="primary",
            key="entra_login",
        ):
            st.login("microsoft")

        render_footer()
        st.stop()

    # Streamlit's identity cookie can outlive the Entra ID token.
    if st.user["exp"] <= time.time():
        st.logout()
        st.stop()

    display_name = (
        st.user.get("name")
        or st.user.get("preferred_username")
        or st.user.get("email")
        or "Authenticated user"
    )

    with st.sidebar:
        st.caption(f"Signed in as **{display_name}**")

        if st.button("Log out", key="entra_logout"):
            st.logout()
            st.stop()
