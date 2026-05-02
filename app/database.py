import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import os
from datetime import datetime

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "vertibis"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

@contextmanager
def get_db_cursor(conn=None):
    """Context manager for database cursors"""
    if conn is None:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()
    else:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
        finally:
            cursor.close()

def init_db():
    """Initialize database schema"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Read and execute schema
            schema_path = os.path.join(os.path.dirname(__file__), "database", "schema.sql")
            with open(schema_path, "r") as f:
                cursor.execute(f.read())
            print("✅ Database schema initialized")

def execute_query(query: str, params: tuple = None):
    """Execute a query and return results"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchall()

def execute_single(query: str, params: tuple = None):
    """Execute a query and return single result"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchone()

def execute_insert(query: str, params: tuple = None):
    """Execute an insert and return the inserted row"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params or ())
        return cursor.fetchone()
