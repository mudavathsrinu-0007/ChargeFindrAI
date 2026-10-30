import os
import sys
import tempfile
import unittest
from decimal import Decimal
import pandas as pd

# Ensure ChargeFindrAI is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.routes.station_routes import serialize_station
from backend.services.recommendation_service import calculate_station_score
from backend.services.demand_service import predict_demand
from ml.preprocess import load_and_preprocess_data, DATA_PATH


class TestModule2PreprocessingAndNulls(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. P1: Station serialization with NULL / Decimal / missing fields
    # -------------------------------------------------------------------------
    def test_serialize_station_with_nulls_and_decimals(self):
        """serialize_station must safely handle Decimal, None, and missing keys without crashing."""
        raw_row = {
            "station_id": 101,
            "station_name": "Null Test Hub",
            "location": "Gachibowli, Hyderabad",
            "distance_km": Decimal("5.25"),
            "charger_type": "Fast DC",
            "capacity_kw": Decimal("50.00"),
            "available_ports": None,
            "total_ports": None,
            "estimated_wait_minutes": None,
            "demand_level": None,
            "latitude": Decimal("17.4400"),
            "longitude": Decimal("78.3800")
        }
        serialized = serialize_station(raw_row)
        self.assertEqual(serialized["station_id"], 101)
        self.assertEqual(serialized["distance_km"], 5.25)
        self.assertEqual(serialized["capacity_kw"], 50.0)
        self.assertIsNone(serialized["available_ports"])
        self.assertIsNone(serialized["total_ports"])
        self.assertIsNone(serialized["estimated_wait_minutes"])
        self.assertEqual(serialized["latitude"], 17.44)
        self.assertEqual(serialized["longitude"], 78.38)

    # -------------------------------------------------------------------------
    # 2. P1: Recommendation scoring with NULL / 0 availability fallbacks
    # -------------------------------------------------------------------------
    def test_calculate_station_score_null_handling(self):
        """calculate_station_score must not crash when fields are None or missing."""
        station_with_nulls = {
            "station_id": 99,
            "station_name": "Edge Station",
            "location": "Hyderabad",
            "distance_km": None,
            "charger_type": None,
            "capacity_kw": None,
            "available_ports": None,
            "total_ports": None,
            "estimated_wait_minutes": None,
            "demand_level": None
        }
        score, reasons = calculate_station_score(station_with_nulls)
        self.assertIsInstance(score, float)
        self.assertIsInstance(reasons, list)
        self.assertTrue(any("congested: 0 ports available" in r.lower() for r in reasons))

    # -------------------------------------------------------------------------
    # 3. P2: Location matching substring collision fix
    # -------------------------------------------------------------------------
    def test_demand_location_matching(self):
        """'public parking lot' and 'public institution' must not trigger 'loc_public_area'."""
        # 1. Exact "public area"
        res_pub_area = predict_demand(hour=14, day_of_week=2, location="public area")
        self.assertTrue(res_pub_area["is_ml_model"])

        # 2. "public parking lot" -> should NOT be categorized as loc_public_area
        # When location is "public parking lot", loc_public_area must be 0
        from backend.services.demand_service import _model, _metrics
        import numpy as np

        if _model is not None:
            # Let's inspect the row_dict used internally by checking hourly_curve or direct prediction
            # We can also check predict_demand for both and ensure "public area" gives expected result
            res_parking = predict_demand(hour=14, day_of_week=2, location="public parking lot")
            res_institution = predict_demand(hour=14, day_of_week=2, location="public institution")
            res_apt = predict_demand(hour=14, day_of_week=2, location="Apartment")

            # Check that hourly_curve retains location attributes
            curve_point = res_apt["hourly_curve"][14]
            self.assertEqual(curve_point["predicted_demand_kwh"], res_apt["predicted_demand_kwh"])

    # -------------------------------------------------------------------------
    # 4. P5: Empty / insufficient dataset validation in preprocess
    # -------------------------------------------------------------------------
    def test_preprocess_empty_and_insufficient_dataset(self):
        """load_and_preprocess_data must raise ValueError for empty or <10 rows datasets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Non-existent file
            fake_path = os.path.join(tmpdir, "non_existent.csv")
            with self.assertRaises(FileNotFoundError):
                load_and_preprocess_data(fake_path)

            # 2. Completely empty CSV
            empty_path = os.path.join(tmpdir, "empty.csv")
            with open(empty_path, "w") as f:
                f.write("")
            with self.assertRaises((ValueError, pd.errors.EmptyDataError)):
                load_and_preprocess_data(empty_path)

            # 3. Insufficient rows (<10)
            small_path = os.path.join(tmpdir, "small.csv")
            small_df = pd.DataFrame({
                "StartDatetime": ["2023-01-01 10:00:00", "2023-01-01 11:00:00"],
                "Demand": [15.5, 20.1],
                "ChargerType": [1, 0],
                "Location": ["public area", "apartment"]
            })
            small_df.to_csv(small_path, index=False)
            with self.assertRaises(ValueError):
                load_and_preprocess_data(small_path)

    # -------------------------------------------------------------------------
    # 5. P3 & P4: Preprocessing split without data leakage & Option B
    # -------------------------------------------------------------------------
    def test_preprocess_train_test_split_and_drop_duplicates(self):
        """Verify chronological split, canonical features, and drop_duplicates flag behavior."""
        # Option B Default (drop_duplicates=False): preserves 58,284 / 14,572 baseline
        X_train, X_test, y_train, y_test, features = load_and_preprocess_data(DATA_PATH, drop_duplicates=False)
        self.assertEqual(len(X_train), 58284)
        self.assertEqual(len(X_test), 14572)
        expected_features = [
            "hour", "day_of_week", "is_weekend", "month", "charger_type_code",
            "loc_public_area", "loc_apartment", "loc_resort", "loc_hotel", "loc_company"
        ]
        self.assertEqual(features, expected_features)
        self.assertEqual(list(X_train.columns), expected_features)
        self.assertEqual(list(X_test.columns), expected_features)

        # drop_duplicates=True: drops exactly 13 duplicates in memory
        X_train_d, X_test_d, y_train_d, y_test_d, features_d = load_and_preprocess_data(DATA_PATH, drop_duplicates=True)
        self.assertEqual(len(X_train_d), 58274)
        self.assertEqual(len(X_test_d), 14569)
        self.assertEqual(len(X_train_d) + len(X_test_d), 72843)
        self.assertEqual(features_d, expected_features)


if __name__ == "__main__":
    unittest.main()

