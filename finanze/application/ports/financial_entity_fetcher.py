import abc

from domain.auto_contributions import AutoContributions
from domain.entity_login import EntityLoginParams, EntityLoginResult
from domain.exception.exceptions import FeatureNotSupported
from domain.fetch_result import FetchOptions
from domain.global_position import GlobalPosition, HistoricalPosition
from domain.transactions import Transactions


class FinancialEntityFetcher(metaclass=abc.ABCMeta):
    async def login(self, login_params: EntityLoginParams) -> EntityLoginResult:
        raise NotImplementedError

    async def global_position(self) -> GlobalPosition:
        raise FeatureNotSupported

    async def auto_contributions(self) -> AutoContributions:
        raise FeatureNotSupported

    async def transactions(
        self, registered_txs: set[str], options: FetchOptions
    ) -> Transactions:
        raise FeatureNotSupported

    async def historical_position(self) -> HistoricalPosition:
        raise FeatureNotSupported
