# db_setup.py
import sqlite3
import time

DB_NAME = 'jobs.db'
# Define the maximum number of seconds a job is allowed to be running
# If a job is RUNNING longer than this, it's considered STALE on startup.
STALE_JOB_TIMEOUT_SECONDS = 3600  # 1 hour


class DBManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization on repeated DBManager() calls
        if self.__class__._initialized:
            return

        self.__class__._initialized = True

        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks
            (
                inserted_at TEXT NOT NULL,
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                output TEXT NOT NULL DEFAULT '',
                output_length INTEGER NOT NULL DEFAULT 0,
                msg TEXT NOT NULL DEFAULT '',
                start_time REAL,
                end_time REAL
            )
        ''')
        conn.commit()
        conn.close()

    def get_db_connection(self):
        """Returns a new thread-safe database connection."""
        conn = sqlite3.connect(DB_NAME)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn