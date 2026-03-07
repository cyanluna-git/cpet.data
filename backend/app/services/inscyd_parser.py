"""Parser for INSCYD PDF reports."""

from dataclasses import dataclass, field
from datetime import datetime, date
import re
from typing import Any, Optional

from pypdf import PdfReader


@dataclass
class ParsedInscydReport:
    external_test_id: Optional[str] = None
    report_date: Optional[date] = None
    sport: Optional[str] = None
    test_type: Optional[str] = None
    athlete_name: Optional[str] = None
    coach_name: Optional[str] = None
    body_mass_kg: Optional[float] = None
    body_height_cm: Optional[float] = None
    body_mass_index: Optional[float] = None
    projected_bsa_m2: Optional[float] = None
    body_fat_percent: Optional[float] = None
    body_fat_kg: Optional[float] = None
    fat_free_percent: Optional[float] = None
    fat_free_kg: Optional[float] = None
    vo2max_abs_ml_min: Optional[float] = None
    vo2max_rel_ml_kg_min: Optional[float] = None
    vlamax_mmol_l_s: Optional[float] = None
    mfo_abs_kcal_h: Optional[float] = None
    mfo_rel_kcal_h_kg: Optional[float] = None
    fatmax_watt: Optional[float] = None
    carbmax_abs_watt: Optional[float] = None
    carbmax_rel_w_kg: Optional[float] = None
    at_abs_watt: Optional[float] = None
    at_rel_w_kg: Optional[float] = None
    at_pct_vo2max: Optional[float] = None
    glycogen_abs_g: Optional[float] = None
    glycogen_rel_g_kg: Optional[float] = None
    hr_max_bpm: Optional[int] = None
    pwc150_watt: Optional[float] = None
    training_zones: list[dict[str, Any]] = field(default_factory=list)
    test_data_rows: list[dict[str, Any]] = field(default_factory=list)
    weighted_regression: dict[str, Any] = field(default_factory=dict)
    raw_sections: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    parsing_warnings: list[str] = field(default_factory=list)


