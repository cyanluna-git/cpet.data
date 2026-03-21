"""
pipeline — Reusable CPET analysis pipeline.

Extracts, parses, and analyzes COSMED K5 breath-by-breath data
alongside FIT, ZWO, and lactate sources into a unified SQLite database
with automated analysis and HTML report generation.

Canonical parser source: hong.changsun/analysis/parsers.py
"""

from pipeline.parsers import parse_workspace

__all__ = ["parse_workspace"]
