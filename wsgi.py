from app import app

app.config.update(
    SESSION_COOKIE_NAME='__Host-arus_session',
    SESSION_COOKIE_PATH='/',
    SESSION_COOKIE_DOMAIN=None,
    SESSION_COOKIE_SECURE=True,
)
