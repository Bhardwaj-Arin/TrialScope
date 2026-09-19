"""
db.py -- single place the project opens a database connection.

Why a raw psycopg2 connection instead of an ORM: the build constraints for
this project explicitly rule out ORMs (SQLAlchemy models / Django ORM)
because the point of the project is that every query is hand-written,
visible SQL that can be read and defended line-by-line in an interview. This
module (and SQLAlchemy Core's `text()`, used only as a thin execution
convenience in a couple of places) never builds queries programmatically --
it only ever runs the exact text of the .sql files in sql/.

Connection settings are read from environment variables so the same code
works against the local synthetic database generated for this offline build
and, unchanged, against a real AACT restore -- see README "Switching to the
real AACT database".
"""

import os

import psycopg2

DB_CONFIG = {
    "host": os.environ.get("TRIALSCOPE_DB_HOST", "localhost"),
    "port": os.environ.get("TRIALSCOPE_DB_PORT", "5432"),
    "dbname": os.environ.get("TRIALSCOPE_DB_NAME", "aact"),
    "user": os.environ.get("TRIALSCOPE_DB_USER", "trialscope"),
    "password": os.environ.get("TRIALSCOPE_DB_PASSWORD", "trialscope"),
}


def get_connection():
    """Return a new raw psycopg2 connection using DB_CONFIG."""
    return psycopg2.connect(**DB_CONFIG)


def run_sql_file(path: str, params: dict | None = None):
    """
    Execute a standalone .sql file and return the results as a pandas
    DataFrame. Kept intentionally dumb: it reads the file text and hands it
    to psycopg2 as-is, so the .sql file (not this function) is the source of
    truth for the query logic -- required by the "save every extraction
    query as a standalone .sql file" constraint.
    """
    import pandas as pd

    with open(path, "r") as f:
        query = f.read()

    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()
    return df
