"""Present cross-table findings using source cells, never guessed coordinates."""

from __future__ import annotations

import math
from typing import Any


MAX_COMPARISON_PAIRS = 100


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _positive_int(value: Any) -> int | None:
    numeric = _number(value)
    return int(numeric) if numeric is not None and numeric > 0 and numeric.is_integer() else None


def _source(item: dict[str, Any], side: str, tables: dict) -> tuple[str, str, dict]:
    filename = str(item.get(f"file_{side}") or item.get("file") or "")
    sheet = str(item.get(f"sheet_{side}") or item.get("sheet") or "")
    prefix = filename + "::"
    if sheet.startswith(prefix):
        sheet = sheet[len(prefix):]
    # No single-sheet fallback: a named sheet must resolve to that exact source.
    file_sheets = tables.get(filename) or {}
    table = file_sheets.get(sheet) or {}
    return filename, sheet, table if isinstance(table, dict) else {}


def _cell(source: tuple[str, str, dict], row_idx: Any, column_idx: Any) -> dict | None:
    row_number, column_number = _positive_int(row_idx), _positive_int(column_idx)
    if row_number is None or column_number is None:
        return None
    filename, sheet, table = source
    rows = [row for row in table.get("rows", []) if isinstance(row, dict)
            and row.get("row_idx") == row_number]
    if len(rows) != 1:
        return None
    values = rows[0].get("values") or []
    if column_number > len(values):
        return None
    headers = table.get("headers") or []
    label = headers[column_number - 1] if column_number <= len(headers) else None
    return {
        "file": filename, "sheet": sheet, "row_idx": row_number,
        "column": str(label) if label not in (None, "") else f"第 {column_number} 列",
        "value": values[column_number - 1],
    }


def _matches(value: Any, expected: Any, digits: int = 9) -> bool:
    left, right = _number(value), _number(expected)
    return left is not None and right is not None and round(left, digits) == round(right, digits)


def _coordinate_pairs(item: dict, sources: tuple, same_position: bool) -> list[dict]:
    pairs = []
    seen = set()
    for example in item.get("examples") or []:
        if not isinstance(example, dict):
            continue
        if same_position:
            row_a = row_b = example.get("row")
            col_a = col_b = example.get("col")
            expected_a = expected_b = example.get("value")
        else:
            row_a, col_a = example.get("row_a"), example.get("col_a")
            row_b, col_b = example.get("row_b"), example.get("col_b")
            expected_a, expected_b = example.get("value_a"), example.get("value_b")
        left, right = _cell(sources[0], row_a, col_a), _cell(sources[1], row_b, col_b)
        identity = (row_a, col_a, row_b, col_b)
        if (left is None or right is None or identity in seen
                or not _matches(left["value"], expected_a)
                or not _matches(right["value"], expected_b)):
            continue
        seen.add(identity)
        pairs.append({"left": left, "right": right})
        if len(pairs) >= MAX_COMPARISON_PAIRS:
            break
    return pairs


def _column_cells(source: tuple[str, str, dict], label: Any) -> list[dict] | None:
    table = source[2]
    matching_columns = [index + 1 for index, header in enumerate(table.get("headers") or [])
                        if str(header) == str(label)]
    if label in (None, "") or len(matching_columns) != 1:
        return None
    cells = []
    seen_rows = set()
    column = matching_columns[0]
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        row_idx = _positive_int(row.get("row_idx"))
        values = row.get("values") or []
        if row_idx is None or column > len(values) or _number(values[column - 1]) is None:
            continue
        if row_idx in seen_rows:
            return None
        seen_rows.add(row_idx)
        cells.append({
            "file": source[0], "sheet": source[1], "row_idx": row_idx,
            "column": str(label), "value": values[column - 1],
        })
    return sorted(cells, key=lambda cell: cell["row_idx"])


def _column_pairs(item: dict, sources: tuple, count: int) -> list[dict]:
    left = _column_cells(sources[0], item.get("col_a"))
    right = _column_cells(sources[1], item.get("col_b"))
    # Engine examples have values only. Locate them only after validating the
    # unique columns and their entire numeric sequences, including the count.
    if not left or not right or len(left) != count or len(right) != count:
        return []
    if not all(_matches(a["value"], b["value"], 6) for a, b in zip(left, right)):
        return []
    examples = item.get("examples") or []
    if any(not isinstance(example, dict) or index >= count
           or not _matches(left[index]["value"], example.get("value"), 6)
           for index, example in enumerate(examples)):
        return []
    return [{"left": a, "right": b} for a, b in zip(left[:MAX_COMPARISON_PAIRS], right)]


