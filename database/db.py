
import sqlite3
import os

DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "retailpulse.db"
)


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    connection = get_connection()

    try:
        # Create products table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock_quantity INTEGER NOT NULL,
                reorder_level INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create sales table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                unit_price REAL NOT NULL,
                total_amount REAL NOT NULL,
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (product_id)
                REFERENCES products(id)
            )
        """)

        # ======================================
        # SAFE DATABASE MIGRATION
        # ======================================

        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(products)"
            ).fetchall()
        }

        if "lead_time_days" not in existing_columns:
            connection.execute("""
                ALTER TABLE products
                ADD COLUMN lead_time_days INTEGER NOT NULL DEFAULT 3
            """)

        if "safety_stock" not in existing_columns:
            connection.execute("""
                ALTER TABLE products
                ADD COLUMN safety_stock INTEGER NOT NULL DEFAULT 5
            """)

        # ======================================
        # DATABASE INDEXES
        # ======================================

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_sales_product
            ON sales(product_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_sales_date
            ON sales(sale_date)
        """)

        connection.commit()

        print("RetailPulse AI database initialized successfully!")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
