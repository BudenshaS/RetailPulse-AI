
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash

from database.db import get_connection, initialize_database
from models.demand_forecasting import forecast_product
from models.smart_reorder import generate_reorder_recommendation
from models.stock_risk import analyze_stock_risk


app = Flask(__name__)
app.secret_key = "retailpulse-development-key"

initialize_database()


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/")
def dashboard():

    connection = get_connection()

    try:
        # ==========================================
        # INVENTORY STATISTICS
        # ==========================================

        total_products = connection.execute("""
            SELECT COUNT(*) FROM products
        """).fetchone()[0]

        total_stock_value = connection.execute("""
            SELECT COALESCE(SUM(price * stock_quantity), 0)
            FROM products
        """).fetchone()[0]

        low_stock_count = connection.execute("""
            SELECT COUNT(*) FROM products
            WHERE stock_quantity > 0
            AND stock_quantity <= reorder_level
        """).fetchone()[0]

        out_of_stock_count = connection.execute("""
            SELECT COUNT(*) FROM products
            WHERE stock_quantity = 0
        """).fetchone()[0]

        total_categories = connection.execute("""
            SELECT COUNT(DISTINCT category)
            FROM products
        """).fetchone()[0]

        recent_products = connection.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

        low_stock_products = connection.execute("""
            SELECT *
            FROM products
            WHERE stock_quantity > 0
            AND stock_quantity <= reorder_level
            ORDER BY stock_quantity ASC
            LIMIT 5
        """).fetchall()

        # ==========================================
        # SALES ANALYTICS
        # ==========================================

        total_sales = connection.execute("""
            SELECT COALESCE(SUM(total_amount), 0)
            FROM sales
        """).fetchone()[0]

        total_transactions = connection.execute("""
            SELECT COUNT(*)
            FROM sales
        """).fetchone()[0]

        total_units_sold = connection.execute("""
            SELECT COALESCE(SUM(quantity), 0)
            FROM sales
        """).fetchone()[0]

        # ==========================================
        # RECENT SALES
        # ==========================================

        recent_sales = connection.execute("""
            SELECT
                sales.id,
                products.name AS product_name,
                sales.quantity,
                sales.unit_price,
                sales.total_amount,
                sales.sale_date
            FROM sales
            JOIN products
            ON products.id = sales.product_id
            ORDER BY sales.id DESC
            LIMIT 5
        """).fetchall()

        # ==========================================
        # ALL PRODUCTS
        # ==========================================

        all_products = connection.execute("""
            SELECT *
            FROM products
            ORDER BY name
        """).fetchall()

        # ==========================================
        # LAST 7 DAYS SALES CHART DATA
        # ==========================================

        today = datetime.now().date()
        start_date = today - timedelta(days=6)

        sales_rows = connection.execute("""
            SELECT
                DATE(sale_date) AS sale_day,
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(SUM(quantity), 0) AS units_sold,
                COUNT(*) AS transactions
            FROM sales
            WHERE DATE(sale_date) BETWEEN ? AND ?
            GROUP BY DATE(sale_date)
            ORDER BY sale_day
        """, (
            start_date.isoformat(),
            today.isoformat()
        )).fetchall()

        sales_by_date = {
            row["sale_day"]: {
                "revenue": float(row["revenue"] or 0),
                "units_sold": int(row["units_sold"] or 0),
                "transactions": int(row["transactions"] or 0)
            }
            for row in sales_rows
            if row["sale_day"]
        }

        daily_sales_chart = []

        for i in range(7):

            chart_date = start_date + timedelta(days=i)
            date_key = chart_date.isoformat()

            day_data = sales_by_date.get(date_key, {
                "revenue": 0,
                "units_sold": 0,
                "transactions": 0
            })

            daily_sales_chart.append({
                "date": date_key,
                "label": chart_date.strftime("%d %b"),
                "revenue": day_data["revenue"],
                "units_sold": day_data["units_sold"],
                "transactions": day_data["transactions"]
            })

        max_daily_sales = max(
            (item["revenue"] for item in daily_sales_chart),
            default=0
        )

        for item in daily_sales_chart:

            item["bar_width"] = (
                round(
                    item["revenue"] / max_daily_sales * 100,
                    2
                )
                if max_daily_sales > 0 else 0
            )

    finally:
        connection.close()

    # ==========================================
    # AI DEMAND FORECASTING
    # ==========================================

    forecast_products = []
    daily_demand = {}

    for product in all_products:

        try:
            result = forecast_product(product["id"])

            status = result.get("status", "error")
            message = result.get("message", "")
            forecasts = result.get("forecasts", []) or []

            total_predicted_demand = (
                result.get("total_predicted_demand", 0) or 0
            )

            history_days = result.get("history_days", 0) or 0

            if status == "success":

                for forecast in forecasts:

                    forecast_date = forecast.get("date")

                    predicted_demand = float(
                        forecast.get("predicted_demand", 0) or 0
                    )

                    if forecast_date:

                        daily_demand[forecast_date] = (
                            daily_demand.get(forecast_date, 0)
                            + predicted_demand
                        )

        except Exception as error:

            status = "error"
            message = str(error)
            forecasts = []
            total_predicted_demand = 0
            history_days = 0

        forecast_products.append({
            "product_name": product["name"],
            "current_stock": product["stock_quantity"],
            "reorder_level": product["reorder_level"],
            "status": status,
            "message": message,
            "history_days": history_days,
            "forecasts": forecasts,
            "total_predicted_demand": total_predicted_demand
        })

    successful_forecasts = sum(
        1 for item in forecast_products
        if item["status"] == "success"
    )

    # ==========================================
    # SEVEN-DAY FORECAST CHART
    # ==========================================

    max_daily_demand = max(
        daily_demand.values(),
        default=0
    )

    daily_forecast_totals = []

    for forecast_date in sorted(daily_demand):

        demand = daily_demand[forecast_date]

        bar_width = (
            min(
                100,
                max(2, (demand / max_daily_demand) * 100)
            )
            if max_daily_demand > 0 else 0
        )

        daily_forecast_totals.append({
            "date": forecast_date,
            "demand": demand,
            "bar_width": round(bar_width, 2)
        })

    # ==========================================
    # SMART REORDER INTELLIGENCE
    # ==========================================

    smart_reorder_recommendations = []

    for product in all_products:

        try:
            recommendation = generate_reorder_recommendation(
                product
            )

        except Exception as error:

            current_stock = int(product["stock_quantity"])
            reorder_level = int(product["reorder_level"])

            if current_stock == 0:
                status = "critical"

            elif current_stock <= reorder_level:
                status = "reorder_soon"

            else:
                status = "healthy"

            recommendation = {
                "product_id": product["id"],
                "product_name": product["name"],
                "current_stock": current_stock,
                "lead_time_days": product["lead_time_days"],
                "safety_stock": product["safety_stock"],
                "predicted_daily_demand": None,
                "lead_time_demand": None,
                "reorder_point": reorder_level,
                "target_stock": reorder_level,
                "recommended_quantity": max(
                    0,
                    reorder_level - current_stock
                ),
                "status": status,
                "forecast_available": False,
                "message": (
                    "Forecast unavailable. Using manual reorder level. "
                    + str(error)
                )
            }

        recommendation.setdefault(
            "lead_time_days",
            product["lead_time_days"]
        )

        recommendation.setdefault(
            "safety_stock",
            product["safety_stock"]
        )

        smart_reorder_recommendations.append(recommendation)

    # ==========================================
    # REORDER STATUS COUNTS
    # ==========================================

    critical_reorder_count = sum(
        1 for item in smart_reorder_recommendations
        if item["status"] == "critical"
    )

    reorder_soon_count = sum(
        1 for item in smart_reorder_recommendations
        if item["status"] == "reorder_soon"
    )

    healthy_reorder_count = sum(
        1 for item in smart_reorder_recommendations
        if item["status"] == "healthy"
    )

    # ==========================================
    # STOCK COMPARISON CHART
    # ==========================================

    stock_chart_data = []

    for item in smart_reorder_recommendations:

        stock_chart_data.append({
            "product_name": item["product_name"],
            "current_stock": int(
                item.get("current_stock", 0) or 0
            ),
            "reorder_point": int(
                item.get("reorder_point", 0) or 0
            ),
            "safety_stock": int(
                item.get("safety_stock", 0) or 0
            )
        })

    max_stock_value = max(
        (
            max(
                item["current_stock"],
                item["reorder_point"],
                item["safety_stock"]
            )
            for item in stock_chart_data
        ),
        default=0
    )

    for item in stock_chart_data:

        item["current_width"] = (
            round(
                item["current_stock"] / max_stock_value * 100,
                2
            )
            if max_stock_value else 0
        )

        item["reorder_width"] = (
            round(
                item["reorder_point"] / max_stock_value * 100,
                2
            )
            if max_stock_value else 0
        )

        item["safety_width"] = (
            round(
                item["safety_stock"] / max_stock_value * 100,
                2
            )
            if max_stock_value else 0
        )

    # ==========================================
    # STOCKOUT & OVERSTOCK RISK INTELLIGENCE
    # ==========================================

    stock_risk_results = []

    for product, reorder in zip(
        all_products,
        smart_reorder_recommendations
    ):

        try:
            risk = analyze_stock_risk(product, reorder)

            risk["lead_time_days"] = product["lead_time_days"]

            # Keep stock above target separate from overstock excess.
            # Being above target does not automatically mean overstock.

            risk["stock_above_target"] = max(
                0,
                int(
                    risk.get("stock_above_target", 0) or 0
                )
            )

            # Only products classified as Overstock receive
            # an overstock excess value.

            if risk.get("risk_level") == "Overstock":

                risk["overstock_excess"] = max(
                    0,
                    int(
                        risk.get("excess_stock", 0) or 0
                    )
                )

            else:

                risk["overstock_excess"] = 0

            # Preserve the separate overstock measurement.
            risk["excess_stock"] = risk["overstock_excess"]

        except Exception as error:

            risk = {
                "product_id": product["id"],
                "product_name": product["name"],
                "current_stock": product["stock_quantity"],
                "lead_time_days": product["lead_time_days"],
                "days_remaining": None,
                "risk_level": "Insufficient Data",
                "risk_type": "unknown",
                "message": (
                    "Risk analysis could not be completed."
                ),
                "recommendation": str(error),
                "stock_above_target": 0,
                "overstock_excess": 0,
                "excess_stock": 0
            }

        stock_risk_results.append(risk)

    # ==========================================
    # RISK COUNTS
    # ==========================================

    stockout_critical_count = sum(
        1 for item in stock_risk_results
        if item["risk_level"] == "Critical"
    )

    stockout_high_count = sum(
        1 for item in stock_risk_results
        if item["risk_level"] == "High"
    )

    medium_risk_count = sum(
        1 for item in stock_risk_results
        if item["risk_level"] == "Medium"
    )

    overstock_count = sum(
        1 for item in stock_risk_results
        if item["risk_level"] == "Overstock"
    )

    healthy_risk_count = sum(
        1 for item in stock_risk_results
        if item["risk_level"] == "Healthy"
    )

    insufficient_risk_count = sum(
        1 for item in stock_risk_results
        if item["risk_level"] == "Insufficient Data"
    )

    # ==========================================
    # INVENTORY RISK CHART
    # ==========================================

    risk_chart_data = [
        {
            "label": "Critical",
            "count": stockout_critical_count
        },
        {
            "label": "High Risk",
            "count": stockout_high_count
        },
        {
            "label": "Medium Risk",
            "count": medium_risk_count
        },
        {
            "label": "Overstock",
            "count": overstock_count
        },
        {
            "label": "Healthy",
            "count": healthy_risk_count
        },
        {
            "label": "Insufficient Data",
            "count": insufficient_risk_count
        }
    ]

    total_risk_items = sum(
        item["count"] for item in risk_chart_data
    )

    for item in risk_chart_data:

        item["percentage"] = (
            round(
                item["count"] / total_risk_items * 100,
                2
            )
            if total_risk_items else 0
        )

    # ==========================================
    # SEND DATA TO DASHBOARD
    # ==========================================

    return render_template(
        "dashboard.html",

        # INVENTORY
        total_products=total_products,
        total_stock_value=total_stock_value,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        total_categories=total_categories,

        recent_products=recent_products,
        low_stock_products=low_stock_products,

        # SALES
        total_sales=total_sales,
        total_transactions=total_transactions,
        total_units_sold=total_units_sold,
        recent_sales=recent_sales,

        # DAILY SALES CHART
        daily_sales_chart=daily_sales_chart,

        # FORECAST
        forecast_products=forecast_products,
        successful_forecasts=successful_forecasts,
        daily_forecast_totals=daily_forecast_totals,

        # SMART REORDER
        smart_reorder_recommendations=smart_reorder_recommendations,
        critical_reorder_count=critical_reorder_count,
        reorder_soon_count=reorder_soon_count,
        healthy_reorder_count=healthy_reorder_count,

        # STOCK COMPARISON CHART
        stock_chart_data=stock_chart_data,

        # STOCK RISK
        stock_risk_results=stock_risk_results,
        stockout_critical_count=stockout_critical_count,
        stockout_high_count=stockout_high_count,
        medium_risk_count=medium_risk_count,
        overstock_count=overstock_count,
        healthy_risk_count=healthy_risk_count,
        insufficient_risk_count=insufficient_risk_count,

        # INVENTORY RISK CHART
        risk_chart_data=risk_chart_data
    )


