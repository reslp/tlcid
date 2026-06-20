"""Pure calibration helpers for TLCid Rf values."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

CALIBRATION_MODE_LINEAR = "Linear interpolation"
CALIBRATION_MODE_NEAREST = "Nearest Reference"

StandardPoint = tuple[float, float]
StandardNameResolver = Callable[[float], str]


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    raw: float
    corrected: float
    mode: str
    used_standards: tuple[str, ...]


def normalize_calibration_mode(mode: str | None) -> str:
    if mode == "Nearest reference":
        return CALIBRATION_MODE_NEAREST
    if mode in (CALIBRATION_MODE_LINEAR, CALIBRATION_MODE_NEAREST):
        return mode
    return CALIBRATION_MODE_LINEAR


def correct_rf(raw_rf: float, standards: Sequence[StandardPoint], mode: str | None = None) -> float:
    corrected_val = raw_rf
    mode = normalize_calibration_mode(mode)

    if mode == CALIBRATION_MODE_LINEAR:
        points = [(0.0, 0.0), *standards, (1.0, 1.0)]
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            if x1 <= raw_rf <= x2:
                if abs(x2 - x1) > 1e-7:
                    corrected_val = y1 + (raw_rf - x1) * (y2 - y1) / (x2 - x1)
                else:
                    corrected_val = y1
                break
    elif standards:
        closest_std = None
        min_dist = float("inf")
        for obs_rf, std_rf in standards:
            dist = abs(raw_rf - obs_rf)
            if dist < min_dist:
                min_dist = dist
                closest_std = (obs_rf, std_rf)

        if closest_std:
            obs_rf, std_rf = closest_std
            if obs_rf > 1e-7:
                correction_factor = std_rf / obs_rf
                corrected_val = raw_rf * correction_factor
                corrected_val = max(0.0, min(1.0, corrected_val))

    return corrected_val


def support_line_raw_rf(corrected_rf: float, standards: Sequence[StandardPoint], mode: str | None = None) -> float:
    if not standards:
        return corrected_rf

    mode = normalize_calibration_mode(mode)
    if mode == CALIBRATION_MODE_LINEAR:
        points = [(0.0, 0.0), *standards, (1.0, 1.0)]
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            lo = min(y1, y2)
            hi = max(y1, y2)
            if lo <= corrected_rf <= hi:
                if abs(y2 - y1) > 1e-7:
                    return x1 + (corrected_rf - y1) * (x2 - x1) / (y2 - y1)
                return x1
        return corrected_rf

    closest_std = None
    min_dist = float("inf")
    for obs_rf, std_rf in standards:
        dist = abs(corrected_rf - std_rf)
        if dist < min_dist:
            min_dist = dist
            closest_std = (obs_rf, std_rf)

    if closest_std:
        obs_rf, std_rf = closest_std
        if std_rf > 1e-7:
            raw_rf = corrected_rf * (obs_rf / std_rf)
            return max(0.0, min(1.0, raw_rf))

    return corrected_rf


def calibrate_spot(
    raw_rf: float,
    standards: Sequence[StandardPoint],
    mode: str | None,
    standard_name_for_rf: StandardNameResolver,
) -> CalibrationResult:
    mode = normalize_calibration_mode(mode)
    corrected = correct_rf(raw_rf, standards, mode)
    used_standards: list[str] = []

    if mode == CALIBRATION_MODE_LINEAR:
        points = [(0.0, 0.0), *standards, (1.0, 1.0)]
        for j in range(len(points) - 1):
            x1, _y1 = points[j]
            x2, _y2 = points[j + 1]
            if x1 <= raw_rf <= x2:
                for standard in standards:
                    if standard == points[j]:
                        used_standards.append(standard_name_for_rf(standard[1]))
                    if standard == points[j + 1]:
                        used_standards.append(standard_name_for_rf(standard[1]))
                break
    elif standards:
        closest_std = None
        min_dist = float("inf")
        for obs_rf, std_rf in standards:
            dist = abs(raw_rf - obs_rf)
            if dist < min_dist:
                min_dist = dist
                closest_std = (obs_rf, std_rf)
        if closest_std:
            used_standards.append(standard_name_for_rf(closest_std[1]))

    return CalibrationResult(
        raw=raw_rf,
        corrected=corrected,
        mode=mode,
        used_standards=tuple(used_standards),
    )
