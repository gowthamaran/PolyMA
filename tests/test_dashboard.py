from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from dashboard.server import create_app


def test_dashboard_is_paper_only_and_does_not_expose_secrets(tmp_path) -> None:
    database = Database(tmp_path / "dashboard.db")
    database.initialize()
    settings = Settings(
        database_path=tmp_path / "dashboard.db",
        telegram_enabled=True,
        telegram_bot_token="super-secret-token",
        telegram_chat_id="secret-chat",
    )
    database.ensure_account(settings.starting_balance)
    client = TestClient(create_app(settings, database))
    overview = client.get("/api/overview")
    assert overview.status_code == 200
    assert overview.json()["paper_only"] is True
    public = client.get("/api/settings")
    assert public.status_code == 200
    body = public.text
    assert "super-secret-token" not in body
    assert "secret-chat" not in body
    assert public.json()["live_trading"] is False

