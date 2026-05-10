from html import escape

import pandas as pd
import streamlit as st


TABLE_CSS = """
<style>
.sd-table-card {
    background: #ffffff;
    border: 1.5px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 2px 6px rgba(15,23,42,0.06);
    overflow: hidden;
    margin-top: 0.25rem;
}

.sd-table-scroll {
    overflow: auto;
    background: #ffffff;
}

.sd-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    color: #0f172a;
}

.sd-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    color: #475569;
    font-size: 0.72rem;
    font-weight: 800;
    padding: 0.72rem 0.78rem;
    text-align: left;
    white-space: nowrap;
}

.sd-table tbody td {
    border-top: 1px solid #eef2f7;
    color: #334155;
    font-size: 0.78rem;
    line-height: 1.55;
    padding: 0.78rem;
    vertical-align: top;
    overflow-wrap: anywhere;
}

.sd-table tbody tr:first-child td {
    border-top: 0;
}

.sd-table tbody tr:hover td {
    background: #f8fafc;
}

.sd-table .sd-table-right {
    text-align: right;
}

.sd-table .sd-table-nowrap {
    white-space: nowrap;
    overflow-wrap: normal;
}

.sd-table .sd-table-wide {
    min-width: 240px;
}

.sd-table-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 88px;
    border-radius: 999px;
    padding: 0.25rem 0.62rem;
    font-size: 0.74rem;
    font-weight: 800;
    line-height: 1.2 !important;
    white-space: nowrap;
}

.sd-badge-green {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    color: #16a34a !important;
}

.sd-badge-red {
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #dc2626 !important;
}

.sd-badge-slate {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    color: #475569 !important;
}

.sd-badge-blue {
    background: #eef2ff;
    border: 1px solid #c7d2fe;
    color: #3b6cf7 !important;
}
</style>
"""


TEXT_COLUMN_HINTS = (
    "tweet",
    "teks",
    "isi",
    "keterangan",
    "bersih",
    "clean",
    "hasil akhir",
)

NOWRAP_COLUMN_HINTS = (
    "id",
    "no",
    "tanggal",
    "waktu",
    "status",
    "sentimen",
    "keyakinan",
    "database",
)


def _plain_value(value):
    if value is None:
        return "-"

    try:
        if pd.isna(value):
            return "-"
    except (TypeError, ValueError):
        pass

    return str(value)


def _badge_class(value):
    text = value.lower()

    if "negatif" in text or "gagal" in text:
        return "sd-badge-red"

    if "positif" in text or "berhasil" in text:
        return "sd-badge-green"

    if "netral" in text:
        return "sd-badge-slate"

    return "sd-badge-blue"


def _is_text_column(column):
    name = column.lower()
    return any(hint in name for hint in TEXT_COLUMN_HINTS)


def _is_nowrap_column(column):
    name = column.lower()
    return any(hint in name for hint in NOWRAP_COLUMN_HINTS)


def render_standard_table(
    df,
    *,
    height=380,
    min_width=760,
    right_align=None,
    nowrap=None,
    badge_columns=None,
    wide_columns=None,
    column_widths=None,
):
    if df.empty:
        st.info("Tidak ada data untuk ditampilkan.")
        return

    right_align = set(right_align or [])
    nowrap = set(nowrap or [])
    badge_columns = set(badge_columns or [])
    wide_columns = set(wide_columns or [])
    column_widths = column_widths or {}

    columns = list(df.columns)

    colgroup = ""
    if column_widths:
        col_tags = []

        for column in columns:
            width = column_widths.get(column)
            style = f' style="width:{escape(str(width))};"' if width else ""
            col_tags.append(f"<col{style}>")

        colgroup = f"<colgroup>{''.join(col_tags)}</colgroup>"

    header_cells = []

    for column in columns:
        classes = []

        if column in right_align:
            classes.append("sd-table-right")

        header_cells.append(
            f'<th class="{" ".join(classes)}">{escape(str(column))}</th>'
        )

    body_rows = []

    for _, row in df.iterrows():
        cells = []

        for column in columns:
            value = _plain_value(row[column])
            classes = []

            if column in right_align:
                classes.append("sd-table-right")

            if column in nowrap or _is_nowrap_column(str(column)):
                classes.append("sd-table-nowrap")

            if column in wide_columns or _is_text_column(str(column)):
                classes.append("sd-table-wide")

            class_attr = f' class="{" ".join(classes)}"' if classes else ""

            if column in badge_columns:
                badge_class = _badge_class(value)
                cell_html = (
                    f'<span class="sd-table-badge {badge_class}">'
                    f"{escape(value)}</span>"
                )
            else:
                cell_html = escape(value)

            cells.append(f"<td{class_attr}>{cell_html}</td>")

        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    table_html = f"""
{TABLE_CSS}
<div class="sd-table-card">
    <div class="sd-table-scroll" style="max-height:{int(height)}px;">
        <table class="sd-table" style="min-width:{int(min_width)}px;">
            {colgroup}
            <thead>
                <tr>{''.join(header_cells)}</tr>
            </thead>
            <tbody>
                {''.join(body_rows)}
            </tbody>
        </table>
    </div>
</div>
"""

    st.markdown(table_html, unsafe_allow_html=True)
