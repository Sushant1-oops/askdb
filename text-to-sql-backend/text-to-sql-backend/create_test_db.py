import sqlite3
import os

db_path = 'test_database.sqlite'

# Remove if it already exists to start fresh
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create Users table
cursor.execute('''
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    join_date DATE NOT NULL
)
''')

# Create Products table
cursor.execute('''
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
)
''')

# Create Orders table
cursor.execute('''
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_id INTEGER,
    quantity INTEGER NOT NULL,
    order_date DATE NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
)
''')

# Insert sample Users
cursor.executemany('''
INSERT INTO users (name, email, join_date) VALUES (?, ?, ?)
''', [
    ('Alice Smith', 'alice@example.com', '2023-01-15'),
    ('Bob Jones', 'bob@example.com', '2023-02-20'),
    ('Charlie Brown', 'charlie@example.com', '2023-03-10'),
    ('Diana Prince', 'diana@example.com', '2023-04-05')
])

# Insert sample Products
cursor.executemany('''
INSERT INTO products (name, category, price) VALUES (?, ?, ?)
''', [
    ('Laptop', 'Electronics', 999.99),
    ('Smartphone', 'Electronics', 699.50),
    ('Desk Chair', 'Furniture', 149.00),
    ('Coffee Mug', 'Kitchen', 12.99),
    ('Headphones', 'Electronics', 199.99)
])

# Insert sample Orders
cursor.executemany('''
INSERT INTO orders (user_id, product_id, quantity, order_date) VALUES (?, ?, ?, ?)
''', [
    (1, 1, 1, '2023-05-01'),
    (1, 5, 2, '2023-05-02'),
    (2, 3, 1, '2023-05-05'),
    (3, 2, 1, '2023-05-10'),
    (4, 4, 4, '2023-05-12'),
    (2, 4, 1, '2023-05-15')
])

conn.commit()
conn.close()

print(f"Successfully created sample database at: {os.path.abspath(db_path)}")
