from asyncio import Lock
from dataclasses import asdict
from datetime import datetime
from typing import TypeVar

from application.ports.auto_contributions_port import AutoContributionsPort
from application.ports.config_port import ConfigPort
from application.ports.historic_port import HistoricPort
from application.ports.position_port import PositionPort
from application.ports.sheets_export_port import SheetsUpdatePort
from application.ports.transaction_port import TransactionPort
from domain.auto_contributions import AutoContributions, ContributionQueryRequest
from domain.exception.exceptions import ExecutionConflict
from domain.export import ExportRequest
from domain.financial_entity import FinancialEntity
from domain.global_position import GlobalPosition
from domain.historic import Historic
from domain.settings import (
    ContributionSheetConfig,
    GlobalsConfig,
    GoogleCredentials,
    HistoricSheetConfig,
    InvestmentSheetConfig,
    ProductSheetConfig,
    SummarySheetConfig,
    TransactionSheetConfig,
)
from domain.transactions import Transactions
from domain.use_cases.update_sheets import UpdateSheets

DETAILS_FIELD = "details"
ADDITIONAL_DATA_FIELD = "additionalData"

T = TypeVar("T", bound=ProductSheetConfig | SummarySheetConfig)


def apply_global_config(config_globals: GlobalsConfig, entries: list[T]) -> list[T]:
    globals_as_dict = asdict(config_globals)
    updated_entries = []
    for entry in entries:
        entry_as_dict = asdict(entry)
        for key, value in globals_as_dict.items():
            if key not in entry_as_dict or entry_as_dict[key] is None:
                entry_as_dict[key] = value
        updated_entries.append(type(entry)(**entry_as_dict))

    return updated_entries


class UpdateSheetsImpl(UpdateSheets):
    def __init__(
        self,
        position_port: PositionPort,
        auto_contr_port: AutoContributionsPort,
        transaction_port: TransactionPort,
        historic_port: HistoricPort,
        sheets_update_port: SheetsUpdatePort,
        config_port: ConfigPort,
    ):
        self._position_port = position_port
        self._auto_contr_port = auto_contr_port
        self._transaction_port = transaction_port
        self._historic_port = historic_port
        self._sheets_update_port = sheets_update_port
        self._config_port = config_port

        self._lock = Lock()

    async def execute(self, request: ExportRequest):
        config = self._config_port.load()
        sheets_export_config = config.export.sheets
        sheet_config = config.integrations.sheets

        if (
            not sheets_export_config
            or not sheets_export_config.enabled
            or not sheet_config
            or not sheet_config.credentials
        ):
            raise ValueError("Sheets export is not enabled")

        if self._lock.locked():
            raise ExecutionConflict()

        async with self._lock:
            sheet_credentials = sheet_config.credentials

            config_globals = sheets_export_config.globals or {}

            summary_configs = sheets_export_config.summary or []
            investment_configs = sheets_export_config.investments or []
            contrib_configs = sheets_export_config.contributions or []
            tx_configs = sheets_export_config.transactions or []
            historic_configs = sheets_export_config.historic or []
            summary_configs = apply_global_config(config_globals, summary_configs)
            investment_configs = apply_global_config(config_globals, investment_configs)
            contrib_configs = apply_global_config(config_globals, contrib_configs)
            tx_configs = apply_global_config(config_globals, tx_configs)
            historic_configs = apply_global_config(config_globals, historic_configs)

            global_position_by_entity = self._position_port.get_last_grouped_by_entity()

            self.update_summary_sheets(
                global_position_by_entity, summary_configs, sheet_credentials
            )
            self.update_investment_sheets(
                global_position_by_entity, investment_configs, sheet_credentials
            )

            auto_contributions = self._auto_contr_port.get_all_grouped_by_entity(
                ContributionQueryRequest()
            )
            auto_contributions_last_update = (
                self._auto_contr_port.get_last_update_grouped_by_entity()
            )

            self.update_contributions(
                auto_contributions,
                contrib_configs,
                auto_contributions_last_update,
                sheet_credentials,
            )

            transactions = self._transaction_port.get_all()
            transactions_last_update = (
                self._transaction_port.get_last_created_grouped_by_entity()
            )
            self.update_transactions(
                transactions, tx_configs, transactions_last_update, sheet_credentials
            )

            historic = self._historic_port.get_all()
            self.update_historic(historic, historic_configs, sheet_credentials)

    def update_summary_sheets(
        self,
        global_position: dict[FinancialEntity, GlobalPosition],
        configs: list[SummarySheetConfig],
        credentials: GoogleCredentials,
    ):
        for config in configs:
            self._sheets_update_port.update_summary(
                global_position, credentials, config
            )

    def update_investment_sheets(
        self,
        global_position: dict[FinancialEntity, GlobalPosition],
        configs: list[InvestmentSheetConfig],
        credentials: GoogleCredentials,
    ):
        for config in configs:
            fields = config.data
            fields = [fields] if isinstance(fields, str) else fields
            config.data = [f"investments.{field}.{DETAILS_FIELD}" for field in fields]

            self._sheets_update_port.update_sheet(global_position, credentials, config)

    def update_contributions(
        self,
        contributions: dict[FinancialEntity, AutoContributions],
        configs: list[ContributionSheetConfig],
        last_update: dict[FinancialEntity, datetime],
        credentials: GoogleCredentials,
    ):
        for config in configs:
            fields = config.data
            config.data = [fields] if isinstance(fields, str) else fields

            self._sheets_update_port.update_sheet(
                contributions, credentials, config, last_update
            )

    def update_transactions(
        self,
        transactions: Transactions,
        configs: list[TransactionSheetConfig],
        last_update: dict[FinancialEntity, datetime],
        credentials: GoogleCredentials,
    ):
        for config in configs:
            fields = config.data
            config.data = [fields] if isinstance(fields, str) else fields

            self._sheets_update_port.update_sheet(
                transactions, credentials, config, last_update
            )

    def update_historic(
        self,
        historic: Historic,
        configs: list[HistoricSheetConfig],
        credentials: GoogleCredentials,
    ):
        for config in configs:
            config.data = ["entries"]

            self._sheets_update_port.update_sheet(historic, credentials, config)
