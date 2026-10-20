import logging
import secrets
import time
from urllib.parse import quote_plus, urlencode

import streamlit as st

from authlib.integrations.requests_client import OAuth2Session

from config import AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, AUTH0_DOMAIN, APP_ENV, AUTH_DISABLED, APP_BASE_URL

logger = logging.getLogger(__name__)

AUTH0_SCOPE = "openid profile email"

# In-memory store for pending OAuth states. Keyed by state value.
# NOTE: this is process-local. It works for a single-replica deployment.
# If you ever scale to multiple pods/replicas behind a load balancer without
# sticky sessions, replace this with a shared store (e.g. Redis).
_PENDING_STATES: dict[str, float] = {}
_STATE_TTL_SECONDS = 300  # 5 minutes


def _remember_state(state: str) -> None:
    _cleanup_expired_states()
    _PENDING_STATES[state] = time.time()


def _consume_state(state: str | None) -> bool:
    """Return True if state was pending and valid, removing it either way."""
    _cleanup_expired_states()
    if not state:
        return False
    issued_at = _PENDING_STATES.pop(state, None)
    return issued_at is not None


def _cleanup_expired_states() -> None:
    now = time.time()
    expired = [
        state
        for state, issued_at in _PENDING_STATES.items()
        if now - issued_at > _STATE_TTL_SECONDS
    ]
    for state in expired:
        _PENDING_STATES.pop(state, None)


def get_application_url() -> str:
    """Return the public URL used for the Auth0 callback.

    APP_BASE_URL should normally be injected by Helm, for example:

        https://coat-coh-dashboard-dev.cloud-platform.service.justice.gov.uk

    When APP_BASE_URL is not set, the URL is derived from forwarded headers.
    """
    configured_url = APP_BASE_URL
    if configured_url:
        return configured_url.rstrip("/")

    try:
        headers = st.context.headers
        forwarded_host = headers.get("X-Forwarded-Host") or headers.get("Host")

        if APP_ENV == "local":
            forwarded_proto = headers.get("X-Forwarded-Proto", "http")
        else:
            forwarded_proto = headers.get("X-Forwarded-Proto", "https")

        if forwarded_host:
            return f"{forwarded_proto.split(',')[0].strip()}://{forwarded_host}"
    except Exception:
        logger.exception("Unable to determine the application URL")

    # This fallback is useful for local development only.
    return "http://localhost:8501"


def get_auth0_redirect_uri() -> str:
    return f"{get_application_url()}/"


def validate_auth0_configuration() -> None:
    missing = [
        name
        for name, value in {
            "AUTH0_CLIENT_ID": AUTH0_CLIENT_ID,
            "AUTH0_CLIENT_SECRET": AUTH0_CLIENT_SECRET,
            "AUTH0_DOMAIN": AUTH0_DOMAIN,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing required Auth0 configuration: " + ", ".join(missing)
        )


def create_auth0_session(state=None) -> OAuth2Session:
    return OAuth2Session(
        client_id=AUTH0_CLIENT_ID,
        client_secret=AUTH0_CLIENT_SECRET,
        scope=AUTH0_SCOPE,
        redirect_uri=get_auth0_redirect_uri(),
        state=state,
    )


def create_auth0_login_url() -> str:
    validate_auth0_configuration()

    oauth = create_auth0_session()

    authorization_url, state = oauth.create_authorization_url(
        f"https://{AUTH0_DOMAIN}/authorize",
        nonce=secrets.token_urlsafe(32),
    )

    # Store pending state server-side (survives the redirect round trip),
    # not in st.session_state.
    _remember_state(state)

    return authorization_url


def exchange_auth0_code(code: str, returned_state: str | None) -> None:
    """Exchange the authorization code and load the authenticated user."""
    if not _consume_state(returned_state):
        raise ValueError("Missing or invalid Auth0 OAuth state")

    oauth = create_auth0_session(state=returned_state)

    token = oauth.fetch_token(
        f"https://{AUTH0_DOMAIN}/oauth/token",
        code=code,
        grant_type="authorization_code",
        redirect_uri=get_auth0_redirect_uri(),
    )

    userinfo_response = oauth.get(f"https://{AUTH0_DOMAIN}/userinfo")
    userinfo_response.raise_for_status()

    st.session_state["auth0_user"] = userinfo_response.json()
    st.session_state["auth0_token"] = token


def process_auth0_callback() -> None:
    code = st.query_params.get("code")
    returned_state = st.query_params.get("state")
    error = st.query_params.get("error")

    if error:
        error_description = st.query_params.get(
            "error_description",
            "Auth0 authentication failed.",
        )
        st.query_params.clear()
        raise RuntimeError(f"{error}: {error_description}")

    if not code:
        return

    try:
        exchange_auth0_code(code, returned_state)
    except Exception:
        logger.exception("Auth0 callback failed")
        st.query_params.clear()
        raise RuntimeError("Unable to complete Auth0 login.") from None

    st.query_params.clear()


def get_auth0_logout_url() -> str:
    validate_auth0_configuration()

    query_parameters = urlencode(
        {
            "client_id": AUTH0_CLIENT_ID,
            "returnTo": get_application_url(),
        },
        quote_via=quote_plus,
    )

    return f"https://{AUTH0_DOMAIN}/v2/logout?{query_parameters}"


def require_auth0_login() -> None:
    if AUTH_DISABLED:
        return

    validate_auth0_configuration()
    process_auth0_callback()

    if "auth0_user" not in st.session_state:
        st.title("AWS Cost Optimization Hub Dashboard")
        st.info("Please log in to continue.")
        st.link_button(
            "Log in with Auth0",
            create_auth0_login_url(),
            type="primary",
        )
        st.stop()

    userinfo = st.session_state["auth0_user"]

    with st.sidebar:
        display_name = (
            userinfo.get("name")
            or userinfo.get("email")
            or userinfo.get("nickname")
            or "Authenticated user"
        )

        st.caption(f"Signed in as **{display_name}**")
        st.link_button("Log out", get_auth0_logout_url())

        if st.button("Clear local session", key="clear_auth0_session"):
            st.session_state.pop("auth0_user", None)
            st.session_state.pop("auth0_token", None)
            st.rerun()