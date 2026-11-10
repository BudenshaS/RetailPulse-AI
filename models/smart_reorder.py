
import math

from models.demand_forecasting import forecast_product


REVIEW_PERIOD_DAYS = 7


def generate_reorder_recommendation(product):

    product_id = product["id"]
    product_name = product["name"]

    current_stock = int(product["stock_quantity"])
    reorder_level = int(product["reorder_level"])

    lead_time = int(product["lead_time_days"])
    safety_stock = int(product["safety_stock"])

    forecast = forecast_product(product_id)

    # ----------------------------------
    # CASE 1: FORECAST IS AVAILABLE
    # ----------------------------------

    if forecast["status"] == "success":

        forecast_days = forecast["forecasts"]

        predicted_daily_demand = (
            forecast["total_predicted_demand"] / len(forecast_days)
        )

        # Estimated demand during supplier delivery
        lead_time_demand = predicted_daily_demand * lead_time

        # Additional demand during the 7-day review period
        review_demand = (
            predicted_daily_demand * REVIEW_PERIOD_DAYS
        )

        reorder_point = math.ceil(
            lead_time_demand + safety_stock
        )

        target_stock = math.ceil(
            lead_time_demand + review_demand + safety_stock
        )

        recommended_quantity = max(
            0,
            target_stock - current_stock
        )

        if current_stock <= lead_time_demand:
            status = "critical"

        elif current_stock <= reorder_point:
            status = "reorder_soon"

        else:
            status = "healthy"

        return {
            "product_id": product_id,
            "product_name": product_name,
            "current_stock": current_stock,
            "lead_time_days": lead_time,
            "safety_stock": safety_stock,
            "predicted_daily_demand": round(
                predicted_daily_demand, 2
            ),
            "lead_time_demand": round(
                lead_time_demand, 2
            ),
            "reorder_point": reorder_point,
            "target_stock": target_stock,
            "recommended_quantity": recommended_quantity,
            "status": status,
            "forecast_available": True,
            "message": "Recommendation based on AI demand forecast."
        }

    # ----------------------------------
    # CASE 2: FORECAST IS UNAVAILABLE
    # ----------------------------------

    reorder_point = reorder_level

    if current_stock <= 0:
        status = "critical"

    elif current_stock <= reorder_point:
        status = "reorder_soon"

    else:
        status = "healthy"

    recommended_quantity = max(
        0,
        reorder_point - current_stock
    )

    return {
        "product_id": product_id,
        "product_name": product_name,
        "current_stock": current_stock,
        "lead_time_days": lead_time,
        "safety_stock": safety_stock,
        "predicted_daily_demand": None,
        "lead_time_demand": None,
        "reorder_point": reorder_point,
        "target_stock": reorder_point,
        "recommended_quantity": recommended_quantity,
        "status": status,
        "forecast_available": False,
        "message": (
            "Forecast unavailable. Using the manual reorder level. "
            "This is a limited recommendation."
        )
    }


def generate_all_recommendations(products):

    recommendations = []

    for product in products:
        recommendation = generate_reorder_recommendation(product)
        recommendations.append(recommendation)

    return recommendations
