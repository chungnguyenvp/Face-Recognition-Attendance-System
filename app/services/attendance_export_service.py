from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from app.db import row_to_dict
from app.repositories.attendance_export_repository import MAX_EXPORT_ROWS


STATUS_LABELS = {
    "present_on_time": "Đúng giờ",
    "late": "Đi muộn",
    "early_leave": "Về sớm",
    "late_and_early_leave": "Muộn + về sớm",
    "missing_checkout": "Thiếu check-out",
    "absent": "Vắng",
    "leave_approved": "Nghỉ có phép",
    "leave_pending": "Chờ duyệt nghỉ",
    "pending": "Chưa ghi nhận",
    "unfinalized": "Chưa chốt",
    "off_day": "Ngày nghỉ",
}

PRESENT_STATUSES = {
    "present_on_time",
    "late",
    "early_leave",
    "late_and_early_leave",
    "missing_checkout",
    "unfinalized",
}

STATUS_STYLE_IDS = {
    "present_on_time": 10,
    "leave_approved": 10,
    "late": 11,
    "early_leave": 11,
    "late_and_early_leave": 11,
    "absent": 12,
    "missing_checkout": 13,
    "pending": 14,
    "leave_pending": 14,
    "unfinalized": 14,
    "off_day": 14,
}


class ExportRowLimitError(ValueError):
    pass


def build_attendance_workbook(rows, payload, actor: dict) -> tuple[bytes, int, str]:
    items = [row_to_dict(row) for row in rows]
    if len(items) > MAX_EXPORT_ROWS:
        raise ExportRowLimitError(
            f"Báo cáo vượt quá {MAX_EXPORT_ROWS:,} dòng. Hãy thu hẹp khoảng ngày hoặc bộ lọc."
        )

    generated_at = datetime.now().astimezone()
    sheets: list[tuple[str, str]] = []
    if payload.include_summary:
        sheets.append(("Tong_hop", _summary_sheet_xml(items, payload, actor, generated_at)))
    if payload.include_details:
        sheets.append(("Chi_tiet", _detail_sheet_xml(items, payload, actor, generated_at)))

    filename = (
        f"bao_cao_cham_cong_{payload.date_from.isoformat()}_"
        f"{payload.date_to.isoformat()}.xlsx"
    )
    return _xlsx_package(sheets, generated_at), len(items), filename


def _summary_sheet_xml(items: list[dict], payload, actor: dict, generated_at: datetime) -> str:
    headers = [
        "STT",
        "Mã sinh viên",
        "Họ và tên",
        "Lớp",
        "Tổng bản ghi",
        "Ngày cần hiện diện",
        "Ngày có mặt",
        "Đúng giờ",
        "Đi muộn",
        "Về sớm",
        "Vắng",
        "Nghỉ có phép",
        "Thiếu check-out",
        "Phút đi muộn",
        "Phút về sớm",
        "Tỷ lệ hiện diện",
        "Tổng giờ trong lab",
    ]
    grouped: dict[tuple[int, str, str, str], list[dict]] = defaultdict(list)
    for item in items:
        key = (
            int(item["student_id"]),
            item.get("student_code") or "",
            item.get("full_name") or "",
            item.get("class_name") or "",
        )
        grouped[key].append(item)

    data_rows: list[list[dict]] = []
    sorted_groups = sorted(grouped.items(), key=lambda entry: (entry[0][3], entry[0][2], entry[0][1]))
    for index, ((_, student_code, full_name, class_name), records) in enumerate(sorted_groups, 1):
        statuses = [record.get("status") or "pending" for record in records]
        required_days = sum(status not in {"off_day", "leave_approved"} for status in statuses)
        present_days = sum(status in PRESENT_STATUSES for status in statuses)
        rate = present_days / required_days if required_days else 0
        excel_row = 7 + index
        data_rows.append([
            _number_cell(index, 7),
            _text_cell(student_code),
            _text_cell(full_name),
            _text_cell(class_name),
            _number_cell(len(records), 7),
            _number_cell(required_days, 7),
            _number_cell(present_days, 7),
            _number_cell(statuses.count("present_on_time"), 7),
            _number_cell(sum(status in {"late", "late_and_early_leave"} for status in statuses), 7),
            _number_cell(sum(status in {"early_leave", "late_and_early_leave"} for status in statuses), 7),
            _number_cell(statuses.count("absent"), 7),
            _number_cell(statuses.count("leave_approved"), 7),
            _number_cell(sum(bool(record.get("missing_checkout")) for record in records), 7),
            _number_cell(sum(int(record.get("late_minutes") or 0) for record in records), 7),
            _number_cell(sum(int(record.get("early_leave_minutes") or 0) for record in records), 7),
            _formula_cell(f"IF(F{excel_row}=0,0,G{excel_row}/F{excel_row})", rate, 9),
            _number_cell(sum(int(record.get("total_minutes") or 0) for record in records) / 60, 8),
        ])

    widths = [7, 16, 28, 16, 14, 19, 15, 12, 12, 12, 10, 15, 18, 15, 16, 18, 19]
    return _worksheet_xml(
        "BÁO CÁO TỔNG HỢP CHẤM CÔNG",
        headers,
        data_rows,
        widths,
        payload,
        actor,
        generated_at,
        note="Tỷ lệ hiện diện = ngày có mặt / (tổng bản ghi - ngày nghỉ - nghỉ có phép).",
    )


