from sherlock.storage.sqlite import Database


def test_database_initialization(tmp_path):
    database_path = tmp_path / "test.db"

    database = Database(database_path)

    database.initialize()

    assert database_path.exists()

    assert database.get_schema_version() == 1
