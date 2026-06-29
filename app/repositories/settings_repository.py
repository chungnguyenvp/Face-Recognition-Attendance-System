def get_settings_map(db) -> dict[str, str]:
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def upsert_settings(db, values: dict[str, str]) -> None:
    for key, value in values.items():
        db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
