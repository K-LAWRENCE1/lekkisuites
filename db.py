# Database layer for Lekki Suites.
#
# Locally (and on a laptop) this keeps using the simple bookings.db SQLite file.
# On Render, set an environment variable called DATABASE_URL and it switches to
# Postgres automatically, so bookings survive restarts and redeploys.

import os
import re
import sqlite3

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
DB_NAME = "bookings.db"


def _clean_url(url):
    # Render sometimes hands out "postgres://"; psycopg2 wants "postgresql://".
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class _PGCursor:
    """Wraps a psycopg2 cursor so the rest of the app can stay unchanged."""

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    def __iter__(self):
        return iter(self._cursor.fetchall())


class _PGConnection:
    def __init__(self, url):
        import psycopg2
        import psycopg2.extras

        self._conn = psycopg2.connect(
            _clean_url(url), cursor_factory=psycopg2.extras.RealDictCursor
        )

    # --- SQL translation: SQLite habits -> Postgres ---
    @staticmethod
    def _translate(sql):
        upper = sql.upper()

        if "AUTOINCREMENT" in upper:
            sql = re.sub(
                r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
                "SERIAL PRIMARY KEY",
                sql,
                flags=re.IGNORECASE,
            )

        if upper.lstrip().startswith("PRAGMA TABLE_INFO"):
            table = sql.split("(")[1].split(")")[0].strip().strip("'\"")
            sql = (
                "SELECT ordinal_position AS cid, column_name AS name, "
                "data_type AS type, 0 AS notnull, '' AS dflt_value, 0 AS pk "
                "FROM information_schema.columns WHERE table_name = '{}' "
                "ORDER BY ordinal_position"
            ).format(table)

        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        statement = self._translate(sql)
        raw = sql.strip().upper()
        cursor = self._conn.cursor()

        # The app asks for cur.lastrowid after inserts; Postgres needs RETURNING id.
        if raw.startswith("INSERT") and "RETURNING" not in statement.upper():
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
            cursor.execute(statement, params)
            row = cursor.fetchone()
            new_id = row["id"] if row else None
            return _PGCursor(cursor, new_id)

        cursor.execute(statement, params)
        return _PGCursor(cursor, None)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    """Return a database connection: Postgres if DATABASE_URL is set, else SQLite."""
    if DATABASE_URL:
        return _PGConnection(DATABASE_URL)

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn
