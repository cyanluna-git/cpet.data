"""
pipeline.parsers.lactate — Lactate data parser (.md + .xlsx).

Parses lactate/glucose blood sample data from either Markdown tables
or LT workbook XLSX format.

Canonical source: hong.changsun/analysis/parsers.py
"""

import re
from pathlib import Path
from typing import Any

import pandas as pd


def parse_lactate(
    *,
    md_path: Path | None = None,
    xlsx_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse lactate data from Markdown or XLSX source.

    Exactly one of md_path or xlsx_path must be provided.

    Args:
        md_path: Path to lactate_data.md file.
        xlsx_path: Path to LT workbook XLSX file.

    Returns:
        Tuple of (blood_df, subject_info dict).
    """
    if md_path is not None:
        return _parse_lactate_md(Path(md_path))
    if xlsx_path is not None:
        return _parse_lactate_xlsx(Path(xlsx_path))
    raise ValueError("Either md_path or xlsx_path must be provided")


def _parse_lactate_md(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse lactate Markdown tables."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # --- Subject info table ---
    subject_info: dict[str, Any] = {}
    info_match = re.findall(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|", content)
    for field, value in info_match:
        field = field.strip()
        value = value.strip()
        if field in ("Field", "---"):
            continue
        subject_info[field] = value

    # --- Parse blood sample tables ---
    samples: list[dict[str, Any]] = []
    current_block = ""

    def _parse_val(s: str) -> float | None:
        s = s.strip()
        if s in ("\u2014", "", "n/a"):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def _parse_str(s: str) -> str | None:
        s = s.strip()
        return None if s in ("\u2014", "") else s

    for line in content.split("\n"):
        block_match = re.match(r"## Block (\d+)", line)
        if block_match:
            if "Rest" in line:
                current_block = "rest"
            elif "LT1" in line:
                current_block = "block_1"
            elif "VO2max" in line:
                current_block = "block_2"
            elif "Clearance" in line:
                current_block = "block_3"
            continue

        if not line.startswith("|") or "---" in line or "Step" in line:
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells or len(cells) < 4:
            continue

        if current_block == "block_3":
            if len(cells) >= 9:
                samples.append(
                    {
                        "block": current_block,
                        "step": _parse_str(cells[0]),
                        "ftp_pct": _parse_str(cells[1]),
                        "load_w": _parse_val(cells[2]),
                        "duration_min": _parse_val(cells[3]),
                        "kst_time": _parse_str(cells[4]),
                        "hr_bpm": _parse_val(cells[5]),
                        "lactate_mmol": _parse_val(cells[6]),
                        "glucose_mmol": _parse_val(cells[7]),
                        "notes": _parse_str(cells[8]) if len(cells) > 8 else None,
                    }
                )
        else:
            if len(cells) >= 7:
                samples.append(
                    {
                        "block": current_block,
                        "step": _parse_str(cells[0]),
                        "ftp_pct": None,
                        "load_w": _parse_val(cells[1]),
                        "duration_min": (
                            _parse_val(cells[2]) if cells[2] not in ("n/a",) else None
                        ),
                        "kst_time": _parse_str(cells[3]),
                        "hr_bpm": _parse_val(cells[4]),
                        "lactate_mmol": _parse_val(cells[5]),
                        "glucose_mmol": _parse_val(cells[6]),
                        "notes": _parse_str(cells[7]) if len(cells) > 7 else None,
                    }
                )

    blood_df = pd.DataFrame(samples)
    return blood_df, subject_info


def _parse_lactate_xlsx(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse lactate data from LT workbook XLSX format."""
    lt_xl = pd.ExcelFile(str(path))
    subject_sheet = None
    for sheet_name in lt_xl.sheet_names:
        preview = lt_xl.parse(sheet_name, header=None, nrows=2)
        first_cell = (
            str(preview.iat[0, 0]).strip().lower() if not preview.empty else ""
        )
        second_cell = (
            str(preview.iat[0, 1]).strip().lower() if preview.shape[1] > 1 else ""
        )
        if "load" in second_cell and first_cell not in {"prt", "nan"}:
            subject_sheet = sheet_name
            break
    if subject_sheet is None:
        raise ValueError(f"Could not find subject LT sheet in {path.name}")

    subject_df = lt_xl.parse(subject_sheet, header=None)
    prt_df = (
        lt_xl.parse("Prt", header=None)
        if "Prt" in lt_xl.sheet_names
        else pd.DataFrame()
    )

    samples: list[dict[str, Any]] = []
    for row_idx in range(1, len(subject_df)):
        row = subject_df.iloc[row_idx].tolist()
        step_index = int(row[0])
        load_w = float(row[1]) if pd.notna(row[1]) else None
        duration_min = float(row[2]) if pd.notna(row[2]) else None
        hr_bpm = float(row[3]) if pd.notna(row[3]) else None
        lactate = float(row[4]) if pd.notna(row[4]) else None
        glucose = float(row[5]) if pd.notna(row[5]) else None
        notes = (
            str(row[6]).strip() if len(row) > 6 and pd.notna(row[6]) else None
        )

        if step_index == 0:
            block = "rest"
            step = "0"
            ftp_pct = None
        elif notes == "CPET":
            block = "block_2"
            step = "2-1"
            ftp_pct = None
        elif step_index < 5:
            block = "block_1"
            step = f"1-{step_index}"
            ftp_pct = None
        else:
            block = "block_3"
            b3_idx = step_index - 4
            step = f"3-{b3_idx}"
            ftp_lookup_row = 18 + b3_idx
            ftp_raw = (
                prt_df.iat[ftp_lookup_row, 1]
                if not prt_df.empty and ftp_lookup_row < len(prt_df)
                else None
            )
            ftp_pct = (
                f"{round(float(ftp_raw) * 100):.0f}%"
                if pd.notna(ftp_raw)
                else None
            )

        samples.append(
            {
                "block": block,
                "step": step,
                "ftp_pct": ftp_pct,
                "load_w": load_w,
                "duration_min": duration_min,
                "kst_time": None,
                "hr_bpm": hr_bpm,
                "lactate_mmol": lactate,
                "glucose_mmol": glucose,
                "notes": notes,
            }
        )

    blood_df = pd.DataFrame(samples)
    ftp_candidates: list[float] = []
    for _, row in blood_df[blood_df["block"] == "block_3"].iterrows():
        ftp_pct = row.get("ftp_pct")
        load_w = row.get("load_w")
        if not ftp_pct or load_w is None:
            continue
        ftp_ratio = float(str(ftp_pct).rstrip("%")) / 100.0
        if ftp_ratio > 0:
            ftp_candidates.append(float(load_w) / ftp_ratio)
    ftp_est = (
        round(pd.Series(ftp_candidates).median() / 5.0) * 5
        if ftp_candidates
        else None
    )
    subject_info = {
        "Name": subject_sheet,
        "FTP": str(int(ftp_est)) if ftp_est else "",
        "Max HR": str(
            int(
                max(v for v in blood_df["hr_bpm"].dropna())
                if not blood_df["hr_bpm"].dropna().empty
                else 0
            )
        ),
    }
    return blood_df, subject_info
