import datetime
from dataclasses import asdict
from typing import Union

from dateutil.tz import tzlocal

from infrastructure.sheets.exporter.sheets_summary_exporter import LAST_UPDATE_FIELD, set_field_value, \
    format_field_value

NO_HEADERS_FOUND = "NO_HEADERS_FOUND"
ENTITY_COLUMN = "entity"
TYPE_COLUMN = "investmentType"
ENTITY_UPDATED_AT = "entityUpdatedAt"


def update_sheet(
        sheet,
        data: Union[dict, object],
        sheet_id: str,
        sheet_name: str,
        field_paths: list[str],
        last_update: dict[str, datetime] = None):
    result = sheet.values().get(spreadsheetId=sheet_id, range=sheet_name).execute()
    cells = result.get('values', None)
    if not cells:
        rows = [[NO_HEADERS_FOUND]]
    else:
        rows = map_rows(data, cells, field_paths, last_update)
        if not rows:
            return

    request = sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    )

    request.execute()


def map_rows(
        data: Union[dict, object],
        cells: list[list[str]],
        field_paths: list[str],
        last_update: dict[str, datetime]) -> list[list[str]]:
    per_entity_date = False
    last_update_row_index, column_index = next(
        ((index, row.index(LAST_UPDATE_FIELD)) for index, row in enumerate(cells) if LAST_UPDATE_FIELD in row),
        (-1, None))

    if last_update and column_index is None:
        per_entity_date = True
        last_update_row_index, column_index = next(
            ((index, row.index(ENTITY_UPDATED_AT)) for index, row in enumerate(cells) if ENTITY_UPDATED_AT in row),
            (-1, None))

    if column_index is not None:
        if per_entity_date:
            entity_last_update_row = map_last_update_row(last_update)
            cells[last_update_row_index] = [*["" for _ in range(column_index)], *entity_last_update_row]
        else:
            set_field_value(cells[last_update_row_index], column_index + 1,
                            datetime.datetime.now(tzlocal()).isoformat())
            for i, cell in enumerate(cells[last_update_row_index]):
                if i < column_index or i > column_index + 1:
                    cells[last_update_row_index][i] = ""

    header_row_index, columns = next(
        ((index, row) for index, row in enumerate(cells[last_update_row_index + 1:], last_update_row_index + 1) if
         row), (None, None))
    if header_row_index is None or columns is None:
        if column_index is not None:
            set_field_value(cells[last_update_row_index], column_index + 2, NO_HEADERS_FOUND)
            return cells
        else:
            return [[NO_HEADERS_FOUND]]

    product_rows = map_products(data, columns, field_paths)
    return [
        *cells[:header_row_index + 1],
        *product_rows,
        *[["" for _ in range(20)] for _ in range(20)],
    ]


def map_products(
        data: Union[dict, object],
        columns: list[str],
        field_paths: list[str]) -> list[list[str]]:
    product_rows = []
    if isinstance(data, dict):
        for entity, entity_data in data.items():
            for field_path in field_paths:
                try:
                    path_tokens = field_path.split(".")
                    target_data = entity_data
                    for field in path_tokens:
                        target_data = getattr(target_data, field)

                    for product in target_data:
                        product_rows.append(map_product_row(product, entity, field_path, columns))
                except AttributeError:
                    pass
    else:
        target_data = data
        for field_path in field_paths:
            path_tokens = field_path.split(".")
            for field in path_tokens:
                target_data = getattr(target_data, field)

            for product in target_data:
                product_rows.append(map_product_row(product, None, None, columns))

    return product_rows


def map_product_row(details, entity, p_type, columns) -> list[str]:
    rows = []
    details = asdict(details)
    if ENTITY_COLUMN not in details:
        details[ENTITY_COLUMN] = entity
    if p_type:
        details[TYPE_COLUMN] = format_type_name(p_type)
    for column in columns:
        if column in details:
            rows.append(format_field_value(details[column]))
        else:
            rows.append("")

    return rows


def format_type_name(value):
    tokens = value.split(".")
    if len(tokens) >= 2:
        return tokens[-2].upper()
    else:
        return value.upper()


def map_last_update_row(last_update: dict[str, datetime]):
    last_update = sorted(last_update.items(), key=lambda item: item[1], reverse=True)
    last_update_row = [None]
    for k, v in last_update:
        last_update_row.append(k)
        last_update_row.append(v.astimezone(tz=tzlocal()).isoformat())
    last_update_row.extend(["" for _ in range(10)])
    return last_update_row