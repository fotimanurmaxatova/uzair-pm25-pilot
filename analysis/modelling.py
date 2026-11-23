"""Feature sets, preprocessing and model specifications (decisions 0009 and 0010, issue #15).

Fixed here, before any model is fitted; nothing is tuned.  Preprocessing order follows 0010 items 6 to 8:
  1. missing feature values -> training-fold median (cyclic sin/cos included; targets are never imputed)
  2. continuous features clipped to the training-fold 1st and 99th percentiles (numpy default linear method)
     (one-hot city and cyclic sin/cos are not clipped)
  3. Ridge only: continuous features standardised with the training-fold mean and standard deviation
     (a zero standard deviation is replaced by 1; one-hot city and cyclic features are not scaled)
Winsorising bounds and scaling statistics are computed on the imputed training values.
Every statistic is learned from the training rows passed to `fit`, never from validation or test rows.
"""
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

CITIES = ["Tashkent", "Samarkand", "Bukhara", "Andijan", "Namangan", "Fergana", "Nukus", "Urgench"]

_WEATHER_CONT = ["temperature_2m", "relative_humidity_2m", "precipitation_mm", "wind_speed_ms",
                 "surface_pressure_hpa", "pressure_change_3h"]
_WEATHER_CYC = ["wind_dir_sin", "wind_dir_cos"]
_BASE_CONT = ["pm2_5", "pm25_lag3", "pm25_lag6", "nitrogen_dioxide"]
_BASE_CYC = ["hour_sin", "hour_cos"]

FEATURE_SETS = {
    "full": {"continuous": _BASE_CONT + _WEATHER_CONT, "cyclic": _BASE_CYC + _WEATHER_CYC},
    "noweather": {"continuous": list(_BASE_CONT), "cyclic": list(_BASE_CYC)},
}
TARGET = "target_pm25_t6"

# Grid fixed by the protocol and decision 0009.
RIDGE_ALPHAS = (0.1, 1, 10, 100)
HGB_DEPTHS = (3, 5)
HGB_RATES = (0.05, 0.1)
HGB_FIXED = dict(max_iter=100, min_samples_leaf=5, l2_regularization=0.0, early_stopping=False, random_state=0)


class PreprocessError(RuntimeError):
    pass


def candidates():
    out = [{"model": "ridge", "alpha": a} for a in RIDGE_ALPHAS]
    out += [{"model": "hgb", "max_depth": d, "learning_rate": lr} for d in HGB_DEPTHS for lr in HGB_RATES]
    return out


def candidate_id(spec):
    if spec["model"] == "ridge":
        return f"ridge_alpha{spec['alpha']}"
    return f"hgb_depth{spec['max_depth']}_lr{spec['learning_rate']}"


def tie_key(spec):
    """Smaller is simpler (0009): Ridge before HGB; larger alpha; smaller max_depth, then smaller learning_rate."""
    if spec["model"] == "ridge":
        return (0, -spec["alpha"], 0)
    return (1, spec["max_depth"], spec["learning_rate"])


def make_estimator(spec):
    if spec["model"] == "ridge":
        return Ridge(alpha=spec["alpha"], fit_intercept=True)
    return HistGradientBoostingRegressor(max_depth=spec["max_depth"], learning_rate=spec["learning_rate"],
                                         **HGB_FIXED)


def _col(rows, name):
    return np.array([np.nan if r[name] is None else float(r[name]) for r in rows], dtype=float)


class Preprocessor:
    def __init__(self, feature_set, scale, cities=None):
        self.cont = FEATURE_SETS[feature_set]["continuous"]
        self.cyc = FEATURE_SETS[feature_set]["cyclic"]
        self.scale = scale
        self.cities = list(cities) if cities is not None else list(CITIES)    # one-hot columns (LOCO: seven cities)
        self.fitted = False

    def fit(self, rows):
        if not rows:
            raise PreprocessError("no training rows")
        self.median, self.lo, self.hi, self.mean, self.std = {}, {}, {}, {}, {}
        for name in self.cont + self.cyc:
            x = _col(rows, name)
            if np.isnan(x).all():
                raise PreprocessError(f"feature {name} has no observed training value")
            self.median[name] = float(np.nanmedian(x))
            x = np.where(np.isnan(x), self.median[name], x)
            if name in self.cont:
                self.lo[name], self.hi[name] = (float(v) for v in np.percentile(x, [1, 99]))
                x = np.clip(x, self.lo[name], self.hi[name])
                self.mean[name] = float(x.mean())
                sd = float(x.std(ddof=0))
                self.std[name] = sd if sd > 0 else 1.0
        self.fitted = True
        return self

    def transform(self, rows, allow_unknown_city=False):
        """allow_unknown_city: a city without its own column is encoded as all zeros (leave-one-city-out only)."""
        if not self.fitted:
            raise PreprocessError("preprocessor is not fitted")
        cols = []
        for name in self.cont:
            x = _col(rows, name)
            x = np.where(np.isnan(x), self.median[name], x)
            x = np.clip(x, self.lo[name], self.hi[name])
            cols.append((x - self.mean[name]) / self.std[name] if self.scale else x)
        for name in self.cyc:
            x = _col(rows, name)
            cols.append(np.where(np.isnan(x), self.median[name], x))
        for city in self.cities:
            cols.append(np.array([1.0 if r["city"] == city else 0.0 for r in rows]))
        unknown = {r["city"] for r in rows} - set(CITIES if allow_unknown_city else self.cities)
        if unknown:
            raise PreprocessError(f"unknown city: {sorted(unknown)}")
        return np.column_stack(cols)

    def state(self):
        return {"continuous": self.cont, "cyclic": self.cyc, "scale": self.scale, "median": self.median,
                "winsor_low": self.lo, "winsor_high": self.hi, "mean": self.mean, "std": self.std,
                "cities": self.cities}


def targets(rows):
    y = _col(rows, TARGET)
    if np.isnan(y).any():
        raise PreprocessError("a training or validation target is missing")
    return y


def fit_model(spec, feature_set, train_rows):
    pre = Preprocessor(feature_set, scale=(spec["model"] == "ridge")).fit(train_rows)
    est = make_estimator(spec).fit(pre.transform(train_rows), targets(train_rows))
    return pre, est


def predict(pre, est, rows):
    return est.predict(pre.transform(rows))


def rmse(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.sqrt(np.mean((y - p) ** 2)))


def persistence(rows):
    """Forecast for t+6 h = PM2.5 observed at t in the same city.  Not tuned."""
    return np.array([float(r["pm2_5"]) for r in rows])
