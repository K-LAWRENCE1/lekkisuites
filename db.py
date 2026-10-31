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


class _Row(dict):
    """A result row that behaves like sqlite3.Row.

    sqlite3.Row can be read both by name (row['ticket_id']) and by position
    (row[0]). Postgres hands back a plain dict, where row[0] raises KeyError.
    This class keeps the dict lookups but also answers integer indexes, so the
    same code works on both databases.
    """

    def __getitem__(self, key):
        if isinstance(key, int):
            try:
                return list(self.values())[key]
            except IndexError:
                raise IndexError("row index out of range")
        return dict.__getitem__(self, key)


class _PGCursor:
    """Wraps a psycopg2 cursor so the rest of the app can stay unchanged."""

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchall(self):
        return [_Row(row) for row in self._cursor.fetchall()]

    def fetchone(self):
        row = self._cursor.fetchone()
        return _Row(row) if row is not None else None

    def __iter__(self):
        return iter(self.fetchall())


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

        # fix65: SQLite's "INSERT OR IGNORE" has no Postgres spelling. Postgres uses
        # "ON CONFLICT DO NOTHING" instead. The rooms seed in init_db needs this.
        if "INSERT OR IGNORE" in upper:
            sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql,
                         flags=re.IGNORECASE)
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        return sql.replace("?", "%s")

    def execute(self, sql, params=()):
        statement = self._translate(sql)
        raw = sql.strip().upper()
        cursor = self._conn.cursor()

        # The app asks for cur.lastrowid after inserts; Postgres needs RETURNING id.
        # A "DO NOTHING" insert returns no row, and the rooms table has no id column,
        # so those inserts must go through untouched.
        if (raw.startswith("INSERT")
                and "RETURNING" not in statement.upper()
                and "ON CONFLICT" not in statement.upper()):
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
