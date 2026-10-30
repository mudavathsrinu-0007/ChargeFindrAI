import os
import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ChargingRecords.csv")

def load_and_preprocess_data(csv_path=DATA_PATH, drop_duplicates=False):
    """
    Load Figshare EV charging transactions dataset (72,856 rows)
    and extract time-series features.

    Parameters:
      csv_path (str): Path to CSV dataset file.
      drop_duplicates (bool): If True, drops exact duplicate rows in memory (13 rows in raw dataset).
                              Defaults to False to preserve exact 58,284 training sample baseline.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset file not found at: {csv_path}")

    print(f"[PREPROCESS] Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"[PREPROCESS] Loaded raw records: {len(df):,} rows, {df.shape[1]} columns")

    # Fail fast on empty dataset
    if df.empty or len(df) == 0:
        raise ValueError(f"Dataset at {csv_path} is empty (0 records). Cannot perform preprocessing.")

    # Drop any null records in essential columns
    df = df.dropna(subset=["StartDatetime", "Demand"])

    if len(df) < 10:
        raise ValueError(f"Insufficient records in dataset ({len(df)} rows). At least 10 records required for time-series train/test split.")

    # Optional deduplication in memory (Option B: default False preserves baseline)
    if drop_duplicates:
        initial_count = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        dropped_count = initial_count - len(df)
        print(f"[PREPROCESS] Dropped {dropped_count} exact duplicate records in memory.")

    # Parse datetime
    df["StartDatetime"] = pd.to_datetime(df["StartDatetime"])

    # Chronological sort to respect time series order
    df = df.sort_values("StartDatetime").reset_index(drop=True)

    # Feature Engineering from timestamp
    df["hour"] = df["StartDatetime"].dt.hour
    df["day_of_week"] = df["StartDatetime"].dt.day_of_week
    df["is_weekend"] = df["day_of_week"].apply(lambda x: 1 if x >= 5 else 0)
    df["month"] = df["StartDatetime"].dt.month

    # Encode ChargerType (0 = Standard/AC, 1 = Fast DC)
    df["charger_type_code"] = df["ChargerType"].astype(int)

    # Chronological 80/20 train-test split BEFORE extracting location categories
    # (prevents data leakage from test split into feature selection)
    split_index = int(len(df) * 0.8)
    train_df = df.iloc[:split_index].copy()
    test_df = df.iloc[split_index:].copy()

    # Identify top 5 location categories from the training set only (preventing data leakage)
    top_locations_train = train_df["Location"].value_counts().nlargest(5).index.tolist()

    # Maintain canonical location feature column order compatible with existing trained models
    location_order = ["public area", "apartment", "resort", "hotel", "company"]
    top_locations = [loc for loc in location_order if loc in top_locations_train]
    for loc in top_locations_train:
        if loc not in top_locations:
            top_locations.append(loc)

    for loc in top_locations:
        clean_col = f"loc_{loc.replace(' ', '_')}"
        train_df[clean_col] = (train_df["Location"] == loc).astype(int)
        test_df[clean_col] = (test_df["Location"] == loc).astype(int)

    feature_cols = ["hour", "day_of_week", "is_weekend", "month", "charger_type_code"] + [
        f"loc_{loc.replace(' ', '_')}" for loc in top_locations
    ]

    target_col = "Demand"

    X_train = train_df[feature_cols]
    y_train = train_df[target_col]
    X_test = test_df[feature_cols]
    y_test = test_df[target_col]

    print(f"[PREPROCESS] Chronological split complete (top locations derived strictly from training set):")
    print(f"  Training set : {len(X_train):,} sessions ({train_df['StartDatetime'].min()} to {train_df['StartDatetime'].max()})")
    print(f"  Test set     : {len(X_test):,} sessions ({test_df['StartDatetime'].min()} to {test_df['StartDatetime'].max()})")

    return X_train, X_test, y_train, y_test, feature_cols

if __name__ == "__main__":
    X_train, X_test, y_train, y_test, features = load_and_preprocess_data()
    print("[SUCCESS] Preprocessing completed. Feature list:", features)

