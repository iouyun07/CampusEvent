import sqlite3

import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "test.db"
    failure_log = tmp_path / "notification_failures.log"
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(database),
            "FAILURE_LOG": str(failure_log),
            "SEED_ACTIVITIES": False,
        }
    )
    application.config["TEST_FAILURE_LOG"] = str(failure_log)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def conn(app):
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()
