"""Prediction scoring for TLCid reference substances."""

from __future__ import annotations

from typing import Any


class PredictionService:
    """Scores observed plate Rf values against loaded reference data."""

    def __init__(self):
        self.reference_data: list[dict[str, Any]] = []
        self.genus_to_substances: dict[str, set[str]] = {}
        self.family_to_substances: dict[str, set[str]] = {}
        self.reference_rf_by_name: dict[str, list[float | None]] = {}

    def load_bundle(self, bundle) -> None:
        self.reference_data = bundle.reference_data
        self.genus_to_substances = bundle.genus_to_substances
        self.family_to_substances = bundle.family_to_substances
        self.reference_rf_by_name = bundle.reference_rf_by_name

    def predict(
        self,
        input_data,
        *,
        detection_method,
        detection_range,
        plate_ranges,
        filter_group=None,
        filter_genus=None,
        filter_family=None,
        filter_vis=False,
        filter_uvs=False,
        filter_uvl=False,
        filter_aft_vis=None,
        filter_aft_uv=None,
        allow_missing_rf_values=False,
    ):
        scores = []

        for item in self.reference_data:
            name = item['name']

            if filter_group and item.get('GroupName') != filter_group:
                continue

            if filter_genus:
                valid_subs = self.genus_to_substances.get(filter_genus, set())
                if name.lower() not in valid_subs:
                    continue

            if filter_family:
                valid_subs = self.family_to_substances.get(filter_family, set())
                if name.lower() not in valid_subs:
                    continue

            if filter_vis and item.get('BefVis') != '+':
                continue
            if filter_uvs and item.get('BefUVS') != '+':
                continue
            if filter_uvl and item.get('BefUVL') != '+':
                continue

            if filter_aft_vis and item.get('AftVis') != filter_aft_vis:
                continue
            if filter_aft_uv and item.get('AftUV') != filter_aft_uv:
                continue

            match = True
            dist = 0.0
            count = 0

            for plate_idx, obs_val in input_data.items():
                if plate_idx >= len(item['rf']):
                    continue

                ref_val = item['rf'][plate_idx]
                if ref_val is None:
                    if allow_missing_rf_values:
                        continue
                    match = False
                    break

                error = abs(obs_val - ref_val)
                if detection_method == "Range":
                    plate_range = plate_ranges.get(plate_idx, detection_range)
                    if error > plate_range:
                        match = False
                        break

                dist += error ** 2
                count += 1

            if match and count > 0:
                scores.append((dist / count, name))

        scores.sort(key=lambda x: x[0])

        unique_matches = []
        seen = set()
        for score, name in scores:
            if name not in seen:
                unique_matches.append((score, name))
                seen.add(name)

        return unique_matches