def normalise_cross_finding(item: dict[str, Any], index: int, file_tables: dict) -> dict[str, Any]:
    """Normalize a PaperConan finding with exact, independently checked sources."""
    kind = str(item.get("kind") or "cross_sheet")
    sources = (_source(item, "a", file_tables), _source(item, "b", file_tables))
    labels = [f"{filename or '未提供文件名'} · {sheet or '未提供工作表名'}"
              for filename, sheet, _ in sources]
    location = f"{labels[0]} ↔ {labels[1]}"
    count = next((_positive_int(item.get(key)) for key in (
        "same_position_count", "shared_value_count", "tail_match_count", "n_occurrences", "run_length"
    ) if _positive_int(item.get(key)) is not None), 0)
    columns = [str(item[key]) for key in ("col_a", "col_b") if item.get(key) not in (None, "")]
    pairs: list[dict] = []
    fallback = "该结果未提供可确认的行列位置，请在两份原始材料中核对。"
    if kind == "cross_sheet_position_identical":
        title = "跨表相同位置重复"
        summary = f"两表相同行列的 {count} 个数值在保留 9 位小数后相同。"
        pairs = _coordinate_pairs(item, sources, same_position=True)
    elif kind == "cross_sheet_column_duplicate":
        title = "跨表整列重复"
        summary = f"“{item.get('col_a', '')}”与“{item.get('col_b', '')}”两列的 {count} 个数值按顺序保留 6 位小数后相同。"
        pairs = _column_pairs(item, sources, count)
        fallback = "未能在原始材料中唯一确认两列及其完整数值顺序，请核对表头和数据范围。"
    elif kind == "cross_sheet_decimal_tail_reuse":
        title = "跨表小数尾数重复"
        summary = f"两表有 {count} 对数值的完整值不同，小数末尾存在相同片段。"
        pairs = _coordinate_pairs(item, sources, same_position=False)
    elif kind == "cross_sheet_value_overlap":
        title = "跨表出现相同数值"
        summary = f"两表共有 {count} 个不同数值相同；所在位置可能不同。"
        fallback = "该项比较的是两表出现过的数值，未提供逐格位置，也不能据此认定实验数据一一对应。请核对原始材料。"
    else:
        titles = {
            "scaled_row_reuse": "跨表行数据固定倍数", "identical_row_reuse": "跨表行数据重复",
            "recurring_row_vector": "多处数据片段重复", "within_row_repeated_segment": "行内数据片段重复",
            "within_table_fraction_reuse": "表内小数部分重复", "short_row_reuse": "行数据片段重复",
            "within_row_shared_fraction": "行内小数部分相同", "shared_fraction_row_pair": "两行小数部分相同",
        }
        title = titles.get(kind, "表格间数据关系待核对")
        summary = f"发现“{title}”的情况，涉及 {count} 处。" if count else f"发现“{title}”的情况。"
    if pairs:
        note = (f"已展示 {len(pairs)} / {count} 对命中数值，均取自原始文件。"
                if len(pairs) < count else f"已展示全部 {len(pairs)} 对命中数值，均取自原始文件。")
        if kind == "cross_sheet_column_duplicate":
            note += "按列内数值顺序比对，不代表相同实验对象。"
    else:
        note = fallback
    return {
        "id": f"FD-{index:04d}", "kind": kind, "category": "cross_sheet",
        "severity": str(item.get("severity") or item.get("raw_severity") or "info").lower(),
        "location": location, "file": " ↔ ".join(dict.fromkeys(source[0] for source in sources)),
        "sheet": " ↔ ".join(dict.fromkeys(source[1] for source in sources)),
        "columns": columns, "n": count, "rule": summary,
        "title_cn": title, "summary_cn": summary,
        "why_cn": "需结合两份材料的实验分组、单位和图注，确认是否为共享数据或已说明的计算关系。",
        "next_steps": ["核对两侧原始数值及实验分组。", "确认是否属于共享对照、重复展示或已说明的换算。"],
        "profile_action": str(item.get("profile_action") or "kept"),
        "likely_benign": "请核对是否已在材料中说明共享数据或计算关系。" if item.get("likely_benign") else "",
        "evidence_note_cn": note,
        "evidence": {"headers": [], "rows": [], "highlight_cols": [], "highlight_rows": [],
                     "focus_cells": [], "comparison": pairs, "note_cn": note,
                     "comparison_total": count, "comparison_shown": len(pairs),
                     "truncated": None},
        "raw": item,
    }