# ==========================================
# PRODUCT MANAGEMENT
# ==========================================

@app.route("/products", methods=["GET", "POST"])
def products():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()

        try:
            price = float(request.form.get("price", 0))
            stock = int(request.form.get("stock_quantity", 0))
            reorder = int(request.form.get("reorder_level", 0))

            lead_time_days = int(
                request.form.get("lead_time_days", 3)
            )

            safety_stock = int(
                request.form.get("safety_stock", 5)
            )

            if not name or not category:
                raise ValueError(
                    "Product name and category are required."
                )

            if (
                price <= 0
                or stock < 0
                or reorder < 0
                or not 1 <= lead_time_days <= 365
                or safety_stock < 0
            ):
                raise ValueError(
                    "Please enter valid product and supplier details."
                )

            connection = get_connection()

            try:
                connection.execute("""
                    INSERT INTO products (
                        name,
                        category,
                        price,
                        stock_quantity,
                        reorder_level,
                        lead_time_days,
                        safety_stock
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    category,
                    price,
                    stock,
                    reorder,
                    lead_time_days,
                    safety_stock
                ))

                connection.commit()

            finally:
                connection.close()

            flash(
                "Product added successfully!",
                "success"
            )

        except (ValueError, TypeError):
            flash(
                "Please enter valid product details.",
                "error"
            )

        return redirect(url_for("products"))

    connection = get_connection()

    try:
        product_list = connection.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
        """).fetchall()

    finally:
        connection.close()

    return render_template(
        "products.html",
        products=product_list
    )


