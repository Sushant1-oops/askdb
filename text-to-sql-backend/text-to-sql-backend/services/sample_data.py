"""Deterministic demo database (e-commerce) for one-click "Try the demo".

Dates are generated relative to *today* so questions like "last month" return
data. ``customers.password_hash`` exists on purpose: it demonstrates the
restricted-column guardrail (hidden from the LLM, blocked in SQL, masked in results).
"""

from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta
from typing import List, Tuple

FIRST = ["Ava", "Liam", "Noah", "Emma", "Olivia", "Ethan", "Mia", "Lucas", "Sofia", "Aarav", "Priya", "Kenji",
         "Zoe", "Omar", "Chloe", "Diego", "Hana", "Ivan", "Nora", "Ravi"]
LAST = ["Smith", "Johnson", "Patel", "Garcia", "Kim", "Nguyen", "Brown", "Singh", "Lopez", "Tanaka",
        "Miller", "Khan", "Davis", "Silva", "Cohen"]
CITIES: List[Tuple[str, str]] = [("New York", "USA"), ("Austin", "USA"), ("Toronto", "Canada"), ("London", "UK"),
                                 ("Berlin", "Germany"), ("Mumbai", "India"), ("Sydney", "Australia"), ("Paris", "France")]
PRODUCTS: List[Tuple[str, str, float]] = [
    ("Laptop Pro 15", "Electronics", 1299.99), ("Wireless Mouse", "Electronics", 29.99),
    ("Mechanical Keyboard", "Electronics", 89.99), ("Monitor 27in", "Electronics", 349.99),
    ("Noise-Cancelling Headphones", "Electronics", 199.99), ("Webcam HD", "Electronics", 69.99),
    ("USB-C Cable", "Accessories", 12.99), ("Laptop Bag", "Accessories", 59.99), ("Phone Stand", "Accessories", 19.99),
    ("Desk Lamp", "Office", 45.99), ("Coffee Mug", "Office", 9.99), ("Desk Organizer", "Office", 24.99),
    ("Office Chair", "Furniture", 299.99), ("Standing Desk", "Furniture", 549.00), ("Bookshelf", "Furniture", 129.00),
    ("Notebook Set", "Stationery", 15.99), ("Pen Set", "Stationery", 12.99), ("Sticky Notes", "Stationery", 6.49),
]
STATUSES = ["Completed"] * 6 + ["Shipped"] * 2 + ["Pending"] + ["Cancelled"]

SCHEMA = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    city TEXT,
    country TEXT,
    password_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock_quantity INTEGER NOT NULL
);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total_amount REAL NOT NULL DEFAULT 0
);
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
"""


def create_sample_db(path: str, *, today: date | None = None, seed: int = 42) -> str:
    """(Re)create the demo database at ``path`` and return the absolute path."""
    rng = random.Random(seed)
    today = today or date.today()
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)

    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        customers = []
        for i in range(60):
            first, last = FIRST[i % len(FIRST)], LAST[(i * 7) % len(LAST)]
            city, country = CITIES[i % len(CITIES)]
            joined = today - timedelta(days=rng.randint(60, 700))
            customers.append((first, last, f"{first.lower()}.{last.lower()}{i}@example.com", city, country,
                              f"$2b$12${rng.getrandbits(96):024x}", joined.isoformat()))
        conn.executemany(
            "INSERT INTO customers (first_name,last_name,email,city,country,password_hash,created_at) VALUES (?,?,?,?,?,?,?)",
            customers)
        conn.executemany("INSERT INTO products (product_name,category,price,stock_quantity) VALUES (?,?,?,?)",
                         [(n, c, p, rng.randint(10, 400)) for n, c, p in PRODUCTS])

        for _ in range(320):
            customer_id = min(60, max(1, int(rng.expovariate(1 / 18)) + 1))  
            order_date = today - timedelta(days=rng.randint(0, 364))
            status = rng.choice(STATUSES)
            cur = conn.execute("INSERT INTO orders (customer_id,order_date,status,total_amount) VALUES (?,?,?,0)",
                               (customer_id, order_date.isoformat(), status))
            order_id, total = cur.lastrowid, 0.0
            for product_id in rng.sample(range(1, len(PRODUCTS) + 1), rng.randint(1, 4)):
                qty = rng.randint(1, 3)
                price = PRODUCTS[product_id - 1][2]
                total += qty * price
                conn.execute("INSERT INTO order_items (order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)",
                             (order_id, product_id, qty, price))
            conn.execute("UPDATE orders SET total_amount=? WHERE order_id=?", (round(total, 2), order_id))
        conn.commit()
    finally:
        conn.close()
    return path


if __name__ == "__main__":  
    print(create_sample_db("data/demo_ecommerce.db"))
