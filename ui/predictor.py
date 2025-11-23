#!/usr/bin/env python3
"""Tap temperature prediction model.

Uses linear regression to predict hot water tap temperature based on
tank temperature readings (lower and upper sensors).

The model learns from manually recorded tap temperature measurements
stored in the tap_readings table.
"""

import numpy as np
from typing import Optional, Dict, List
import db


class TapTempPredictor:
    """Predicts tap water temperature from tank sensor readings."""

    # Minimum number of readings required before making predictions
    MIN_SAMPLES = 5

    def __init__(self, db_path: str = None):
        self.db_path = db_path
        self.coefficients = None  # [intercept, coef_lower, coef_upper]
        self.r_squared = None
        self.sample_count = 0
        self._trained = False

    def train(self) -> bool:
        """Train the model on stored tap readings.

        Returns True if training was successful, False if insufficient data.
        """
        manager = db.DBManager(path=self.db_path) if self.db_path else db.DBManager()
        manager.connect()

        readings = manager.get_tap_readings()
        self.sample_count = len(readings)

        if self.sample_count < self.MIN_SAMPLES:
            self._trained = False
            return False

        # Prepare data for linear regression
        # X = [[1, tank_lower, tank_upper], ...] (1 for intercept)
        # y = [tap_temp, ...]
        X = []
        y = []

        for r in readings:
            if r['tank_lower'] is not None and r['tank_upper'] is not None:
                X.append([1.0, r['tank_lower'], r['tank_upper']])
                y.append(r['tap_temp'])

        if len(X) < self.MIN_SAMPLES:
            self._trained = False
            return False

        X = np.array(X)
        y = np.array(y)

        # Solve normal equations: coefficients = (X'X)^-1 X'y
        try:
            XtX = X.T @ X
            Xty = X.T @ y
            self.coefficients = np.linalg.solve(XtX, Xty)

            # Calculate R-squared
            y_pred = X @ self.coefficients
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            self.r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            self._trained = True
            return True
        except np.linalg.LinAlgError:
            self._trained = False
            return False

    def predict(self, tank_lower: float, tank_upper: float) -> Optional[float]:
        """Predict tap temperature from tank readings.

        Returns predicted temperature, or None if model not trained.
        """
        if not self._trained or self.coefficients is None:
            return None

        # prediction = intercept + coef_lower * tank_lower + coef_upper * tank_upper
        prediction = (
            self.coefficients[0] +
            self.coefficients[1] * tank_lower +
            self.coefficients[2] * tank_upper
        )

        # Clamp to reasonable range (0-100°C)
        return max(0.0, min(100.0, prediction))

    def get_stats(self) -> Dict:
        """Return model statistics."""
        return {
            'trained': self._trained,
            'sample_count': self.sample_count,
            'min_samples': self.MIN_SAMPLES,
            'r_squared': round(self.r_squared, 3) if self.r_squared is not None else None,
            'coefficients': {
                'intercept': round(self.coefficients[0], 3) if self.coefficients is not None else None,
                'tank_lower': round(self.coefficients[1], 3) if self.coefficients is not None else None,
                'tank_upper': round(self.coefficients[2], 3) if self.coefficients is not None else None,
            } if self.coefficients is not None else None
        }

    @property
    def is_trained(self) -> bool:
        return self._trained


# Global predictor instance (lazy-loaded)
_predictor: Optional[TapTempPredictor] = None


def get_predictor(db_path: str = None) -> TapTempPredictor:
    """Get or create the global predictor instance."""
    global _predictor
    if _predictor is None:
        _predictor = TapTempPredictor(db_path)
        _predictor.train()
    return _predictor


def retrain_predictor(db_path: str = None) -> TapTempPredictor:
    """Force retrain the predictor with latest data."""
    global _predictor
    _predictor = TapTempPredictor(db_path)
    _predictor.train()
    return _predictor
