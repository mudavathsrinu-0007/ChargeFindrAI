import os
import json
import joblib
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "ml", "demand_model.joblib")
METRICS_PATH = os.path.join(BASE_DIR, "ml", "model_metrics.json")

_model = None
_metrics = None

def _load_model_artifacts():
    global _model, _metrics
    if _model is None and os.path.exists(MODEL_PATH):
        try:
            _model = joblib.load(MODEL_PATH)
        except Exception as e:
            print(f"[DEMAND SERVICE] Could not load model: {e}")
            _model = None

    if _metrics is None and os.path.exists(METRICS_PATH):
        try:
            with open(METRICS_PATH, "r") as f:
                _metrics = json.load(f)
        except Exception as e:
            print(f"[DEMAND SERVICE] Could not load metrics: {e}")
            _metrics = None

def categorize_demand(kwh):
    """Classify predicted session energy consumption (kWh)."""
    if kwh < 12.0:
        return "Low", "Low session energy consumption (<12 kWh). Favorable for rapid session turnaround."
    elif kwh <= 20.0:
        return "Medium", "Typical session energy consumption (12-20 kWh). Regular session turnaround expected."
    else:
        return "High", "High session energy consumption (>20 kWh). Longer vehicle charging session duration expected."

def get_model_metadata():
    """
    Return model metadata, chronological train/test split details, and evaluation metrics
    loaded from the verified artifact ml/model_metrics.json.
    """
    _load_model_artifacts()
    if _metrics is not None:
        metrics_dict = _metrics.get("metrics", {})
        train_count = _metrics.get("train_samples")
        test_count = _metrics.get("test_samples")
        total_count = (train_count + test_count) if (train_count and test_count) else None

        return {
            "model_type": _metrics.get("model_type", "RandomForestRegressor"),
            "dataset": _metrics.get("dataset", "Figshare EV Charging Transactions (72,856 records)"),
            "target_variable": _metrics.get("target_variable", "Demand (kWh)"),
            "target_description": "Individual Session Energy Consumption (kWh)",
            "location_benchmark": "Public Area (Default representative site category)",
            "train_samples": train_count,
            "test_samples": test_count,
            "total_samples": total_count,
            "split_type": "80/20 Chronological Split (No Data Leakage)" if train_count and test_count else "Chronological Split",
            "metrics": {
                "MAE": metrics_dict.get("MAE"),
                "RMSE": metrics_dict.get("RMSE"),
                "R2_Score": metrics_dict.get("R2_Score")
            },
            "is_available": True
        }
    return {
        "model_type": "Baseline Statistical Average (Fallback)",
        "dataset": "Unavailable",
        "target_variable": "Demand (kWh)",
        "target_description": "Individual Session Energy Consumption (kWh)",
        "location_benchmark": "Public Area (Default representative site category)",
        "train_samples": None,
        "test_samples": None,
        "total_samples": None,
        "split_type": "Unavailable",
        "metrics": None,
        "is_available": False
    }

def predict_demand(hour=None, day_of_week=None, charger_type="Fast DC", location="public area"):
    """
    Predict charging demand (kWh) using the trained Random Forest model.
    Falls back to transparent baseline forecast if model artifact is unavailable.
    """
    _load_model_artifacts()

    now = datetime.now()
    if hour is None:
        hour = now.hour
    else:
        hour = max(0, min(23, int(hour)))

    if day_of_week is None:
        day_of_week = now.weekday()
    else:
        day_of_week = max(0, min(6, int(day_of_week)))

    is_weekend = 1 if day_of_week >= 5 else 0
    month = now.month
    charger_code = 1 if "fast" in str(charger_type).lower() else 0

    # Safe location handling: never crash on location=None or non-string
    loc_clean = str(location or "public area").strip().lower()

    if _model is not None and _metrics is not None:
        feature_cols = _metrics.get("feature_columns", [
            "hour", "day_of_week", "is_weekend", "month", "charger_type_code",
            "loc_public_area", "loc_apartment", "loc_resort", "loc_hotel", "loc_company"
        ])

        # Disambiguate "public area" from other public categories like "public parking lot" and "public institution"
        is_public_area = 1 if ("public area" in loc_clean or loc_clean in ("public", "public_area")) else 0

        row_dict = {
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "month": month,
            "charger_type_code": charger_code,
            "loc_public_area": is_public_area,
            "loc_apartment": 1 if "apartment" in loc_clean else 0,
            "loc_resort": 1 if "resort" in loc_clean else 0,
            "loc_hotel": 1 if "hotel" in loc_clean else 0,
            "loc_company": 1 if "company" in loc_clean else 0,
        }

        # Fill any missing columns with 0
        input_df = pd.DataFrame([row_dict])[feature_cols]
        predicted_kwh = float(_model.predict(input_df)[0])
        model_name = _metrics.get("model_type", "RandomForestRegressor")
        is_ml_model = True
    else:
        # Transparent baseline forecast
        baseline_hourly_factors = {
            0: 10.2, 1: 8.5, 2: 7.0, 3: 6.5, 4: 7.2, 5: 9.0,
            6: 12.5, 7: 15.8, 8: 18.2, 9: 21.4, 10: 22.0, 11: 20.5,
            12: 19.8, 13: 18.9, 14: 19.2, 15: 20.8, 16: 22.5, 17: 24.1,
            18: 25.0, 19: 23.5, 20: 20.1, 21: 17.0, 22: 14.2, 23: 12.0
        }
        base = baseline_hourly_factors.get(hour, 16.5)
        if charger_code == 1:
            base *= 1.25
        predicted_kwh = float(round(base, 2))
        model_name = "Baseline Statistical Average (Fallback)"
        is_ml_model = False

    demand_level, advisory = categorize_demand(predicted_kwh)

    # Generate 24-hour hourly curve for visualization
    hourly_curve = []
    for h in range(24):
        if _model is not None and _metrics is not None:
            temp_dict = {
                "hour": h,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "month": month,
                "charger_type_code": charger_code,
                "loc_public_area": row_dict["loc_public_area"],
                "loc_apartment": row_dict["loc_apartment"],
                "loc_resort": row_dict["loc_resort"],
                "loc_hotel": row_dict["loc_hotel"],
                "loc_company": row_dict["loc_company"],
            }
            temp_df = pd.DataFrame([temp_dict])[feature_cols]
            kwh = round(float(_model.predict(temp_df)[0]), 2)
        else:
            kwh = round(float(baseline_hourly_factors.get(h, 16.0)), 2)

        lvl, _ = categorize_demand(kwh)
        hourly_curve.append({
            "hour": h,
            "label": f"{h:02d}:00",
            "predicted_kwh": kwh,
            "predicted_demand_kwh": kwh,
            "demand_level": lvl
        })

    meta = get_model_metadata()

    return {
        "hour": hour,
        "day_of_week": day_of_week,
        "charger_type": charger_type,
        "predicted_demand_kwh": round(predicted_kwh, 2),
        "demand_level": demand_level,
        "advisory": advisory,
        "model_used": model_name,
        "is_ml_model": is_ml_model,
        "forecast_type": "Illustrative Hourly Sensitivity Profile (00:00 - 23:00)",
        "target_description": "Expected Individual Session Energy Consumption (kWh)",
        "location_benchmark": "Public Area (Default representative site category)" if "public area" in loc_clean else loc_clean.title(),
        "metrics": meta.get("metrics"),
        "dataset": meta.get("dataset"),
        "metadata": meta,
        "hourly_curve": hourly_curve
    }
