from asyncio import Lock
from datetime import datetime
from uuid import uuid4

from application.mixins.atomic_use_case import AtomicUCMixin
from application.ports.config_port import ConfigPort
from application.ports.entity_port import EntityPort
from application.ports.position_port import PositionPort
from application.ports.transaction_handler_port import TransactionHandlerPort
from application.ports.transaction_port import TransactionPort
from application.ports.virtual_fetch import VirtualFetcher
from application.ports.virtual_import_registry import VirtualImportRegistry
from application.use_cases.update_sheets import apply_global_config
from dateutil.tz import tzlocal
from domain.entity import Feature
from domain.exception.exceptions import ExecutionConflict
from domain.fetch_result import FetchResult, FetchResultCode
from domain.fetched_data import VirtuallyFetchedData
from domain.use_cases.virtual_fetch import VirtualFetch
from domain.virtual_fetch import VirtualDataImport, VirtualDataSource


class VirtualFetchImpl(AtomicUCMixin, VirtualFetch):
    def __init__(
        self,
        position_port: PositionPort,
        transaction_port: TransactionPort,
        virtual_fetcher: VirtualFetcher,
        entity_port: EntityPort,
        config_port: ConfigPort,
        virtual_import_registry: VirtualImportRegistry,
        transaction_handler_port: TransactionHandlerPort,
    ):
        AtomicUCMixin.__init__(self, transaction_handler_port)

        self._position_port = position_port
        self._transaction_port = transaction_port
        self._virtual_fetcher = virtual_fetcher
        self._entity_port = entity_port
        self._config_port = config_port
        self._virtual_import_registry = virtual_import_registry

        self._lock = Lock()

    async def execute(self) -> FetchResult:
        config = self._config_port.load()
        virtual_fetch_config = config.fetch.virtual

        sheet_config = config.integrations.sheets

        if (
            not virtual_fetch_config.enabled
            or not sheet_config
            or not sheet_config.credentials
        ):
            return FetchResult(FetchResultCode.DISABLED)

        if self._lock.locked():
            raise ExecutionConflict()

        async with self._lock:
            sheets_credentials = sheet_config.credentials

            config_globals = virtual_fetch_config.globals

            investment_sheets = virtual_fetch_config.position or []
            transaction_sheets = virtual_fetch_config.transactions or []
            investment_sheets = apply_global_config(config_globals, investment_sheets)
            transaction_sheets = apply_global_config(config_globals, transaction_sheets)

            existing_entities = self._entity_port.get_all()
            existing_entities_by_name = {
                entity.name: entity for entity in existing_entities
            }

            (
                global_positions,
                created_pos_entities,
            ) = await self._virtual_fetcher.global_positions(
                sheets_credentials, investment_sheets, existing_entities_by_name
            )

            now = datetime.now(tzlocal())
            import_id = None
            virtual_import_entries = []
            if global_positions:
                for entity in created_pos_entities:
                    self._entity_port.insert(entity)
                    existing_entities_by_name[entity.name] = entity

                import_id = uuid4()
                for position in global_positions:
                    self._position_port.save(position)
                    virtual_import_entries.append(
                        VirtualDataImport(
                            import_id=import_id,
                            global_position_id=position.id,
                            source=VirtualDataSource.SHEETS,
                            date=now,
                            feature=Feature.POSITION,
                            entity_id=position.entity.id,
                        )
                    )

            (
                transactions,
                created_tx_entities,
            ) = await self._virtual_fetcher.transactions(
                sheets_credentials,
                transaction_sheets,
                existing_entities_by_name,
            )

            self._transaction_port.delete_non_real()
            if transactions:
                for entity in created_tx_entities:
                    self._entity_port.insert(entity)

                self._transaction_port.save(transactions)

                tx_entities = {
                    tx.entity.id
                    for tx in transactions.investment + transactions.account
                }
                for entity_id in tx_entities:
                    virtual_import_entries.append(
                        VirtualDataImport(
                            import_id=import_id,
                            global_position_id=None,
                            source=VirtualDataSource.SHEETS,
                            date=now,
                            feature=Feature.TRANSACTIONS,
                            entity_id=entity_id,
                        )
                    )

            if not virtual_import_entries and import_id:
                virtual_import_entries.append(
                    VirtualDataImport(
                        import_id=import_id,
                        global_position_id=None,
                        source=VirtualDataSource.SHEETS,
                        date=now,
                        feature=None,
                        entity_id=None,
                    )
                )

            self._virtual_import_registry.insert(virtual_import_entries)

            data = VirtuallyFetchedData(
                positions=global_positions, transactions=transactions
            )

            return FetchResult(FetchResultCode.COMPLETED, data=data)