# ==========================================
# INVENTORY MANAGEMENT
# ==========================================

@app.route("/inventory")
def inventory():

    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all")

    allowed_filters = [
        "all",
        "healthy",
        "low",
        "out"
    ]

    if status_filter not in allowed_filters:
        status_filter = "all"

    connection = get_connection()

    try:
        total_products = connection.execute("""
            SELECT COUNT(*) FROM products
        """).fetchone()[0]

        low_stock = connection.execute("""
            SELECT COUNT(*) FROM products
            WHERE stock_quantity > 0
            AND stock_quantity <= reorder_level
        """).fetchone()[0]

        out_of_stock = connection.execute("""
            SELECT COUNT(*) FROM products
            WHERE stock_quantity = 0
        """).fetchone()[0]

        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if search:

            query += """
                AND (name LIKE ? OR category LIKE ?)
            """

            params.extend([
                f"%{search}%",
                f"%{search}%"
            ])

        if status_filter == "low":

            query += """
                AND stock_quantity > 0
                AND stock_quantity <= reorder_level
            """

        elif status_filter == "out":

            query += """
                AND stock_quantity = 0
            """

        elif status_filter == "healthy":

            query += """
                AND stock_quantity > reorder_level
            """

        query += """
            ORDER BY stock_quantity ASC, name ASC
        """

        products_list = connection.execute(
            query,
            params
        ).fetchall()

        return render_template(
            "inventory.html",
            products=products_list,
            total_products=total_products,
            low_stock=low_stock,
            out_of_stock=out_of_stock,
            search=search,
            status_filter=status_filter
        )

    finally:
        connection.close()


