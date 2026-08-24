# -*- coding: utf-8 -*-
"""Purged walk-forward calibration and the no-fake-probability publication gate."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Optional

MODEL_VERSION = "narrative-calibration-v1"
BOOTSTRAP_SEED = 17
FORBIDDEN_HISTORICAL_KEYS = {
    "probability",
    "direction",
    "verdict",
    "target",
    "forecast",
    "signal",
    "score",
}


@dataclass
class CalibrationResult:
    probability_status: str
    probability: Optional[float]
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    model_name: str
    model_version: str
    brier_skill: Optional[float]
    skill_ci_low: Optional[float]
    skill_ci_high: Optional[float]
    metrics: dict
    oos_predictions: list[float]

    def to_dict(self) -> dict:
        return {
            "probability_status": self.probability_status,
            "probability": self.probability if self.probability_status == "calibrated" else None,
            "lower_bound": self.lower_bound if self.probability_status == "calibrated" else None,
            "upper_bound": self.upper_bound if self.probability_status == "calibrated" else None,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "brier_skill": self.brier_skill,
            "skill_ci_low": self.skill_ci_low,
            "skill_ci_high": self.skill_ci_high,
            "metrics": self.metrics,
            "oos_predictions": self.oos_predictions,
        }


def _clip(value: float) -> float:
    return min(1 - 1e-6, max(1e-6, float(value)))


def brier_score(outcomes: list[int], probabilities: list[float]) -> float:
    if not outcomes or len(outcomes) != len(probabilities):
        raise ValueError("outcomes and probabilities must have equal non-zero length")
    return sum((_clip(p) - int(y)) ** 2 for y, p in zip(outcomes, probabilities)) / len(outcomes)


def prequential_baseline(outcomes: list[int]) -> list[float]:
    predictions = []
    positives = 1.0
    total = 2.0
    for outcome in outcomes:
        predictions.append(positives / total)
        positives += int(outcome)
        total += 1.0
    return predictions


def brier_skill(
    outcomes: list[int], probabilities: list[float], baseline: Optional[list[float]] = None
) -> float:
    base = baseline or prequential_baseline(outcomes)
    base_score = brier_score(outcomes, base)
    if base_score <= 1e-12:
        return 0.0
    return 1 - brier_score(outcomes, probabilities) / base_score


def bootstrap_skill_interval(
    outcomes: list[int],
    probabilities: list[float],
    baseline: list[float],
    *,
    confidence: float = 0.90,
    draws: int = 1000,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    if len(outcomes) < 2:
        return (-1.0, 1.0)
    rng = random.Random(seed)
    values: list[float] = []
    n = len(outcomes)
    for _ in range(max(100, draws)):
        indexes = [rng.randrange(n) for _ in range(n)]
        ys = [outcomes[i] for i in indexes]
        ps = [probabilities[i] for i in indexes]
        bs = [baseline[i] for i in indexes]
        base_score = brier_score(ys, bs)
        if base_score <= 1e-12:
            continue
        values.append(1 - brier_score(ys, ps) / base_score)
    if not values:
        return (-1.0, 1.0)
    values.sort()
    tail = (1 - confidence) / 2
    lo = values[min(len(values) - 1, int(tail * len(values)))]
    hi = values[min(len(values) - 1, int((1 - tail) * len(values)))]
    return lo, hi


def probability_interval(
    probability: float, effective_n: int, confidence_z: float = 1.6448536269514722
) -> tuple[float, float]:
    """Conservative normal interval with a Jeffreys-style effective sample adjustment."""
    p = _clip(probability)
    n = max(1, int(effective_n))
    half = confidence_z * math.sqrt((p * (1 - p) + 0.25 / n) / (n + 2))
    return max(0.0, p - half), min(1.0, p + half)


def _classification_metrics(outcomes: list[int], probabilities: list[float]) -> dict:
    positives = sum(outcomes)
    predicted = [1 if p >= 0.5 else 0 for p in probabilities]
    true_positive = sum(1 for y, p in zip(outcomes, predicted) if y == 1 and p == 1)
    false_positive = sum(1 for y, p in zip(outcomes, predicted) if y == 0 and p == 1)
    base_rate = positives / len(outcomes) if outcomes else 0.0
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, positives)
    negative_count = len(outcomes) - positives
    false_positive_rate = false_positive / max(1, negative_count)
    lift = precision / base_rate if base_rate > 0 else 0.0
    return {
        "base_rate": base_rate,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "lift": lift,
    }


def controls(outcomes: list[int]) -> dict:
    if not outcomes or len(set(outcomes)) < 2:
        return {"status": "invalid", "reason": "controls require both outcome classes"}
    positive = [0.9 if y else 0.1 for y in outcomes]
    rng = random.Random(BOOTSTRAP_SEED)
    negative = [rng.random() for _ in outcomes]
    pos_metrics = _classification_metrics(outcomes, positive)
    neg_metrics = _classification_metrics(outcomes, negative)
    return {
        "status": "ok",
        "positive": {
            **pos_metrics,
            "brier_skill": brier_skill(outcomes, positive),
        },
        "negative": {
            **neg_metrics,
            "brier_skill": brier_skill(outcomes, negative),
        },
        "passed": pos_metrics["lift"] > 1 and abs(neg_metrics["lift"] - 1) <= 0.75,
    }


def validate_historical_samples(samples: list[dict]) -> list[dict]:
    validated = []
    previous_as_of = ""
    for sample in sorted(samples, key=lambda row: str(row.get("as_of") or "")):
        as_of = str(sample.get("as_of") or "")
        outcome = sample.get("outcome")
        features = sample.get("features") or {}
        if not as_of or outcome not in (0, 1) or not isinstance(features, dict):
            raise ValueError("each sample needs as_of, binary outcome, and a feature object")
        banned = FORBIDDEN_HISTORICAL_KEYS.intersection(features)
        if banned:
            raise ValueError(f"historical feature pollution: {', '.join(sorted(banned))}")
        outcome_observed_at = str(sample.get("outcome_observed_at") or "")
        if not outcome_observed_at:
            raise ValueError("historical samples require outcome_observed_at")
        if outcome_observed_at <= as_of:
            raise ValueError(
                "outcome_observed_at must be later than the point-in-time feature cutoff"
            )
        if previous_as_of and as_of < previous_as_of:
            raise ValueError("samples must be sortable by point-in-time as_of")
        numeric = {}
        for key, value in features.items():
            if isinstance(value, bool):
                numeric[str(key)] = float(value)
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                numeric[str(key)] = float(value)
        validated.append({"as_of": as_of, "outcome": int(outcome), "features": numeric})
        previous_as_of = as_of
    return validated


def _feature_matrix(
    samples: list[dict], current_features: dict
) -> tuple[list[str], list[list[float]], list[float]]:
    names = sorted(
        {name for row in samples for name in row["features"]}
        | {str(k) for k, v in current_features.items() if isinstance(v, (int, float, bool))}
    )
    matrix = [[float(row["features"].get(name, float("nan"))) for name in names] for row in samples]
    current = [float(current_features.get(name, float("nan"))) for name in names]
    return names, matrix, current


def _base_candidate(outcomes: list[int]) -> tuple[list[float], float]:
    predictions = prequential_baseline(outcomes)
    current = (1 + sum(outcomes)) / (2 + len(outcomes))
    return predictions, current


def _sklearn_candidates(
    samples: list[dict],
    current_features: dict,
) -> list[tuple[str, list[int], list[float], float]]:
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return []
    outcomes = [row["outcome"] for row in samples]
    if len(samples) < 16 or len(set(outcomes)) < 2:
        return []
    _, matrix, current = _feature_matrix(samples, current_features)
    if not matrix or not matrix[0]:
        return []
    splits = min(5, max(2, len(samples) // 8))
    splitter = TimeSeriesSplit(n_splits=splits, gap=1)
    factories = (
        (
            "l2_logistic",
            lambda: make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                LogisticRegression(C=1.0, max_iter=2000, random_state=BOOTSTRAP_SEED),
            ),
        ),
        (
            "hist_gradient_boosting",
            lambda: make_pipeline(
                SimpleImputer(strategy="median"),
                HistGradientBoostingClassifier(
                    max_depth=3,
                    learning_rate=0.05,
                    max_iter=150,
                    random_state=BOOTSTRAP_SEED,
                ),
            ),
        ),
    )
    candidates = []
    for name, factory in factories:
        test_indexes: list[int] = []
        raw_predictions: list[float] = []
        failed = False
        for train_idx, test_idx in splitter.split(matrix):
            y_train = [outcomes[i] for i in train_idx]
            if len(set(y_train)) < 2:
                failed = True
                break
            model = factory()
            try:
                model.fit([matrix[i] for i in train_idx], y_train)
                fold = model.predict_proba([matrix[i] for i in test_idx])[:, 1]
            except Exception:
                failed = True
                break
            test_indexes.extend(int(i) for i in test_idx)
            raw_predictions.extend(float(p) for p in fold)
        if failed or len(raw_predictions) < 8:
            continue
        y_oos = [outcomes[i] for i in test_indexes]
        calibration_cut = max(4, int(len(raw_predictions) * 0.50))
        selection_cut = max(calibration_cut + 2, int(len(raw_predictions) * 0.75))
        if selection_cut >= len(raw_predictions) - 2 or len(set(y_oos[:calibration_cut])) < 2:
            continue
        calibration_options: list[tuple[str, list[float], Any]] = []
        try:
            platt = LogisticRegression(C=1.0, max_iter=1000, random_state=BOOTSTRAP_SEED)
            platt.fit(
                [[p] for p in raw_predictions[:calibration_cut]],
                y_oos[:calibration_cut],
            )
            calibrated = [
                float(p) for p in platt.predict_proba([[p] for p in raw_predictions])[:, 1]
            ]
            calibration_options.append(("platt", calibrated, platt))
        except Exception:
            pass
        try:
            isotonic = IsotonicRegression(out_of_bounds="clip")
            isotonic.fit(
                raw_predictions[:calibration_cut],
                y_oos[:calibration_cut],
            )
            calibrated = [float(p) for p in isotonic.predict(raw_predictions)]
            calibration_options.append(("isotonic", calibrated, isotonic))
        except Exception:
            pass
        if not calibration_options:
            continue
        calibration_options.sort(
            key=lambda item: brier_score(
                y_oos[calibration_cut:selection_cut],
                item[1][calibration_cut:selection_cut],
            )
        )
        calibrator_name, calibrated_oos, _ = calibration_options[0]
        final_model = factory()
        final_model.fit(matrix, outcomes)
        raw_current = float(final_model.predict_proba([current])[0][1])
        if calibrator_name == "platt":
            final_calibrator = LogisticRegression(C=1.0, max_iter=1000, random_state=BOOTSTRAP_SEED)
            final_calibrator.fit([[p] for p in raw_predictions], y_oos)
            current_p = float(final_calibrator.predict_proba([[raw_current]])[0][1])
        else:
            final_calibrator = IsotonicRegression(out_of_bounds="clip")
            final_calibrator.fit(raw_predictions, y_oos)
            current_p = float(final_calibrator.predict([raw_current])[0])
        candidates.append(
            (
                f"{name}+{calibrator_name}",
                test_indexes[selection_cut:],
                calibrated_oos[selection_cut:],
                current_p,
            )
        )
    return candidates


def calibrated_forecast(
    samples: list[dict], current_features: Optional[dict] = None
) -> CalibrationResult:
    """Choose from the pre-registered ladder and enforce the publication gate."""
    validated = validate_historical_samples(samples)
    current_features = current_features or {}
    if len(validated) < 2 or len({row["outcome"] for row in validated}) < 2:
        return CalibrationResult(
            "insufficient_data",
            None,
            None,
            None,
            "none",
            MODEL_VERSION,
            None,
            None,
            None,
            {
                "reason": "resolved point-in-time samples need both outcome classes",
                "llm_involvement": "none",
            },
            [],
        )
    outcomes = [row["outcome"] for row in validated]
    baseline_all, current_base = _base_candidate(outcomes)
    candidates: list[tuple[str, list[int], list[float], float]] = [
        ("smoothed_base_rate", list(range(len(outcomes))), baseline_all, current_base)
    ]
    candidates.extend(_sklearn_candidates(validated, current_features))
    scored = []
    for order, (name, indexes, probabilities, current_p) in enumerate(candidates):
        ys = [outcomes[i] for i in indexes]
        baseline = [baseline_all[i] for i in indexes]
        skill = brier_skill(ys, probabilities, baseline)
        ci_low, ci_high = bootstrap_skill_interval(ys, probabilities, baseline)
        scored.append(
            {
                "name": name,
                "order": order,
                "indexes": indexes,
                "outcomes": ys,
                "probabilities": probabilities,
                "current_probability": _clip(current_p),
                "brier": brier_score(ys, probabilities),
                "baseline_brier": brier_score(ys, baseline),
                "brier_skill": skill,
                "skill_ci_low": ci_low,
                "skill_ci_high": ci_high,
            }
        )
    scored.sort(key=lambda row: (-row["brier_skill"], row["order"]))
    chosen = scored[0]
    lower, upper = probability_interval(chosen["current_probability"], len(chosen["outcomes"]))
    control = controls(chosen["outcomes"])
    interval_width = upper - lower
    eligible = (
        chosen["skill_ci_low"] > 0 and interval_width <= 0.40 and control.get("passed") is True
    )
    metrics = {
        "gate": {
            "confidence": 0.90,
            "requires_skill_ci_low_above": 0.0,
            "max_probability_interval_width": 0.40,
            "passed": eligible,
        },
        "oos_n": len(chosen["outcomes"]),
        "brier": chosen["brier"],
        "baseline_brier": chosen["baseline_brier"],
        "brier_skill": chosen["brier_skill"],
        "skill_ci": [chosen["skill_ci_low"], chosen["skill_ci_high"]],
        "probability_interval_width": interval_width,
        "controls": control,
        "candidate_scores": [
            {"model": row["name"], "brier_skill": row["brier_skill"], "oos_n": len(row["outcomes"])}
            for row in scored
        ],
        "point_in_time": True,
        "purged_gap": 1,
        "llm_involvement": "none",
    }
    return CalibrationResult(
        "calibrated" if eligible else "insufficient_data",
        chosen["current_probability"] if eligible else None,
        lower if eligible else None,
        upper if eligible else None,
        chosen["name"],
        MODEL_VERSION,
        chosen["brier_skill"],
        chosen["skill_ci_low"],
        chosen["skill_ci_high"],
        metrics,
        chosen["probabilities"],
    )


def evaluate_published_forecasts(outcomes: list[int], probabilities: list[float]) -> dict:
    if len(outcomes) != len(probabilities) or not outcomes:
        return {"eligible": False, "reason": "no resolved calibrated forecasts"}
    baseline = prequential_baseline(outcomes)
    skill = brier_skill(outcomes, probabilities, baseline)
    lo, hi = bootstrap_skill_interval(outcomes, probabilities, baseline)
    control = controls(outcomes)
    return {
        "eligible": lo > 0 and control.get("passed") is True,
        "brier": brier_score(outcomes, probabilities),
        "baseline_brier": brier_score(outcomes, baseline),
        "brier_skill": skill,
        "skill_ci_90": [lo, hi],
        "classification": _classification_metrics(outcomes, probabilities),
        "controls": control,
        "llm_involvement": "none",
    }
