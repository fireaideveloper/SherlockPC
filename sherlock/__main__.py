from pathlib import Path

from sherlock import __version__
from sherlock.storage.sqlite import Database


def main() -> None:
    project_root = Path.cwd()

    database_path = (
        project_root
        / "data"
        / "sherlock.db"
    )

    database = Database(database_path)

    database.initialize()

    schema_version = database.get_schema_version()

    print()
    print("SHERLOCKPC")
    print("────────────────────────")
    print(f"Version          {__version__}")
    print(f"Database         {database_path}")
    print(f"Schema version   {schema_version}")
    print("Status           READY")
    print()


if __name__ == "__main__":
    main()
