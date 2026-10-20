"""Tiny SQLite store for local order records."""
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    paypal_order_id TEXT PRIMARY KEY,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'CREATED',
    payer_email TEXT,
    raw_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    segments_json TEXT,
    products_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        self.path = path
        # check_same_thread=False: FastAPI serves requests in a threadpool.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_order(
        self,
        paypal_order_id: str,
        amount: str,
        currency: str = "USD",
        description: str | None = None,
        status: str = "CREATED",
        raw: dict | None = None,
    ) -> dict:
        now = time.time()
        self.conn.execute(
            """
            INSERT INTO orders
                (paypal_order_id, amount, currency, description, status,
                 raw_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paypal_order_id) DO UPDATE SET
                status=excluded.status,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            (
                paypal_order_id,
                amount,
                currency,
                description,
                status,
                json.dumps(raw or {}),
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get_order(paypal_order_id)

    def list_orders(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- jobs (M2 video pipeline) ----------------------------------------
    def create_job(self, job_id: str, filename: str, stored_path: str) -> dict:
        now = time.time()
        self.conn.execute(
            "INSERT INTO jobs (id, filename, stored_path, status, created_at,"
            " updated_at) VALUES (?, ?, ?, 'uploaded', ?, ?)",
            (job_id, filename, stored_path, now, now),
        )
        self.conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["segments"] = json.loads(job.pop("segments_json") or "[]")
        job["products"] = json.loads(job.pop("products_json") or "[]")
        return job

    def update_job(
        self,
        job_id: str,
        status: str | None = None,
        error: str | None = None,
        segments: list | None = None,
        products: list | None = None,
    ) -> dict | None:
        sets = ["updated_at = ?"]
        params: list = [time.time()]
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if segments is not None:
            sets.append("segments_json = ?")
            params.append(json.dumps(segments))
        if products is not None:
            sets.append("products_json = ?")
            params.append(json.dumps(products))
        params.append(job_id)
        self.conn.execute(
            f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_job(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self.get_job(row["id"]) for row in rows]

    def get_order(self, paypal_order_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM orders WHERE paypal_order_id = ?",
            (paypal_order_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_status(
        self,
        paypal_order_id: str,
        status: str,
        payer_email: str | None = None,
        raw: dict | None = None,
    ) -> dict | None:
        now = time.time()
        if payer_email is not None:
            self.conn.execute(
                "UPDATE orders SET status=?, payer_email=?, raw_json=?, updated_at=? "
                "WHERE paypal_order_id=?",
                (status, payer_email, json.dumps(raw or {}), now, paypal_order_id),
            )
        else:
            self.conn.execute(
                "UPDATE orders SET status=?, raw_json=?, updated_at=? "
                "WHERE paypal_order_id=?",
                (status, json.dumps(raw or {}), now, paypal_order_id),
            )
        self.conn.commit()
        return self.get_order(paypal_order_id)
