import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from uuid import UUID

from dateutil.tz import tzlocal
from domain.dezimal import Dezimal
from domain.entity import Entity
from domain.exception.exceptions import ExportException
from domain.settings import BaseSheetConfig, ProductSheetConfig
from googleapiclient.errors import HttpError
from infrastructure.sheets.importer.sheets_importer import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_DATETIME_FORMAT,
)
from pytz import utc

LAST_UPDATE_FIELD = "last_update"
NO_HEADERS_FOUND = "NO_HEADERS_FOUND"
ENTITY_COLUMN = "entity"
TYPE_COLUMN = "investment_type"
ENTITY_UPDATED_AT = "entity_updated_at"

_log = logging.getLogger(__name__)


def update_sheet(
    sheet,
    data: object | dict[Entity, object],
    config: ProductSheetConfig,
    last_update: dict[Entity, datetime] = None,
):
    sheet_id, sheet_range, field_paths = config.spreadsheetId, config.range, config.data
    try:
        result = sheet.values().get(spreadsheetId=sheet_id, range=sheet_range).execute()
    except HttpError as e:
        if e.resp.status == 400:
            raise ExportException(f"sheet.not_found.{sheet_range}")
        else:
            raise
    cells = result.get("values")
    if not cells:
        _log.warning(f"Got empty sheet for {sheet_range}, aborting sheet...")
        return

    rows = map_rows(data, cells, field_paths, last_update, config)
    if not rows:
        return

    request = sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"{sheet_range}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    )

    request.execute()


def map_rows(
    data: object | dict[Entity, object],
    cells: list[list[str]],
    field_paths: list[str],
    last_update: dict[Entity, datetime],
    config: ProductSheetConfig,
) -> list[list[str]] | None:
    sheet_range = config.range
    per_entity_date = False
    last_update_row_index, column_index = next(
        (
            (index, row.index(LAST_UPDATE_FIELD))
            for index, row in enumerate(cells)
            if LAST_UPDATE_FIELD in row
        ),
        (-1, None),
    )

    if last_update and column_index is None:
        per_entity_date = True
        last_update_row_index, column_index = next(
            (
                (index, row.index(ENTITY_UPDATED_AT))
                for index, row in enumerate(cells)
                if ENTITY_UPDATED_AT in row
            ),
            (-1, None),
        )

    if column_index is not None:
        if per_entity_date:
            entity_last_update_row = map_last_update_row(last_update, config)
            cells[last_update_row_index] = [
                *["" for _ in range(column_index)],
                *entity_last_update_row,
            ]
        else:
            last_update_date = datetime.now(tzlocal())
            config_datetime_format = config.datetimeFormat
            if config_datetime_format:
                formated_last_update_date = last_update_date.strftime(
                    config_datetime_format
                )
            else:
                formated_last_update_date = last_update_date.isoformat()

            set_field_value(
                cells[last_update_row_index],
                column_index + 1,
                formated_last_update_date,
                config,
            )

            for i, cell in enumerate(cells[last_update_row_index]):
                if i < column_index or i > column_index + 1:
                    cells[last_update_row_index][i] = ""

    header_row_index, columns = next(
        (
            (index, row)
            for index, row in enumerate(
                cells[last_update_row_index + 1 :], last_update_row_index + 1
            )
            if row
        ),
        (None, None),
    )
    if header_row_index is None or columns is None:
        _log.warning(
            f"No headers in {sheet_range} found while trying to export data to Google Sheets, aborting sheet..."
        )
        return None

    product_rows = map_products(data, columns, field_paths, config)
    return [
        *cells[: header_row_index + 1],
        *product_rows,
        *[["" for _ in range(100)] for _ in range(500)],
    ]