class InscydParser:
    """Extract structured metrics from INSCYD PDF reports."""

    def parse_file(self, file_path: str) -> ParsedInscydReport:
        reader = PdfReader(file_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        compact = self._compact(text)

        report = ParsedInscydReport(raw_text=text)
        report.external_test_id = self._extract_text(compact, r"Test Id\s+([A-Za-z0-9_-]+)")
        report.report_date = self._extract_date(compact, r"Date\s+(\d{2}\.\d{2}\.\d{4})")
        report.sport = self._extract_text(compact, r"Sport\s+(.+?)\s+Test Type")
        report.test_type = self._extract_text(compact, r"Test Type\s+(.+?)\s+Athlete")
        report.athlete_name = self._extract_text(compact, r"Athlete\s+(.+?)\s+Coach")
        report.coach_name = self._extract_text(compact, r"Coach\s+(.+?)\s+Body Composition")

        report.body_mass_kg = self._extract_float(compact, r"Body Mass\s+([0-9.]+)\s*kg")
        report.body_height_cm = self._extract_float(
            compact, r"Body Height\s+([0-9.]+)\s*cm"
        )
        report.body_mass_index = self._extract_float(
            compact, r"Body Mass Index\s+([0-9.]+)\s*kg/m2"
        )
        report.projected_bsa_m2 = self._extract_float(
            compact, r"Projected BSA\s+([0-9.]+)\s*m2"
        )
        report.body_fat_percent = self._extract_float(
            compact, r"Body Fat\s+([0-9.]+)\s*% of body mass /"
        )
        report.body_fat_kg = self._extract_float(
            compact, r"Body Fat\s+[0-9.]+\s*% of body mass /\s*([0-9.]+)\s*kg"
        )
        report.fat_free_percent = self._extract_float(
            compact, r"Fat Free\s+([0-9.]+)\s*% of body mass /"
        )
        report.fat_free_kg = self._extract_float(
            compact, r"Fat Free\s+[0-9.]+\s*% of body mass /\s*([0-9.]+)\s*kg"
        )

        benchmark_block = self._extract_section(
            compact,
            "Physiological Performance Benchmarks",
            "Load Characteristics",
        )
        report.raw_sections["benchmarks"] = benchmark_block

        report.vo2max_abs_ml_min = self._extract_float(
            benchmark_block, r"Absolute:\s*([0-9.]+)\s*ml/min"
        )
        report.vo2max_rel_ml_kg_min = self._extract_float(
            benchmark_block, r"Relative:\s*([0-9.]+)\s*ml/min/kg"
        )
        report.vlamax_mmol_l_s = self._extract_float(
            benchmark_block, r"VLamax:\s*([0-9.]+)\s*mmol/l/s"
        )
        report.mfo_abs_kcal_h = self._extract_float(
            benchmark_block, r"MFO Absolute:\s*([0-9.]+)\s*kcal/h"
        )
        report.mfo_rel_kcal_h_kg = self._extract_float(
            benchmark_block, r"MFO Relative:\s*([0-9.]+)\s*kcal/h/kg"
        )
        report.fatmax_watt = self._extract_float(
            benchmark_block, r"Fatmax:\s*([0-9.]+)\s*Watt"
        )
        report.at_pct_vo2max = self._extract_float(
            benchmark_block, r"%VO2max:\s*([0-9.]+)\s*%"
        )
        report.glycogen_abs_g = self._extract_float(
            benchmark_block, r"Absolute:\s*([0-9.]+)\s*g"
        )
        report.glycogen_rel_g_kg = self._extract_float(
            benchmark_block, r"Relative:\s*([0-9.]+)\s*g/kg"
        )
        report.hr_max_bpm = self._extract_int(
            benchmark_block, r"Maximum:\s*([0-9.]+)\s*bpm"
        )
        report.pwc150_watt = self._extract_float(
            benchmark_block, r"PWC150:\s*([0-9.]+)\s*Watt"
        )

        absolute_watts = self._extract_all_floats(
            benchmark_block, r"Absolute:\s*([0-9.]+)\s*Watt"
        )
        relative_watts = self._extract_all_floats(
            benchmark_block, r"Relative:\s*([0-9.]+)\s*Watt/kg"
        )
        if absolute_watts:
            report.at_abs_watt = absolute_watts[0]
        if len(absolute_watts) > 1:
            report.carbmax_abs_watt = absolute_watts[1]
        if relative_watts:
            report.at_rel_w_kg = relative_watts[0]
        if len(relative_watts) > 1:
            report.carbmax_rel_w_kg = relative_watts[1]

        zones_block = self._extract_section(compact, "Training Zones", None)
        report.raw_sections["training_zones"] = zones_block
        report.training_zones = self._parse_training_zones(zones_block)

        test_tables_block = self._extract_section(
            compact,
            "Test Data - tables",
            "Training Zones",
        )
        report.raw_sections["test_data_tables"] = test_tables_block
        report.test_data_rows = self._parse_test_data_rows(test_tables_block)
        report.weighted_regression = self._parse_weighted_regression(test_tables_block)

        if not report.training_zones:
            report.parsing_warnings.append("Training zones could not be extracted")
        if report.vo2max_rel_ml_kg_min is None:
            report.parsing_warnings.append("VO2max metrics could not be extracted")

        return report

    def _compact(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _extract_text(self, text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip()

    def _extract_float(self, text: str, pattern: str) -> Optional[float]:
        value = self._extract_text(text, pattern)
        if value is None:
            return None
        return float(value)

    def _extract_int(self, text: str, pattern: str) -> Optional[int]:
        value = self._extract_float(text, pattern)
        if value is None:
            return None
        return int(round(value))

    def _extract_all_floats(self, text: str, pattern: str) -> list[float]:
        return [float(value) for value in re.findall(pattern, text, re.IGNORECASE)]

    def _extract_date(self, text: str, pattern: str) -> Optional[date]:
        value = self._extract_text(text, pattern)
        if not value:
            return None
        return datetime.strptime(value, "%d.%m.%Y").date()

    def _extract_section(
        self,
        text: str,
        start_marker: str,
        end_marker: Optional[str],
    ) -> str:
        if end_marker:
            match = re.search(
                rf"{re.escape(start_marker)}\s+(.*?)\s+{re.escape(end_marker)}",
                text,
                re.IGNORECASE,
            )
        else:
            match = re.search(
                rf"{re.escape(start_marker)}\s+(.*)$",
                text,
                re.IGNORECASE,
            )
        return match.group(1).strip() if match else ""

    def _parse_training_zones(self, text: str) -> list[dict[str, Any]]:
        zones: list[dict[str, Any]] = []
        if not text:
            return zones

        chunks = re.findall(r"Zone\s+(\d+)\s+(.*?)(?=Zone\s+\d+|$)", text, re.IGNORECASE)
        for zone_number, payload in chunks:
            tokens = payload.split()
            code_index = None
            for index, token in enumerate(tokens):
                next_token = tokens[index + 1] if index + 1 < len(tokens) else None
                if len(token) <= 5 and re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", token):
                    if next_token is None or re.fullmatch(r"[0-9.]+", next_token):
                        code_index = index
                        break

            if code_index is None:
                name_tokens = tokens
                code = None
                numeric_tokens: list[str] = []
            else:
                name_tokens = tokens[:code_index]
                code = tokens[code_index]
                numeric_tokens = tokens[code_index + 1 :]

            def get_float(index: int) -> Optional[float]:
                if index >= len(numeric_tokens):
                    return None
                return float(numeric_tokens[index])

            zones.append(
                {
                    "zone_number": int(zone_number),
                    "name": " ".join(name_tokens).strip(),
                    "code": code,
                    "lower_watt": get_float(0),
                    "upper_watt": get_float(1),
                    "target_watt": get_float(2),
                    "energy_kcal_h": get_float(3),
                    "fat_percent": get_float(4),
                    "carbohydrate_percent": get_float(5),
                    "fat_g_h": get_float(6),
                    "carbohydrate_g_h": get_float(7),
                }
            )

        return zones

    def _parse_test_data_rows(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not text:
            return rows

        match = re.search(
            r"Type Average Power Duration Additional Value\s+(.*?)\s+Weighted Regression",
            text,
            re.IGNORECASE,
        )
        if not match:
            return rows

        body = match.group(1).strip()
        for line in re.split(r"\s*(?=Power Duration|VO2 Max)\s*", body):
            line = line.strip()
            if not line:
                continue
            row_match = re.match(
                r"(.+?)\s+([0-9.]+)W\s+([0-9]+)(?:\s+(.+))?$",
                line,
                re.IGNORECASE,
            )
            if not row_match:
                continue
            rows.append(
                {
                    "type": row_match.group(1).strip(),
                    "average_power_watt": float(row_match.group(2)),
                    "duration_sec": int(row_match.group(3)),
                    "additional_value": (
                        row_match.group(4).strip() if row_match.group(4) else None
                    ),
                }
            )

        return rows

    def _parse_weighted_regression(self, text: str) -> dict[str, Any]:
        match = re.search(
            r"Weighted Regression\s+VLamax VO2max Anaerobic Threshold\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)",
            text,
            re.IGNORECASE,
        )
        if not match:
            return {}
        return {
            "vlamax": float(match.group(1)),
            "vo2max": float(match.group(2)),
            "anaerobic_threshold": float(match.group(3)),
        }