# ==========================================
# SALES MANAGEMENT
# ==========================================

@app.route("/sales", methods=["GET", "POST"])
def sales():

    connection = get_connection()

    try:

        if request.method == "POST":

            product_id = request.form.get(
                "product_id",
                type=int
            )

            quantity = request.form.get(
                "quantity",
                type=int
            )

            if (
                not product_id
                or not quantity
                or quantity <= 0
            ):
                flash(
                    "Please enter valid sales details.",
                    "error"
                )

                return redirect(url_for("sales"))

            connection.execute("BEGIN")

            product = connection.execute("""
                SELECT *
                FROM products
                WHERE id = ?
            """, (product_id,)).fetchone()

            if product is None:

                connection.rollback()

                flash(
                    "Product not found.",
                    "error"
                )

                return redirect(url_for("sales"))

            if quantity > product["stock_quantity"]:

                connection.rollback()

                flash(
                    "Insufficient stock for this sale.",
                    "error"
                )

                return redirect(url_for("sales"))

            unit_price = product["price"]
            total_amount = unit_price * quantity

            connection.execute("""
                INSERT INTO sales
                (
                    product_id,
                    quantity,
                    unit_price,
                    total_amount
                )
                VALUES (?, ?, ?, ?)
            """, (
                product_id,
                quantity,
                unit_price,
                total_amount
            ))

            connection.execute("""
                UPDATE products
                SET stock_quantity = stock_quantity - ?
                WHERE id = ?
            """, (
                quantity,
                product_id
            ))

            connection.commit()

            flash(
                "Sale recorded successfully!",
                "success"
            )

            return redirect(url_for("sales"))

        # ==========================================
        # PRODUCT LIST
        # ==========================================

        product_list = connection.execute("""
            SELECT *
            FROM products
            ORDER BY name
        """).fetchall()

        # ==========================================
        # SALES LIST
        # ==========================================

        sales_list = connection.execute("""
            SELECT
                sales.id,
                products.name AS product_name,
                sales.quantity,
                sales.unit_price,
                sales.total_amount,
                sales.sale_date
            FROM sales
            JOIN products
            ON products.id = sales.product_id
            ORDER BY sales.id DESC
        """).fetchall()

        # ==========================================
        # SALES STATISTICS
        # ==========================================

        total_sales = connection.execute("""
            SELECT COALESCE(SUM(total_amount), 0)
            FROM sales
        """).fetchone()[0]

        total_transactions = connection.execute("""
            SELECT COUNT(*)
            FROM sales
        """).fetchone()[0]

        total_units_sold = connection.execute("""
            SELECT COALESCE(SUM(quantity), 0)
            FROM sales
        """).fetchone()[0]

        return render_template(
            "sales.html",
            products=product_list,
            sales=sales_list,
            total_sales=total_sales,
            total_transactions=total_transactions,
            total_units_sold=total_units_sold
        )

    except Exception:

        connection.rollback()
        raise

    finally:
        connection.close()


# ==========================================
# APPLICATION START
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)
