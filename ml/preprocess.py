import os
import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChargingRecords.csv")

def load_and_preprocess_data(csv_path=DATA_PATH):
    """
    Load Figshare EV charging transactions dataset (72,856 rows)
    and extract time-series features.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset file not found at: {csv_path}")

    print(f"[PREPROCESS] Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"[PREPROCESS] Loaded raw records: {len(df):,} rows, {df.shape[1]} columns")

    # Drop any null records in essential columns
    df = df.dropna(subset=["StartDatetime", "Demand"])

    # Parse datetime
    df["StartDatetime"] = pd.to_datetime(df["StartDatetime"])

    # Chronological sort to respect time series order
    df = df.sort_values("StartDatetime").reset_index(drop=True)

    # Feature Engineering from timestamp
    df["hour"] = df["StartDatetime"].dt.hour
    df["day_of_week"] = df["StartDatetime"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].apply(lambda x: 1 if x >= 5 else 0)
    df["month"] = df["StartDatetime"].dt.month

    # Encode ChargerType (0 = Standard/AC, 1 = Fast DC)
    df["charger_type_code"] = df["ChargerType"].astype(int)

    # One-hot encode top location types to preserve generalizability
    top_locations = df["Location"].value_counts().nlargest(5).index.tolist()
    for loc in top_locations:
        clean_col = f"loc_{loc.replace(' ', '_')}"
        df[clean_col] = (df["Location"] == loc).astype(int)

    feature_cols = ["hour", "day_of_week", "is_weekend", "month", "charger_type_code"] + [
        f"loc_{loc.replace(' ', '_')}" for loc in top_locations
    ]

    target_col = "Demand"

    # Chronological 80/20 train-test split (avoiding future data leakage)
    split_index = int(len(df) * 0.8)
    train_df = df.iloc[:split_index]
    test_df = df.iloc[split_index:]

    X_train = train_df[feature_cols]
    y_train = train_df[target_col]
    X_test = test_df[feature_cols]
    y_test = test_df[target_col]

    print(f"[PREPROCESS] Chronological split complete:")
    print(f"  Training set : {len(X_train):,} sessions ({train_df['StartDatetime'].min()} to {train_df['StartDatetime'].max()})")
    print(f"  Test set     : {len(X_test):,} sessions ({test_df['StartDatetime'].min()} to {test_df['StartDatetime'].max()})")

    return X_train, X_test, y_train, y_test, feature_cols

if __name__ == "__main__":
    X_train, X_test, y_train, y_test, features = load_and_preprocess_data()
    print("[SUCCESS] Preprocessing completed. Feature list:", features)

