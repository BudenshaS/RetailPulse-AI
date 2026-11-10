
import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestRegressor
from database.db import get_connection


# ==========================================
# DEMAND FORECASTING ENGINE
# ==========================================

FORECAST_DAYS = 7
MIN_HISTORY_DAYS = 21


def get_sales_history(product_id):

    connection = get_connection()

    try:
        query = """
            SELECT
                DATE(sale_date) AS sale_day,
                SUM(quantity) AS daily_quantity
            FROM sales
            WHERE product_id = ?
            GROUP BY DATE(sale_date)
            ORDER BY sale_day
        """

        data = pd.read_sql_query(
            query,
            connection,
            params=(product_id,)
        )

    finally:
        connection.close()

    if data.empty:
        return None

    data["sale_day"] = pd.to_datetime(data["sale_day"])

    # Fill missing calendar days with zero sales
    data = data.set_index("sale_day")

    full_dates = pd.date_range(
        start=data.index.min(),
        end=data.index.max(),
        freq="D"
    )

    data = data.reindex(full_dates, fill_value=0)

    data.index.name = "sale_day"
    data = data.reset_index()

    data["daily_quantity"] = (
        data["daily_quantity"].astype(float)
    )

    return data


def create_features(data):

    data = data.copy()

    data["day_of_week"] = data["sale_day"].dt.dayofweek

    data["day_number"] = (
        data["sale_day"] - data["sale_day"].min()
    ).dt.days

    data["lag_1"] = data["daily_quantity"].shift(1)

    data["lag_7"] = data["daily_quantity"].shift(7)

    data["rolling_mean_7"] = (
        data["daily_quantity"]
        .shift(1)
        .rolling(window=7)
        .mean()
    )

    return data.dropna().reset_index(drop=True)


def forecast_product(product_id):

    data = get_sales_history(product_id)

    if data is None:
        return {
            "status": "no_data",
            "message": "No sales history available."
        }

    if len(data) < MIN_HISTORY_DAYS:
        return {
            "status": "insufficient_data",
            "history_days": len(data),
            "required_days": MIN_HISTORY_DAYS,
            "message": "More sales history is needed."
        }

    feature_columns = [
        "day_of_week",
        "day_number",
        "lag_1",
        "lag_7",
        "rolling_mean_7"
    ]

    training_data = create_features(data)

    if len(training_data) < 10:
        return {
            "status": "insufficient_data",
            "history_days": len(data),
            "required_days": MIN_HISTORY_DAYS,
            "message": "Not enough training samples."
        }

    X = training_data[feature_columns]
    y = training_data["daily_quantity"]

    model = RandomForestRegressor(
        n_estimators=100,
        random_state=42,
        max_depth=5
    )

    model.fit(X, y)

    history = data["daily_quantity"].tolist()
    forecasts = []

    last_date = data["sale_day"].max()

    for day in range(1, FORECAST_DAYS + 1):

        next_date = last_date + pd.Timedelta(days=day)

        features = pd.DataFrame([{
            "day_of_week": next_date.dayofweek,
            "day_number": len(history),
            "lag_1": history[-1],
            "lag_7": history[-7],
            "rolling_mean_7": np.mean(history[-7:])
        }])

        prediction = model.predict(features)[0]

        prediction = max(0, round(float(prediction), 2))

        forecasts.append({
            "date": next_date.strftime("%Y-%m-%d"),
            "predicted_demand": prediction
        })

        history.append(prediction)

    return {
        "status": "success",
        "history_days": len(data),
        "forecasts": forecasts,
        "total_predicted_demand": round(
            sum(item["predicted_demand"] for item in forecasts),
            2
        )
    }
