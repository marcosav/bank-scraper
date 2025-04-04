from application.ports.config_port import ConfigPort
from domain.available_sources import AvailableSources, AvailableSourceEntity
from domain.financial_entity import Entity, ENTITY_DETAILS
from domain.use_cases.get_available_sources import GetAvailableSources


class GetAvailableSourcesImpl(GetAvailableSources):

    def __init__(self, config_port: ConfigPort):
        self._config_port = config_port

    async def execute(self) -> AvailableSources:
        scrape_config = self._config_port.load()["scrape"]

        virtual_enabled = scrape_config["virtual"]["enabled"]

        all_entities = Entity.__members__.values()
        enabled_entities_config = scrape_config.get("enabledEntities", all_entities)

        enabled_entities = [
            AvailableSourceEntity(**details) for entity, details in ENTITY_DETAILS.items()
            if entity in enabled_entities_config
        ]

        return AvailableSources(
            virtual=virtual_enabled,
            entities=enabled_entities
        )