def _detail_sheet_xml(items: list[dict], payload, actor: dict, generated_at: datetime) -> str:
    headers = [
        "STT",
        "Ngày",
        "Mã sinh viên",
        "Họ và tên",
        "Lớp",
        "Giờ vào đầu tiên",
        "Giờ ra cuối cùng",
        "Trạng thái",
        "Phút đi muộn",
        "Phút về sớm",
        "Tổng giờ trong lab",
        "Thiếu check-out",
        "Ghi chú",
        "Mã bản ghi",
    ]
    data_rows: list[list[dict]] = []
    for index, item in enumerate(items, 1):
        status = item.get("status") or "pending"
        data_rows.append([
            _number_cell(index, 7),
            _date_cell(item.get("attendance_date")),
            _text_cell(item.get("student_code") or ""),
            _text_cell(item.get("full_name") or ""),
            _text_cell(item.get("class_name") or ""),
            _datetime_cell(item.get("first_check_in_at")),
            _datetime_cell(item.get("last_check_out_at")),
            _text_cell(STATUS_LABELS.get(status, status), STATUS_STYLE_IDS.get(status, 14)),
            _number_cell(int(item.get("late_minutes") or 0), 7),
            _number_cell(int(item.get("early_leave_minutes") or 0), 7),
            _number_cell(int(item.get("total_minutes") or 0) / 60, 8),
            _text_cell("Có" if item.get("missing_checkout") else "Không", 13 if item.get("missing_checkout") else 10),
            _text_cell(item.get("note") or ""),
            _number_cell(int(item["id"]), 7),
        ])

    widths = [7, 13, 16, 28, 16, 20, 20, 20, 15, 16, 19, 18, 38, 14]
    return _worksheet_xml(
        "BÁO CÁO CHI TIẾT CHẤM CÔNG",
        headers,
        data_rows,
        widths,
        payload,
        actor,
        generated_at,
        note="Dữ liệu được xuất nguyên trạng; thao tác xuất không tự tính lại chấm công.",
    )


def _worksheet_xml(
    title: str,
    headers: list[str],
    data_rows: list[list[dict]],
    widths: list[float],
    payload,
    actor: dict,
    generated_at: datetime,
    note: str,
) -> str:
    last_col = _column_name(len(headers))
    last_row = max(7, 7 + len(data_rows))
    rows: list[str] = []
    rows.append(_row_xml(1, [_text_cell(title, 1)], height=28))
    metadata = [
        ("Khoảng ngày", f"{payload.date_from.strftime('%d/%m/%Y')} - {payload.date_to.strftime('%d/%m/%Y')}"),
        ("Bộ lọc", _filter_description(payload)),
        ("Người xuất", f"{actor.get('username') or '-'} ({actor.get('role') or '-'})"),
        ("Tạo lúc", generated_at.strftime("%d/%m/%Y %H:%M:%S %z")),
        ("Ghi chú", note),
    ]
    for row_number, (label, value) in enumerate(metadata, 2):
        rows.append(_row_xml(row_number, [_text_cell(label, 2), _text_cell(value, 3)]))
    rows.append(_row_xml(7, [_text_cell(header, 4) for header in headers], height=32))
    for row_number, cells in enumerate(data_rows, 8):
        rows.append(_row_xml(row_number, cells))

    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, 1)
    )
    metadata_merges = "".join(f'<mergeCell ref="B{row}:{last_col}{row}"/>' for row in range(2, 7))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:{last_col}{last_row}"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="7" topLeftCell="A8" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="20"/>
  <cols>{columns}</cols>
  <sheetData>{''.join(rows)}</sheetData>
  <autoFilter ref="A7:{last_col}{last_row}"/>
  <mergeCells count="6"><mergeCell ref="A1:{last_col}1"/>{metadata_merges}</mergeCells>
  <pageMargins left="0.35" right="0.35" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''


