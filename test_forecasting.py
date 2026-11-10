from database.db import get_connection
from models.demand_forecasting import forecast_product


connection = get_connection()

try:
    products = connection.execute(
        "SELECT id, name FROM products"
    ).fetchall()
finally:
    connection.close()


for product in products:

    product_id = product["id"]
    product_name = product["name"]

    print("\n" + "=" * 40)
    print("PRODUCT:", product_name)
    print("=" * 40)

    result = forecast_product(product_id)

    print("STATUS:", result["status"])

    if result["status"] == "success":

        print("\n7-DAY DEMAND FORECAST:")

        for item in result["forecasts"]:
            print(
                item["date"],
                "->",
                item["predicted_demand"],
                "units"
            )

        print(
            "\nTotal predicted demand:",
            result["total_predicted_demand"],
            "units"
        )

    else:
        print("MESSAGE:", result["message"])