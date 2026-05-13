from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import settings


def mysql_url_from_env(db_url: str, username: str, password: str) -> str:
    if db_url.startswith("jdbc:"):
        db_url = db_url[5:]

    parsed = urlparse(db_url)
    if parsed.scheme != "mysql":
        raise ValueError(f"Unsupported DB scheme: {parsed.scheme}")

    host = parsed.hostname
    port = parsed.port or 3306
    db_name = parsed.path.lstrip("/")
    if not host or not db_name:
        raise ValueError(f"Invalid DB URL: {db_url}")

    raw_qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    mapped_qs: dict[str, str] = {}

    if "useSSL" in raw_qs:
        use_ssl = raw_qs["useSSL"].lower() == "true"
        mapped_qs["ssl_disabled"] = str(not use_ssl).lower()

    mapped_qs.setdefault("charset", "utf8mb4")
    mapped_qs.setdefault("connect_timeout", "10")

    safe_user = quote_plus(username)
    safe_pass = quote_plus(password)
    query = urlencode(mapped_qs)
    return f"mysql+pymysql://{safe_user}:{safe_pass}@{host}:{port}/{db_name}?{query}"


def build_engine() -> Engine:
    url = mysql_url_from_env(settings.db_url, settings.db_username, settings.db_password)
    return create_engine(url, pool_pre_ping=True)


engine = build_engine()
