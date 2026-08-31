-- Sample shop_db schema and data for migration demo
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20),
    city VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    price NUMERIC(10, 2) NOT NULL,
    stock_qty INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    total_amount NUMERIC(10, 2),
    status VARCHAR(50) DEFAULT 'pending',
    order_date TIMESTAMP DEFAULT NOW()
);

-- Insert sample customers
INSERT INTO customers (name, email, phone, city) VALUES
('Alice Johnson',    'alice@example.com',   '9876543210', 'Mumbai'),
('Bob Smith',        'bob@example.com',     '9123456789', 'Delhi'),
('Carol White',      'carol@example.com',   '9988776655', 'Bangalore'),
('David Brown',      'david@example.com',   '9001122334', 'Chennai'),
('Eva Green',        'eva@example.com',     '9871234567', 'Hyderabad'),
('Frank Miller',     'frank@example.com',   '9765432109', 'Pune'),
('Grace Lee',        'grace@example.com',   '9654321098', 'Kolkata'),
('Henry Wilson',     'henry@example.com',   '9543210987', 'Ahmedabad'),
('Iris Taylor',      'iris@example.com',    '9432109876', 'Jaipur'),
('Jack Anderson',    'jack@example.com',    '9321098765', 'Lucknow');

-- Insert sample products
INSERT INTO products (name, category, price, stock_qty) VALUES
('Laptop Pro 15',     'Electronics',   75000.00, 50),
('Wireless Mouse',    'Electronics',    1200.00, 200),
('USB-C Hub',         'Electronics',    2500.00, 150),
('Desk Chair',        'Furniture',     12000.00, 30),
('Standing Desk',     'Furniture',     25000.00, 20),
('Notebook A4',       'Stationery',      150.00, 500),
('Blue Pen Set',      'Stationery',       80.00, 1000),
('Coffee Mug',        'Kitchen',         350.00, 300),
('Water Bottle',      'Kitchen',         450.00, 250),
('Desk Lamp',         'Electronics',    1800.00, 100);

-- Insert sample orders
INSERT INTO orders (customer_id, product_id, quantity, total_amount, status) VALUES
(1, 1, 1,  75000.00, 'delivered'),
(1, 2, 2,   2400.00, 'delivered'),
(2, 3, 1,   2500.00, 'shipped'),
(3, 4, 1,  12000.00, 'delivered'),
(4, 5, 1,  25000.00, 'pending'),
(5, 6, 10,  1500.00, 'delivered'),
(6, 7, 5,    400.00, 'delivered'),
(7, 8, 3,   1050.00, 'shipped'),
(8, 9, 2,    900.00, 'pending'),
(9, 10, 1,  1800.00, 'delivered'),
(10, 1, 1, 75000.00, 'cancelled'),
(2, 2, 3,   3600.00, 'delivered');