def _filter_description(payload) -> str:
    status = STATUS_LABELS.get(payload.status, "Tất cả trạng thái") if payload.status else "Tất cả trạng thái"
    query = payload.q or "Không"
    return f"Trạng thái: {status} | Sinh viên: {query if payload.q else 'Tất cả'}"


def _text_cell(value: object, style: int = 0) -> dict:
    return {"kind": "text", "value": _safe_excel_text(value), "style": style}


def _number_cell(value: int | float, style: int = 0) -> dict:
    return {"kind": "number", "value": value, "style": style}


def _formula_cell(formula: str, cached_value: int | float, style: int = 0) -> dict:
    return {"kind": "formula", "formula": formula, "value": cached_value, "style": style}


def _date_cell(value: str | None) -> dict:
    if not value:
        return _text_cell("")
    try:
        parsed = date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return _text_cell(value)
    return _number_cell((parsed - date(1899, 12, 30)).days, 5)


def _datetime_cell(value: str | None) -> dict:
    if not value:
        return _text_cell("")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return _text_cell(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    base = datetime(1899, 12, 30)
    serial = (parsed - base).total_seconds() / 86400
    return _number_cell(serial, 6)


def _safe_excel_text(value: object) -> str:
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _row_xml(row_number: int, cells: list[dict], height: int | None = None) -> str:
    attrs = f'r="{row_number}"'
    if height:
        attrs += f' ht="{height}" customHeight="1"'
    rendered = "".join(_cell_xml(row_number, column, cell) for column, cell in enumerate(cells, 1))
    return f"<row {attrs}>{rendered}</row>"


def _cell_xml(row_number: int, column_number: int, cell: dict) -> str:
    reference = f"{_column_name(column_number)}{row_number}"
    style = int(cell.get("style") or 0)
    style_attr = f' s="{style}"' if style else ""
    if cell["kind"] == "text":
        value = escape(str(cell.get("value") or ""))
        return f'<c r="{reference}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{value}</t></is></c>'
    if cell["kind"] == "formula":
        formula = escape(str(cell["formula"]))
        return f'<c r="{reference}"{style_attr}><f>{formula}</f><v>{cell["value"]}</v></c>'
    return f'<c r="{reference}"{style_attr}><v>{cell["value"]}</v></c>'


def _column_name(column_number: int) -> str:
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xlsx_package(sheets: list[tuple[str, str]], generated_at: datetime) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_relationships_xml())
        archive.writestr("docProps/app.xml", _app_properties_xml(sheets))
        archive.writestr("docProps/core.xml", _core_properties_xml(generated_at))
        archive.writestr("xl/workbook.xml", _workbook_xml(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (_, sheet_xml) in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml)
    return output.getvalue()


def _content_types_xml(sheet_count: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  {sheets}
</Types>'''


def _root_relationships_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _workbook_xml(sheets: list[tuple[str, str]]) -> str:
    entries = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <bookViews><workbookView activeTab="0"/></bookViews>
  <sheets>{entries}</sheets>
  <calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>
</workbook>'''


def _workbook_relationships_xml(sheet_count: int) -> str:
    sheets = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {sheets}
  <Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''


def _app_properties_xml(sheets: list[tuple[str, str]]) -> str:
    titles = "".join(f"<vt:lpstr>{escape(name)}</vt:lpstr>" for name, _ in sheets)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Face Lab System</Application>
  <HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(sheets)}</vt:i4></vt:variant></vt:vector></HeadingPairs>
  <TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>
</Properties>'''


def _core_properties_xml(generated_at: datetime) -> str:
    created = generated_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Face Lab System</dc:creator><cp:lastModifiedBy>Face Lab System</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>'''


def _styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="3"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy hh:mm"/><numFmt numFmtId="166" formatCode="0.00"/></numFmts>
  <fonts count="3">
    <font><sz val="10"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="16"/><name val="Aptos Display"/><family val="2"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/><family val="2"/></font>
  </fonts>
  <fills count="8">
    <fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1E3A5F"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF2563EB"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFDBEAFE"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="thin"><color rgb="FFD9E2F3"/></bottom><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="15">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
    <xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
    <xf numFmtId="10" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
