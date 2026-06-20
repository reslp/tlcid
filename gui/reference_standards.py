"""Predefined reference-standard configuration for TLCid."""

from dataclasses import dataclass

from PyQt6.QtGui import QColor


@dataclass(frozen=True, slots=True)
class ReferenceStandard:
    sample_id: int
    name: str
    button_attr: str
    button_text: str
    inactive_text: str
    active_text: str
    color_name: str
    rf_by_plate: dict[int, float]

    @property
    def sample_name(self) -> str:
        return f"{self.name} (Ref)"

    @property
    def rf_values(self) -> list[float | None]:
        return [self.rf_by_plate.get(idx) for idx in range(3)]

    def color(self) -> QColor:
        return QColor(self.color_name)


REFERENCE_STANDARDS: dict[int, ReferenceStandard] = {
    0: ReferenceStandard(
        sample_id=0,
        name="Atranorin",
        button_attr="mark_atranorin_button",
        button_text="Atranorin",
        inactive_text="Atranorin",
        active_text="Stop Ref (Atr)",
        color_name="red",
        rf_by_plate={0: 0.76, 1: 0.73, 2: 0.79},
    ),
    -1: ReferenceStandard(
        sample_id=-1,
        name="Norstictic Acid",
        button_attr="mark_norstictic_button",
        button_text="Norstictic Acid",
        inactive_text="Norstictic",
        active_text="Stop Ref (Nor)",
        color_name="gold",
        rf_by_plate={0: 0.40, 1: 0.32, 2: 0.30},
    ),
    -2: ReferenceStandard(
        sample_id=-2,
        name="Rhizocarpic Acid",
        button_attr="mark_rhizocarpic_button",
        button_text="Rhizocarpic Acid",
        inactive_text="Rhizocarpic Acid",
        active_text="Stop Ref (Rhi)",
        color_name="orange",
        rf_by_plate={0: 0.67, 1: 0.41, 2: 0.65},
    ),
    -3: ReferenceStandard(
        sample_id=-3,
        name="Lecanoric Acid",
        button_attr="mark_lecanoric_button",
        button_text="Lecanoric Acid",
        inactive_text="Lecanoric Acid",
        active_text="Stop Ref (Lec)",
        color_name="limegreen",
        rf_by_plate={0: 0.28, 1: 0.44, 2: 0.22},
    ),
    -4: ReferenceStandard(
        sample_id=-4,
        name="Evernic Acid",
        button_attr="mark_evernic_button",
        button_text="Evernic Acid",
        inactive_text="Evernic Acid",
        active_text="Stop Ref (Eve)",
        color_name="magenta",
        rf_by_plate={0: 0.38, 1: 0.60, 2: 0.43},
    ),
}

REFERENCE_STANDARD_IDS = frozenset(REFERENCE_STANDARDS)


def get_reference_standard(sample_id: int) -> ReferenceStandard | None:
    return REFERENCE_STANDARDS.get(sample_id)


def predefined_reference_rf_values() -> dict[int, list[float | None]]:
    return {sample_id: standard.rf_values for sample_id, standard in REFERENCE_STANDARDS.items()}


def reference_standard_name_for_rf_value(rf_value: float) -> str | None:
    for standard in REFERENCE_STANDARDS.values():
        if rf_value in standard.rf_by_plate.values():
            return standard.name
    return None
