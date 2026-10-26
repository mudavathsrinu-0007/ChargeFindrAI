import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Ensure ml package is in sys.path
ML_DIR = os.path.dirname(os.path.abspath(__file__))
if ML_DIR not in sys.path:
    sys.path.insert(0, ML_DIR)

from preprocess import load_and_preprocess_data

def run_diagnostics():
    print("=" * 70)
    print(" CHARGEFINDR AI - STAGE 4: MODEL DIAGNOSIS & VALIDATION")
    print("=" * 70)

    # 1. Dataset Inspection
    csv_path = os.path.join(ML_DIR, "ChargingRecords.csv")
    df = pd.read_csv(csv_path)
    print(f"\n[1. RAW DATASET INSPECTION]")
    print(f"  File Size      : {os.path.getsize(csv_path):,} bytes")
    print(f"  Shape          : {df.shape[0]:,} rows, {df.shape[1]} columns")
    print(f"  Columns        : {list(df.columns)}")
    print(f"  Missing values : {df.isnull().sum().to_dict()}")

    # Target variable distribution
    demand = df["Demand"]
    print(f"\n  Target Variable ('Demand' in kWh):")
    print(f"    Count        : {demand.count():,}")
    print(f"    Mean         : {demand.mean():.2f} kWh")
    print(f"    Std Dev      : {demand.std():.2f} kWh")
    print(f"    Median (50%) : {demand.median():.2f} kWh")
    print(f"    Min / Max    : {demand.min():.2f} kWh / {demand.max():.2f} kWh")
    print(f"    IQR (25-75%) : {demand.quantile(0.25):.2f} - {demand.quantile(0.75):.2f} kWh")
    print(f"    95th %ile    : {demand.quantile(0.95):.2f} kWh")
    print(f"    Skewness     : {demand.skew():.2f} (Positive right-skewed)")
    print(f"    Kurtosis     : {demand.kurtosis():.2f}")

    # Check correlation with Duration
    if "Duration" in df.columns:
        corr_dur = df["Duration"].corr(df["Demand"])
        print(f"    Correlation with Duration: {corr_dur:.4f} (Strong physical dependency)")

    # 2. Reproduce Chronological Split
    print(f"\n[2. CHRONOLOGICAL SPLIT REPRODUCTION]")
    X_train, X_test, y_train, y_test, feature_cols = load_and_preprocess_data()
    print(f"  Feature Columns ({len(feature_cols)}): {feature_cols}")
    print(f"  Train Set Size : {len(X_train):,} ({len(X_train)/len(df)*100:.2f}%)")
    print(f"  Test Set Size  : {len(X_test):,} ({len(X_test)/len(df)*100:.2f}%)")
    print(f"  Train Target   : Mean = {y_train.mean():.2f} kWh, Std = {y_train.std():.2f} kWh")
    print(f"  Test Target    : Mean = {y_test.mean():.2f} kWh, Std = {y_test.std():.2f} kWh")

    # 3. Model Artifact Evaluation (Reproduce exact metrics)
    print(f"\n[3. SAVED MODEL ARTIFACT REPRODUCTION]")
    model_path = os.path.join(ML_DIR, "demand_model.joblib")
    model = joblib.load(model_path)
    print(f"  Loaded Artifact: {model_path} ({os.path.getsize(model_path):,} bytes)")
    print(f"  Model Type     : {type(model).__name__}")
    print(f"  Parameters     : n_estimators={model.n_estimators}, max_depth={model.max_depth}, min_samples_leaf={model.min_samples_leaf}")

    y_pred = model.predict(X_test)
    model_mae = mean_absolute_error(y_test, y_pred)
    model_rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    model_r2 = r2_score(y_test, y_pred)

    print(f"  Measured Evaluation on Held-Out Test Set:")
    print(f"    MAE  : {model_mae:.4f} kWh")
    print(f"    RMSE : {model_rmse:.4f} kWh")
    print(f"    R2   : {model_r2:.4f}")

    # Check against model_metrics.json
    metrics_path = os.path.join(ML_DIR, "model_metrics.json")
    with open(metrics_path, "r") as f:
        stored_metrics = json.load(f)
    print(f"  Stored in JSON : MAE={stored_metrics['metrics']['MAE']}, RMSE={stored_metrics['metrics']['RMSE']}, R2={stored_metrics['metrics']['R2_Score']}")
    is_exact_match = (
        round(model_mae, 4) == stored_metrics['metrics']['MAE'] and
        round(model_rmse, 4) == stored_metrics['metrics']['RMSE'] and
        round(model_r2, 4) == stored_metrics['metrics']['R2_Score']
    )
    print(f"  Exact Match with Stored Artifacts: {is_exact_match}")

    # 4. Baseline Comparisons on Identical Held-Out Test Data
    print(f"\n[4. BASELINE BENCHMARKING ON IDENTICAL TEST DATA]")
    # Baseline 1: Global Mean Baseline (predict mean of training set)
    y_pred_mean = np.full_like(y_test, y_train.mean())
    b1_mae = mean_absolute_error(y_test, y_pred_mean)
    b1_rmse = np.sqrt(mean_squared_error(y_test, y_pred_mean))
    b1_r2 = r2_score(y_test, y_pred_mean)

    # Baseline 2: Global Median Baseline
    y_pred_median = np.full_like(y_test, y_train.median())
    b2_mae = mean_absolute_error(y_test, y_pred_median)
    b2_rmse = np.sqrt(mean_squared_error(y_test, y_pred_median))
    b2_r2 = r2_score(y_test, y_pred_median)

    # Baseline 3: Stratified Hourly Mean Baseline
    train_hourly_mean = y_train.groupby(X_train["hour"]).mean()
    y_pred_hourly = X_test["hour"].map(train_hourly_mean)
    b3_mae = mean_absolute_error(y_test, y_pred_hourly)
    b3_rmse = np.sqrt(mean_squared_error(y_test, y_pred_hourly))
    b3_r2 = r2_score(y_test, y_pred_hourly)

    # Baseline 4: Stratified (Hour + Charger Type) Mean Baseline
    train_strat = y_train.groupby([X_train["hour"], X_train["charger_type_code"]]).mean()
    test_idx = pd.MultiIndex.from_arrays([X_test["hour"], X_test["charger_type_code"]])
    y_pred_strat = test_idx.map(train_strat)
    b4_mae = mean_absolute_error(y_test, y_pred_strat)
    b4_rmse = np.sqrt(mean_squared_error(y_test, y_pred_strat))
    b4_r2 = r2_score(y_test, y_pred_strat)

    benchmarks = [
        ("Global Mean Baseline (y_train.mean)", b1_mae, b1_rmse, b1_r2),
        ("Global Median Baseline (y_train.median)", b2_mae, b2_rmse, b2_r2),
        ("Hourly Stratified Mean Baseline", b3_mae, b3_rmse, b3_r2),
        ("Hourly + ChargerType Stratified Mean", b4_mae, b4_rmse, b4_r2),
        ("Random Forest Regressor (Trained)", model_mae, model_rmse, model_r2),
    ]

    print(f"  {'Model / Baseline':<40} | {'MAE (kWh)':<10} | {'RMSE (kWh)':<10} | {'R2 Score':<10}")
    print("  " + "-" * 76)
    for name, mae, rmse, r2 in benchmarks:
        print(f"  {name:<40} | {mae:<10.2f} | {rmse:<10.2f} | {r2:<10.4f}")

    # 5. Feature Importances
    print(f"\n[5. RANDOM FOREST FEATURE IMPORTANCE ANALYSIS]")
    importances = model.feature_importances_
    feat_rank = sorted(zip(feature_cols, importances), key=lambda x: x[1], reverse=True)
    for feat, imp in feat_rank:
        print(f"  {feat:<22} : {imp*100:6.2f}%")

    # 6. Diagnosis Summary Object
    diag_summary = {
        "dataset_rows": int(len(df)),
        "dataset_cols": int(df.shape[1]),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "split_ratio": "80/20 Chronological",
        "model_performance": {
            "MAE": round(float(model_mae), 4),
            "RMSE": round(float(model_rmse), 4),
            "R2": round(float(model_r2), 4)
        },
        "mean_baseline": {
            "MAE": round(float(b1_mae), 4),
            "RMSE": round(float(b1_rmse), 4),
            "R2": round(float(b1_r2), 4)
        },
        "feature_importances": {feat: round(float(imp), 4) for feat, imp in feat_rank}
    }

    diag_out_path = os.path.join(ML_DIR, "diagnostic_report_output.json")
    with open(diag_out_path, "w") as f:
        json.dump(diag_summary, f, indent=2)
    print(f"\n[DIAGNOSTIC OUTPUT]")
    print(f"  Saved detailed diagnostic metrics to: {diag_out_path}")
    print("=" * 70)

if __name__ == "__main__":
    run_diagnostics()

