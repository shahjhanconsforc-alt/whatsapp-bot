from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def _load_env_file(env_path: str | Path = ".env") -> None:
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _connect_postgres():
    _load_env_file(".env")

    host = os.getenv("PGHOST")
    port = os.getenv("PGPORT", "5432")
    dbname = os.getenv("PGDATABASE")
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")

    if not all([host, port, dbname, user, password]):
        raise RuntimeError("Missing PostgreSQL configuration in .env")

    # Try psycopg3 first, then psycopg2.
    try:
        import psycopg  # type: ignore

        conn = psycopg.connect(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
        return conn
    except ImportError:
        pass

    try:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
        return conn
    except ImportError as exc:
        raise RuntimeError(
            "No PostgreSQL driver found. Install `psycopg` or `psycopg2-binary`."
        ) from exc


def _normalize_group_metadata(group_name: str, metadata: dict | None = None) -> dict:
    metadata = dict(metadata or {})
    safe_group = (group_name or metadata.get("group_name") or "group").strip()
    return {
        "group_name": safe_group,
        "description": str(metadata.get("description") or "").strip(),
        "members_label": str(metadata.get("members_label") or "").strip(),
        "members_count": int(metadata.get("members_count") or 0) if str(metadata.get("members_count") or "").strip() else None,
        "created_by": str(metadata.get("created_by") or "").strip(),
        "created_on": str(metadata.get("created_on") or "").strip(),
        "invite_link": str(metadata.get("invite_link") or "").strip(),
        "source_scrap_id": str(metadata.get("source_scrap_id") or "").strip(),
        "last_scraped_at": str(metadata.get("last_scraped_at") or "").strip(),
    }


def _get_all_contacts_columns(cur) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'all_contacts'
        """
    )
    return {row[0] for row in cur.fetchall() if row and row[0]}


def ensure_all_contacts_table(cur) -> bool:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS all_contacts (
            "Phone" TEXT,
            "whatspp_group" TEXT,
            "time" TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute('ALTER TABLE all_contacts ADD COLUMN IF NOT EXISTS "Phone" TEXT')
    cur.execute('ALTER TABLE all_contacts ADD COLUMN IF NOT EXISTS "whatspp_group" TEXT')
    cur.execute('ALTER TABLE all_contacts ADD COLUMN IF NOT EXISTS "time" TIMESTAMPTZ NOT NULL DEFAULT NOW()')
    cur.execute('ALTER TABLE all_contacts ADD COLUMN IF NOT EXISTS "whatsapp_group" TEXT')

    existing_cols = _get_all_contacts_columns(cur)
    has_legacy_whatsapp_group = "whatsapp_group" in existing_cols

    if has_legacy_whatsapp_group:
        cur.execute(
            """
            UPDATE all_contacts
            SET "whatspp_group" = COALESCE(NULLIF(TRIM("whatspp_group"), ''), NULLIF(TRIM("whatsapp_group"), ''))
            WHERE COALESCE(NULLIF(TRIM("whatspp_group"), ''), '') = ''
              AND COALESCE(NULLIF(TRIM("whatsapp_group"), ''), '') <> ''
            """
        )
        cur.execute(
            """
            UPDATE all_contacts
            SET "whatsapp_group" = COALESCE(NULLIF(TRIM("whatsapp_group"), ''), NULLIF(TRIM("whatspp_group"), ''))
            WHERE COALESCE(NULLIF(TRIM("whatsapp_group"), ''), '') = ''
              AND COALESCE(NULLIF(TRIM("whatspp_group"), ''), '') <> ''
            """
        )

    cur.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = current_schema()
          AND tc.table_name = 'all_contacts'
          AND tc.constraint_type = 'UNIQUE'
        GROUP BY tc.constraint_name
        HAVING COUNT(*) = 1
           AND MIN(kcu.column_name) = 'Phone'
           AND MAX(kcu.column_name) = 'Phone'
        """
    )
    for row in cur.fetchall():
        constraint_name = str(row[0] or "").strip()
        if not constraint_name:
            continue
        cur.execute(f'ALTER TABLE all_contacts DROP CONSTRAINT IF EXISTS "{constraint_name}"')

    cur.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND tablename = 'all_contacts'
        """
    )
    for index_name, index_def in cur.fetchall():
        normalized_def = " ".join(str(index_def or "").split())
        if "CREATE UNIQUE INDEX" not in normalized_def.upper():
            continue
        if '("Phone")' not in normalized_def:
            continue
        if '("Phone", ' in normalized_def or ', "Phone")' in normalized_def:
            continue
        if str(index_name or "").strip() == "all_contacts_pkey":
            continue
        cur.execute(f'DROP INDEX IF EXISTS "{index_name}"')

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_all_contacts_phone_group
        ON all_contacts ("Phone", "whatspp_group")
        """
    )
    return has_legacy_whatsapp_group


