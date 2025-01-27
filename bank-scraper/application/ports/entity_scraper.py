import abc

from domain.auto_contributions import AutoContributions
from domain.exceptions import FeatureNotSupported
from domain.global_position import GlobalPosition, HistoricalPosition
from domain.transactions import Transactions


class EntityScraper(metaclass=abc.ABCMeta):
    async def login(self, credentials: tuple, **kwargs) -> dict:
        raise NotImplementedError

    async def global_position(self) -> GlobalPosition:
        raise FeatureNotSupported

    async def auto_contributions(self) -> AutoContributions:
        raise FeatureNotSupported

    async def transactions(self, registered_txs: set[str]) -> Transactions:
        raise FeatureNotSupported

    async def historical_position(self) -> HistoricalPosition:
        raise FeatureNotSupported
