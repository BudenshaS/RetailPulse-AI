import random
from datetime import datetime, timedelta

from database.db import get_connection


# ==========================================
# SAMPLE SALES DATA GENERATOR
# ==========================================

SAMPLE_DAYS = 30
random.seed(42)


def generate_sample_sales():

    connection = get_connection()

    try:
        products = connection.execute(
            "SELECT id, name FROM products"
        ).fetchall()

        if not products:
            print("No products found. Add a product first.")
            return

        for product in products:

            product_id = product["id"]
            product_name = product["name"]

            # Get the latest recorded sale and its selling price
            latest_sale = connection.execute("""
                SELECT sale_date, unit_price
                FROM sales
                WHERE product_id = ?
                ORDER BY sale_date DESC
                LIMIT 1
            """, (product_id,)).fetchone()

            if not latest_sale:
                print(
                    f"Skipping {product_name}: "
                    "No existing sale to determine its price."
                )
                continue

            last_date = datetime.strptime(
                latest_sale["sale_date"][:10],
                "%Y-%m-%d"
            ).date()

            unit_price = float(latest_sale["unit_price"])

            added = 0

            for day in range(SAMPLE_DAYS, 0, -1):

                sale_date = last_date - timedelta(days=day)

                # Avoid duplicating existing sales on the same date
                existing = connection.execute("""
                    SELECT COUNT(*)
                    FROM sales
                    WHERE product_id = ?
                    AND DATE(sale_date) = ?
                """, (product_id, sale_date.isoformat())).fetchone()[0]

                if existing:
                    continue

                quantity = random.randint(1, 5)
                total_amount = quantity * unit_price

                connection.execute("""
                    INSERT INTO sales (
                        product_id,
                        quantity,
                        unit_price,
                        total_amount,
                        sale_date
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    product_id,
                    quantity,
                    unit_price,
                    total_amount,
                    sale_date.isoformat()
                ))

                added += 1

            print(f"\nProduct: {product_name}")
            print(f"Sample sales days added: {added}")

        connection.commit()
        print("\nSample sales generation completed!")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    generate_sample_sales()