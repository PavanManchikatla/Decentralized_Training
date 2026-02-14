import sqlite3
from pathlib import Path


def _sqlite_path_from_url(db_url: str) -> Path:
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        raise ValueError("Only sqlite:/// URLs are supported")

    raw_path = db_url.removeprefix(prefix)
    if raw_path == ":memory:":
        raise ValueError("In-memory databases are not supported for migrations")

    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    return path


def apply_migrations(db_url: str) -> None:
    db_path = _sqlite_path_from_url(db_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    migrations_dir = Path(__file__).resolve().parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        applied_versions = {
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        }

        for migration_file in migration_files:
            version = migration_file.stem
            if version in applied_versions:
                continue

            sql = migration_file.read_text(encoding="utf-8")
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (version,),
            )

        connection.commit()
