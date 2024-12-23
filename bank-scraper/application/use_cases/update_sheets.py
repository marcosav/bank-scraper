from datetime import datetime

from application.ports.auto_contributions_port import AutoContributionsPort
from application.ports.config_port import ConfigPort
from application.ports.position_port import PositionPort
from application.ports.sheets_export_port import SheetsUpdatePort
from application.ports.transaction_port import TransactionPort
from domain.auto_contributions import AutoContributions
from domain.global_position import GlobalPosition
from domain.transactions import Transactions
from domain.use_cases.update_sheets import UpdateSheets

DETAILS_FIELD = "details"
ADDITIONAL_DATA_FIELD = "additionalData"


def apply_global_config(config_globals, entries: list[dict]) -> list[dict]:
    for key, value in config_globals.items():
        for entry in entries:
            if key not in entry:
                entry[key] = value
    return entries


class UpdateSheetsImpl(UpdateSheets):

    def __init__(self,
                 position_port: PositionPort,
                 auto_contr_port: AutoContributionsPort,
                 transaction_port: TransactionPort,
                 sheets_update_port: SheetsUpdatePort,
                 config_port: ConfigPort):
        self.position_port = position_port
        self.auto_contr_port = auto_contr_port
        self.transaction_port = transaction_port
        self.sheets_update_port = sheets_update_port
        self.config_port = config_port

    def execute(self):
        config = self.config_port.load()
        sheets_export_config = config["export"]["sheets"]

        config_globals = sheets_export_config["globals"]

        summary_configs = sheets_export_config["summary"]
        investment_configs = sheets_export_config["investments"]
        contrib_configs = sheets_export_config["contributions"]
        tx_configs = sheets_export_config["transactions"]
        apply_global_config(config_globals, summary_configs)
        apply_global_config(config_globals, investment_configs)
        apply_global_config(config_globals, contrib_configs)
        apply_global_config(config_globals, tx_configs)

        global_position = self.position_port.get_last_grouped_by_entity()

        self.update_summary_sheets(global_position, summary_configs)
        self.update_investment_sheets(global_position, investment_configs)

        auto_contributions = self.auto_contr_port.get_all_grouped_by_entity()
        auto_contributions_last_update = self.auto_contr_port.get_last_update_grouped_by_entity()
        self.update_contributions(auto_contributions, contrib_configs, auto_contributions_last_update)

        transactions = self.transaction_port.get_all()
        transactions_last_update = self.transaction_port.get_last_created_grouped_by_entity()
        self.update_transactions(transactions, tx_configs, transactions_last_update)

    def update_summary_sheets(self, global_position: dict[str, GlobalPosition], summary_configs):
        for config in summary_configs:
            self.sheets_update_port.update_summary(global_position, config)

    def update_investment_sheets(self, global_position: dict[str, GlobalPosition], inv_configs):
        for config in inv_configs:
            fields = config["data"]
            fields = [fields] if isinstance(fields, str) else fields
            config["data"] = [f"investments.{field}.{DETAILS_FIELD}" for field in fields]

            self.sheets_update_port.update_sheet(global_position, config)

    def update_contributions(self, contributions: dict[str, AutoContributions], contrib_configs,
                             last_update: dict[str, datetime]):
        for config in contrib_configs:
            fields = config["data"]
            config["data"] = [fields] if isinstance(fields, str) else fields
            self.sheets_update_port.update_sheet(contributions, config, last_update)

    def update_transactions(self, transactions: Transactions, tx_configs, last_update: dict[str, datetime]):
        for config in tx_configs:
            fields = config["data"]
            config["data"] = [fields] if isinstance(fields, str) else fields
            self.sheets_update_port.update_sheet(transactions, config, last_update)