def map_products(
    data: object | dict[Entity, object],
    columns: list[str],
    field_paths: list[str],
    config: ProductSheetConfig,
) -> list[list[str]]:
    product_rows = []
    if isinstance(data, dict):
        for entity, entity_data in data.items():
            for field_path in field_paths:
                try:
                    path_tokens = field_path.split(".")
                    target_data = entity_data
                    for field in path_tokens:
                        try:
                            target_data = getattr(target_data, field)
                        except AttributeError:
                            target_data = target_data.get(field)

                    if not target_data:
                        continue

                    if isinstance(target_data, list):
                        for product in target_data:
                            if not matches_filters(product, config):
                                continue
                            product_rows.append(
                                map_product_row(
                                    product, entity, field_path, columns, config
                                )
                            )
                    else:
                        if not matches_filters(target_data, config):
                            continue
                        product_rows.append(
                            map_product_row(
                                target_data, entity, field_path, columns, config
                            )
                        )
                except AttributeError:
                    pass
    else:
        for field_path in field_paths:
            target_data = data
            path_tokens = field_path.split(".")
            for field in path_tokens:
                if not hasattr(target_data, field):
                    continue
                target_data = getattr(target_data, field)

            for product in target_data:
                if not matches_filters(product, config):
                    continue
                product_rows.append(
                    map_product_row(product, None, None, columns, config)
                )

    return product_rows


def matches_filters(element, config: ProductSheetConfig):
    filters = config.filters if (hasattr(config, "filters") and config.filters) else []
    for filter_rule in filters:
        filtered_field = filter_rule.field
        matching_values = filter_rule.values
        matching_values = (
            [matching_values]
            if not isinstance(matching_values, list)
            else matching_values
        )
        matching_values = [str(value) for value in matching_values]
        value = str(getattr(element, filtered_field))
        if value not in matching_values:
            return False
    return True


def map_product_row(
    details, entity: Entity, p_type, columns, config: ProductSheetConfig
) -> list[str]:
    rows = []
    details = asdict(details)
    if ENTITY_COLUMN not in details:
        details[ENTITY_COLUMN] = str(entity)
    else:
        details[ENTITY_COLUMN] = details[ENTITY_COLUMN]["name"]

    if p_type:
        details[TYPE_COLUMN] = format_type_name(p_type)
    for column in columns:
        if column in details:
            rows.append(format_field_value(details[column], config))
        else:
            complex_column = "." in column
            if complex_column:
                fields = column.split(".")
                obj = details
                for field in fields:
                    obj = obj.get(field) or {}
                value = format_field_value(obj, config) if obj != {} else ""
                rows.append(value)
            else:
                rows.append("")

    return rows


def format_type_name(value):
    tokens = value.split(".")
    if len(tokens) >= 2:
        return tokens[-2].upper()
    else:
        return value.upper()


def map_last_update_row(last_update: dict[Entity, datetime], config: BaseSheetConfig):
    last_update = sorted(last_update.items(), key=lambda item: item[1], reverse=True)
    last_update_row = [None]
    for k, v in last_update:
        last_update_row.append(str(k))
        last_update_date = v.astimezone(tz=tzlocal())
        config_datetime_format = config.datetimeFormat
        if config_datetime_format:
            formated_last_update_date = last_update_date.strftime(
                config_datetime_format
            )
        else:
            formated_last_update_date = last_update_date.isoformat()
        last_update_row.append(formated_last_update_date)
    last_update_row.extend(["" for _ in range(10)])
    return last_update_row


def set_field_value(row: list[str], index: int, value, config: BaseSheetConfig):
    value = format_field_value(value, config)
    if len(row) > index:
        row[index] = value
    else:
        row.append(value)


def format_field_value(value, config: BaseSheetConfig):
    if value is None:
        return ""

    if isinstance(value, date) and not isinstance(value, datetime):
        date_format = config.dateFormat or DEFAULT_DATE_FORMAT
        return value.strftime(date_format)

    elif isinstance(value, datetime):
        datetime_format = config.datetimeFormat or DEFAULT_DATETIME_FORMAT
        value = value.replace(tzinfo=utc).astimezone(tzlocal())
        return value.strftime(datetime_format)

    elif isinstance(value, dict) or isinstance(value, list):
        return json.dumps(value, default=str)

    elif isinstance(value, Dezimal):
        return float(value)

    elif isinstance(value, UUID):
        return str(value)

    return value