def save_group_metadata_to_postgres(group_name: str, metadata: dict | None = None) -> str:
    table_name = "group_metadata"
    normalized = _normalize_group_metadata(group_name, metadata)

    conn = _connect_postgres()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS group_metadata (
                        group_name TEXT PRIMARY KEY,
                        description TEXT,
                        members_label TEXT,
                        members_count INTEGER,
                        created_by TEXT,
                        created_on TEXT,
                        invite_link TEXT,
                        source_scrap_id TEXT,
                        last_scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS description TEXT')
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS members_label TEXT')
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS members_count INTEGER')
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS created_by TEXT')
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS created_on TEXT')
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS invite_link TEXT')
                cur.execute('ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS source_scrap_id TEXT')
                cur.execute(
                    'ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS last_scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()'
                )
                cur.execute(
                    'ALTER TABLE group_metadata ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()'
                )
                cur.execute(
                    """
                    INSERT INTO group_metadata (
                        group_name,
                        description,
                        members_label,
                        members_count,
                        created_by,
                        created_on,
                        invite_link,
                        source_scrap_id,
                        last_scraped_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()), NOW())
                    ON CONFLICT (group_name)
                    DO UPDATE SET
                        description = EXCLUDED.description,
                        members_label = EXCLUDED.members_label,
                        members_count = EXCLUDED.members_count,
                        created_by = EXCLUDED.created_by,
                        created_on = EXCLUDED.created_on,
                        invite_link = EXCLUDED.invite_link,
                        source_scrap_id = EXCLUDED.source_scrap_id,
                        last_scraped_at = EXCLUDED.last_scraped_at,
                        updated_at = NOW()
                    """,
                    (
                        normalized["group_name"],
                        normalized["description"] or None,
                        normalized["members_label"] or None,
                        normalized["members_count"],
                        normalized["created_by"] or None,
                        normalized["created_on"] or None,
                        normalized["invite_link"] or None,
                        normalized["source_scrap_id"] or None,
                        normalized["last_scraped_at"] or datetime.now(timezone.utc).isoformat(),
                    ),
                )
    finally:
        conn.close()

    return table_name


def save_group_contacts_to_postgres(group_name: str, contacts: list[str], metadata: dict | None = None) -> str:
    """
    Save all scraped contacts into shared `all_contacts` table with columns:
    "Phone", "whatspp_group", "time"
    Returns used table name.
    """
    table_name = "all_contacts"
    unique_contacts = sorted(set((c or "").strip() for c in contacts if (c or "").strip()))
    normalized_metadata = _normalize_group_metadata(group_name, metadata)
    safe_group = normalized_metadata["group_name"]

    conn = _connect_postgres()
    try:
        with conn:
            with conn.cursor() as cur:
                has_legacy_whatsapp_group = ensure_all_contacts_table(cur)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS group_metadata (
                        group_name TEXT PRIMARY KEY,
                        description TEXT,
                        members_label TEXT,
                        members_count INTEGER,
                        created_by TEXT,
                        created_on TEXT,
                        invite_link TEXT,
                        source_scrap_id TEXT,
                        last_scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                for number in unique_contacts:
                    if has_legacy_whatsapp_group:
                        cur.execute(
                            """
                            INSERT INTO all_contacts ("Phone", "whatspp_group", "whatsapp_group", "time")
                            VALUES (%s, %s, %s, NOW())
                            ON CONFLICT ("Phone", "whatspp_group") DO NOTHING
                            """,
                            (number, safe_group, safe_group),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO all_contacts ("Phone", "whatspp_group", "time")
                            VALUES (%s, %s, NOW())
                            ON CONFLICT ("Phone", "whatspp_group") DO NOTHING
                            """,
                            (number, safe_group),
                        )
        save_group_metadata_to_postgres(safe_group, normalized_metadata)
    finally:
        conn.close()

    return table_name
