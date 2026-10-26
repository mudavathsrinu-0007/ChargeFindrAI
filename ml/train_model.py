import os
import sys
import json
import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Ensure ml package is resolvable
ML_DIR = os.path.dirname(os.path.abspath(__file__))
if ML_DIR not in sys.path:
    sys.path.insert(0, ML_DIR)

from preprocess import load_and_preprocess_data

MODEL_SAVE_PATH = os.path.join(ML_DIR, "demand_model.joblib")
METRICS_SAVE_PATH = os.path.join(ML_DIR, "model_metrics.json")

def train_and_evaluate():
    """
    Train Random Forest Regressor on chronological EV charging transactions
    and save trained model and evaluation metrics.
    """
    print("==================================================")
    print(" ChargeFindr AI - Demand Prediction Model Training")
    print("==================================================")

    # 1. Load and chronologically split data
    X_train, X_test, y_train, y_test, feature_cols = load_and_preprocess_data()

    # 2. Initialize Random Forest Regressor
    print("\n[MODEL] Training RandomForestRegressor (n_estimators=100, max_depth=12)...")
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)
    print("[MODEL] Training complete.")

    # 3. Evaluate strictly on chronologically held-out test data
    print("\n[EVALUATION] Evaluating model on chronological test set...")
    y_pred = model.predict(X_test)

    mae = float(mean_absolute_error(y_test, y_pred))
    mse = float(mean_squared_error(y_test, y_pred))
    rmse = float(np.sqrt(mse))
    r2 = float(r2_score(y_test, y_pred))

    metrics = {
        "model_type": "RandomForestRegressor",
        "dataset": "Figshare EV Charging Transactions (72,856 records)",
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "feature_columns": feature_cols,
        "metrics": {
            "MAE": round(mae, 4),
            "RMSE": round(rmse, 4),
            "R2_Score": round(r2, 4)
        },
        "target_variable": "Demand (kWh)"
    }

    print("\n----------------- Performance Metrics -----------------")
    print(f" Mean Absolute Error (MAE)     : {mae:.2f} kWh")
    print(f" Root Mean Squared Error (RMSE): {rmse:.2f} kWh")
    print(f" Coefficient of Det. (R2)      : {r2:.4f}")
    print("-------------------------------------------------------")

    # 4. Save trained model artifact and metrics
    joblib.dump(model, MODEL_SAVE_PATH)
    with open(METRICS_SAVE_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"[SAVE] Model saved to   : {MODEL_SAVE_PATH}")
    print(f"[SAVE] Metrics saved to : {METRICS_SAVE_PATH}")
    print("==================================================")
    return metrics

if __name__ == "__main__":
    train_and_evaluate()

