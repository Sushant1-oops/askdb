import sqlite3
import random
from datetime import datetime, timedelta

def create_sample_database():
    """Create a sample SQLite database for testing"""
    
    # Connect to database
    conn = sqlite3.connect('sample_ecommerce.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        city TEXT,
        country TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        stock_quantity INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS order_items (
        order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (order_id),
        FOREIGN KEY (product_id) REFERENCES products (product_id)
    )
    ''')
    
    # Sample data
    customers_data = [
        ('John', 'Doe', 'john.doe@email.com', '555-0101', 'New York', 'USA'),
        ('Jane', 'Smith', 'jane.smith@email.com', '555-0102', 'Los Angeles', 'USA'),
        ('Bob', 'Johnson', 'bob.j@email.com', '555-0103', 'Chicago', 'USA'),
        ('Alice', 'Williams', 'alice.w@email.com', '555-0104', 'Houston', 'USA'),
        ('Charlie', 'Brown', 'charlie.b@email.com', '555-0105', 'Phoenix', 'USA'),
        ('Diana', 'Davis', 'diana.d@email.com', '555-0106', 'Philadelphia', 'USA'),
        ('Eve', 'Miller', 'eve.m@email.com', '555-0107', 'San Antonio', 'USA'),
        ('Frank', 'Wilson', 'frank.w@email.com', '555-0108', 'San Diego', 'USA'),
        ('Grace', 'Moore', 'grace.m@email.com', '555-0109', 'Dallas', 'USA'),
        ('Henry', 'Taylor', 'henry.t@email.com', '555-0110', 'San Jose', 'USA'),
    ]
    
    cursor.executemany(
        'INSERT INTO customers (first_name, last_name, email, phone, city, country) VALUES (?, ?, ?, ?, ?, ?)',
        customers_data
    )
    
    products_data = [
        ('Laptop Pro 15', 'Electronics', 1299.99, 50),
        ('Wireless Mouse', 'Electronics', 29.99, 200),
        ('USB-C Cable', 'Accessories', 12.99, 500),
        ('Desk Lamp', 'Office', 45.99, 100),
        ('Office Chair', 'Furniture', 299.99, 30),
        ('Notebook Set', 'Stationery', 15.99, 300),
        ('Wireless Keyboard', 'Electronics', 79.99, 150),
        ('Monitor 27"', 'Electronics', 349.99, 75),
        ('Phone Stand', 'Accessories', 19.99, 250),
        ('Coffee Mug', 'Office', 9.99, 400),
        ('Pen Set', 'Stationery', 12.99, 350),
        ('Desk Organizer', 'Office', 24.99, 180),
        ('Laptop Bag', 'Accessories', 59.99, 120),
        ('Webcam HD', 'Electronics', 89.99, 90),
        ('Headphones', 'Electronics', 149.99, 110),
    ]
    
    cursor.executemany(
        'INSERT INTO products (product_name, category, price, stock_quantity) VALUES (?, ?, ?, ?)',
        products_data
    )
    
    # Generate orders
    base_date = datetime.now() - timedelta(days=90)
    
    for i in range(50):
        customer_id = random.randint(1, 10)
        order_date = (base_date + timedelta(days=random.randint(0, 90))).strftime('%Y-%m-%d')
        status = random.choice(['Completed', 'Completed', 'Completed', 'Pending', 'Shipped'])
        
        cursor.execute(
            'INSERT INTO orders (customer_id, order_date, status, total_amount) VALUES (?, ?, ?, ?)',
            (customer_id, order_date, status, 0.0)
        )
        
        order_id = cursor.lastrowid
        
        # Add 1-4 items to each order
        num_items = random.randint(1, 4)
        total_amount = 0.0
        
        for _ in range(num_items):
            product_id = random.randint(1, 15)
            quantity = random.randint(1, 3)
            
            cursor.execute('SELECT price FROM products WHERE product_id = ?', (product_id,))
            price = cursor.fetchone()[0]
            
            item_total = price * quantity
            total_amount += item_total
            
            cursor.execute(
                'INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)',
                (order_id, product_id, quantity, price)
            )
        
        # Update order total
        cursor.execute('UPDATE orders SET total_amount = ? WHERE order_id = ?', (total_amount, order_id))
    
    conn.commit()
    conn.close()
    
    print("✓ Sample database created: sample_ecommerce.db")
    print("✓ Tables: customers, products, orders, order_items")
    print("✓ Sample data inserted")

if __name__ == "__main__":
    create_sample_database()
