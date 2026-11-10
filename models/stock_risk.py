
import math


# ==========================================================
# RETAILPULSE AI
# STOCKOUT & OVERSTOCK RISK ANALYSIS ENGINE
# ==========================================================


def analyze_stock_risk(product, reorder):

    """
    Analyze stockout and overstock risk using:
    - Current inventory
    - Supplier lead time
    - Safety stock
    - Manual reorder level
    - Available demand forecasts

    Compatible with SQLite Row objects.
    """

    # ------------------------------------------------------
    # 1. PRODUCT INFORMATION
    # ------------------------------------------------------

    current_stock = max(
        0,
        int(product["stock_quantity"] or 0)
    )

    lead_time = max(
        1,
        int(product["lead_time_days"] or 3)
    )

    safety_stock = max(
        0,
        int(product["safety_stock"] or 5)
    )

    reorder_level = max(
        0,
        int(product["reorder_level"] or 0)
    )

    # ------------------------------------------------------
    # 2. FORECAST INFORMATION
    # ------------------------------------------------------

    forecast_available = reorder.get(
        "forecast_available",
        False
    )

    daily_demand = reorder.get(
        "predicted_daily_demand"
    )

    lead_time_demand = reorder.get(
        "lead_time_demand"
    )

    target_stock = reorder.get(
        "target_stock"
    )

    # ------------------------------------------------------
    # 3. INITIAL RESULT
    # ------------------------------------------------------

    result = {
        "product_id": product["id"],
        "product_name": product["name"],
        "current_stock": current_stock,
        "lead_time_days": lead_time,
        "days_remaining": None,
        "risk_level": "Insufficient Data",
        "risk_type": "unknown",
        "message": "",
        "recommendation": "",
        "stock_above_target": 0,
        "excess_stock": 0
    }

    # ------------------------------------------------------
    # 4. MANUAL STOCKOUT CHECK
    # ------------------------------------------------------

    if current_stock == 0:

        result.update({
            "risk_level": "Critical",
            "risk_type": "stockout",
            "message": "Product is currently out of stock.",
            "recommendation": (
                "Review replenishment immediately."
            )
        })

        return result

    if current_stock <= reorder_level:

        result.update({
            "risk_level": "High",
            "risk_type": "stockout",
            "message": (
                "Stock has reached the manual reorder level."
            ),
            "recommendation": (
                "Review supplier availability and reorder."
            )
        })

        return result

    # ------------------------------------------------------
    # 5. FORECAST VALIDATION
    # ------------------------------------------------------

    if not forecast_available or daily_demand is None:

        result.update({
            "risk_level": "Insufficient Data",
            "risk_type": "unknown",
            "message": (
                "Reliable demand forecast is unavailable."
            ),
            "recommendation": (
                "Collect more sales history for risk analysis."
            )
        })

        return result

    try:

        daily_demand = float(daily_demand)

        if (
            not math.isfinite(daily_demand)
            or daily_demand <= 0
        ):
            raise ValueError("Invalid predicted daily demand")

    except (TypeError, ValueError, OverflowError):

        result.update({
            "risk_level": "Insufficient Data",
            "risk_type": "unknown",
            "message": (
                "Predicted daily demand is invalid."
            ),
            "recommendation": (
                "Review sales history and forecasting results."
            )
        })

        return result

    # ------------------------------------------------------
    # 6. LEAD TIME DEMAND
    # ------------------------------------------------------

    try:

        if lead_time_demand is None:

            lead_time_demand = daily_demand * lead_time

        else:

            lead_time_demand = float(lead_time_demand)

        if (
            not math.isfinite(lead_time_demand)
            or lead_time_demand < 0
        ):
            raise ValueError("Invalid lead time demand")

    except (TypeError, ValueError, OverflowError):

        result.update({
            "message": "Lead time demand could not be calculated.",
            "recommendation": (
                "Review the smart reorder calculations."
            )
        })

        return result

    # ------------------------------------------------------
    # 7. TARGET STOCK
    # ------------------------------------------------------

    try:

        if target_stock is None:

            target_stock = (
                lead_time_demand + safety_stock
            )

        else:

            target_stock = float(target_stock)

        if (
            not math.isfinite(target_stock)
            or target_stock < 0
        ):
            raise ValueError("Invalid target stock")

    except (TypeError, ValueError, OverflowError):

        result.update({
            "message": "Target stock could not be calculated.",
            "recommendation": (
                "Review inventory target calculations."
            )
        })

        return result

    # ------------------------------------------------------
    # 8. INVENTORY COVERAGE
    # ------------------------------------------------------

    days_remaining = round(
        current_stock / daily_demand,
        1
    )

    result["days_remaining"] = days_remaining

    # ------------------------------------------------------
    # 9. STOCKOUT RISK CLASSIFICATION
    # ------------------------------------------------------

    if current_stock <= lead_time_demand:

        risk_level = "Critical"
        risk_type = "stockout"

        message = (
            "Available inventory may not cover expected "
            "demand during supplier lead time."
        )

        action = (
            "Review replenishment immediately."
        )

    elif days_remaining <= lead_time + 2:

        risk_level = "High"
        risk_type = "stockout"

        message = (
            "Inventory coverage is close to supplier lead time."
        )

        action = (
            "Plan replenishment and monitor stock closely."
        )

    elif days_remaining <= lead_time + 7:

        risk_level = "Medium"
        risk_type = "stockout"

        message = (
            "Inventory coverage is limited compared with "
            "the expected demand period."
        )

        action = (
            "Monitor sales and prepare the next reorder."
        )

    else:

        # --------------------------------------------------
        # 10. OVERSTOCK ANALYSIS
        # --------------------------------------------------

        stock_above_target = max(
            0,
            current_stock - math.ceil(target_stock)
        )

        overstock_threshold = max(
            safety_stock * 2,
            math.ceil(daily_demand * 7)
        )

        if (
            current_stock > target_stock * 1.5
            and stock_above_target >= overstock_threshold
        ):

            risk_level = "Overstock"
            risk_type = "overstock"

            excess_stock = stock_above_target

            message = (
                "Current inventory is substantially above "
                "the forecast-based target stock."
            )

            action = (
                "Review purchasing plans and avoid unnecessary "
                "additional stock."
            )

        else:

            risk_level = "Healthy"
            risk_type = "healthy"

            excess_stock = 0

            message = (
                "Current inventory provides sufficient "
                "estimated demand coverage."
            )

            action = (
                "Continue monitoring sales and inventory."
            )

        result["stock_above_target"] = stock_above_target
        result["excess_stock"] = excess_stock

    # ------------------------------------------------------
    # 11. FINAL RESULT
    # ------------------------------------------------------

    result.update({
        "risk_level": risk_level,
        "risk_type": risk_type,
        "message": message,
        "recommendation": action
    })

    return result
