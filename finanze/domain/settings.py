from dataclasses import field

from pydantic.dataclasses import dataclass

DataField = str | list[str]
FilterValues = str | list[str]


@dataclass
class GlobalsConfig:
    spreadsheetId: str
    datetimeFormat: str | None = None
    dateFormat: str | None = None


@dataclass
class FilterConfig:
    field: str
    values: FilterValues


@dataclass
class BaseSheetConfig:
    range: str
    spreadsheetId: str | None = None
    datetimeFormat: str | None = None
    dateFormat: str | None = None


@dataclass
class SummarySheetConfig(BaseSheetConfig):
    pass


@dataclass
class InvestmentSheetConfig(BaseSheetConfig):
    data: DataField = field(default_factory=list)


@dataclass
class ContributionSheetConfig(BaseSheetConfig):
    data: DataField = field(default_factory=list)


@dataclass
class TransactionSheetConfig(BaseSheetConfig):
    data: DataField = field(default_factory=list)
    filters: list[FilterConfig] | None = None


@dataclass
class HistoricSheetConfig(BaseSheetConfig):
    filters: list[FilterConfig] | None = None


@dataclass
class SheetsConfig:
    globals: GlobalsConfig
    summary: list[SummarySheetConfig] = field(default_factory=list)
    investments: list[InvestmentSheetConfig] = field(default_factory=list)
    contributions: list[ContributionSheetConfig] = field(default_factory=list)
    transactions: list[TransactionSheetConfig] = field(default_factory=list)
    historic: list[HistoricSheetConfig] = field(default_factory=list)


@dataclass
class ExportConfig:
    sheets: SheetsConfig


@dataclass
class VirtualInvestmentSheetConfig(BaseSheetConfig):
    data: str = field(default_factory=str)


@dataclass
class VirtualTransactionSheetConfig(BaseSheetConfig):
    data: str = field(default_factory=str)


@dataclass
class VirtualScrapeConfig:
    enabled: bool
    globals: GlobalsConfig
    investments: list[VirtualInvestmentSheetConfig] | None = None
    transactions: list[VirtualTransactionSheetConfig] | None = None


@dataclass
class ScrapeConfig:
    virtual: VirtualScrapeConfig
    updateCooldown: int | None = None


@dataclass
class Settings:
    export: ExportConfig
    scrape: ScrapeConfig


ProductSheetConfig = (InvestmentSheetConfig
                      | ContributionSheetConfig
                      | TransactionSheetConfig
                      | HistoricSheetConfig
                      | VirtualInvestmentSheetConfig
                      | VirtualTransactionSheetConfig)
