from dataclasses import asdict
from datetime import datetime, timezone

from dateutil.tz import tzlocal

from application.ports.auto_contributions_port import AutoContributionsPort
from application.ports.config_port import ConfigPort
from application.ports.credentials_port import CredentialsPort
from application.ports.entity_scraper import EntityScraper
from application.ports.position_port import PositionPort
from application.ports.transaction_port import TransactionPort
from domain.financial_entity import Entity, Feature, ENTITY_DETAILS
from domain.global_position import RealStateCFDetail, FactoringDetail
from domain.historic import Historic, RealStateCFEntry, FactoringEntry
from domain.scrap_result import ScrapResultCode, ScrapResult, LoginResult, SCRAP_BAD_LOGIN_CODES
from domain.scraped_data import ScrapedData
from domain.transactions import TxType
from domain.use_cases.scrape import Scrape
from infrastructure.repository.historic_repository import HistoricRepository

DEFAULT_FEATURES = [Feature.POSITION]


class ScrapeImpl(Scrape):
    def __init__(self,
                 update_cooldown: int,
                 position_port: PositionPort,
                 auto_contr_port: AutoContributionsPort,
                 transaction_port: TransactionPort,
                 historic_repository: HistoricRepository,
                 entity_scrapers: dict[Entity, EntityScraper],
                 config_port: ConfigPort,
                 credentials_port: CredentialsPort):
        self.update_cooldown = update_cooldown
        self.position_port = position_port
        self.auto_contr_repository = auto_contr_port
        self.transaction_port = transaction_port
        self.historic_repository = historic_repository
        self.entity_scrapers = entity_scrapers
        self.config_port = config_port
        self.credentials_port = credentials_port

    async def execute(self,
                      entity: Entity,
                      features: list[Feature],
                      **kwargs) -> ScrapResult:
        scrape_config = self.config_port.load()["scrape"].get("enabledEntities")
        if scrape_config and entity not in scrape_config:
            return ScrapResult(ScrapResultCode.DISABLED)

        if features and not all(f in ENTITY_DETAILS[entity]["features"] for f in features):
            return ScrapResult(ScrapResultCode.FEATURE_NOT_SUPPORTED)

        if Feature.POSITION in features:
            last_update = self.position_port.get_last_updated(entity)
            if last_update and (datetime.now(timezone.utc) - last_update).seconds < self.update_cooldown:
                remaining_seconds = self.update_cooldown - (datetime.now(timezone.utc) - last_update).seconds
                details = {"lastUpdate": last_update.astimezone(tzlocal()).isoformat(), "wait": remaining_seconds}
                return ScrapResult(ScrapResultCode.COOLDOWN, details=details)

        login_args = kwargs.get("login", {})
        credentials = self.credentials_port.get(entity)
        if not credentials:
            return ScrapResult(ScrapResultCode.NO_CREDENTIALS_AVAILABLE)

        specific_scraper = self.entity_scrapers[entity]
        login_result = await specific_scraper.login(credentials, **login_args)
        login_result_code = login_result["result"]
        del login_result["result"]

        if login_result_code == LoginResult.CODE_REQUESTED:
            return ScrapResult(ScrapResultCode.CODE_REQUESTED, details=login_result)

        elif login_result_code not in [LoginResult.CREATED, LoginResult.RESUMED]:
            return ScrapResult(SCRAP_BAD_LOGIN_CODES[login_result_code], details=login_result)

        if not features:
            features = DEFAULT_FEATURES

        scraped_data = await self.get_data(entity, features, specific_scraper)

        return ScrapResult(ScrapResultCode.COMPLETED, data=scraped_data)

    async def get_data(self, entity, features, specific_scraper) -> ScrapedData:
        position = None
        if Feature.POSITION in features:
            position = await specific_scraper.global_position()

        auto_contributions = None
        if Feature.AUTO_CONTRIBUTIONS in features:
            auto_contributions = await specific_scraper.auto_contributions()

        transactions = None
        if Feature.TRANSACTIONS in features:
            registered_txs = self.transaction_port.get_ids_by_entity(entity.name)
            transactions = await specific_scraper.transactions(registered_txs)

        if position:
            self.position_port.save(entity.name, position)

        if auto_contributions:
            self.auto_contr_repository.save(entity.name, auto_contributions)

        historic = None
        if transactions:
            self.transaction_port.save(transactions)

            if transactions.investment and Feature.HISTORIC in features:
                historic = await self.build_historic(entity, specific_scraper)

                self.historic_repository.delete_by_entity(entity.name)
                self.historic_repository.save(historic)

        scraped_data = ScrapedData(position=position,
                                   autoContributions=auto_contributions,
                                   transactions=transactions,
                                   historic=historic)
        return scraped_data

    async def build_historic(self, entity, specific_scraper) -> Historic:
        historical_position = await specific_scraper.historical_position()

        investments_by_name = {}
        for key, cat in asdict(historical_position.investments).items():
            if not cat or "details" not in cat:
                continue
            investments = cat["details"]
            for inv in investments:
                inv_name = inv["name"]
                if inv_name in investments_by_name:
                    investments_by_name[inv_name]["amount"] += inv["amount"]
                    investments_by_name[inv_name]["lastInvestDate"] = max(
                        investments_by_name[inv_name]["lastInvestDate"],
                        inv["lastInvestDate"])
                else:
                    investments_by_name[inv_name] = inv

        investments = list(investments_by_name.values())

        related_txs = self.transaction_port.get_by_entity(entity.name)
        txs_by_name = {}
        for tx in related_txs.investment:
            if tx.name in txs_by_name:
                txs_by_name[tx.name].append(tx)
            else:
                txs_by_name[tx.name] = [tx]

        historic_entries = []
        for inv in investments:
            inv_name = inv["name"]
            if inv_name not in txs_by_name:
                print(f"No txs for investment {inv_name}")
                continue

            related_inv_txs = txs_by_name[inv_name]
            inv_txs = [tx for tx in related_inv_txs if tx.type == TxType.INVESTMENT]
            maturity_txs = [tx for tx in related_inv_txs if tx.type == TxType.MATURITY]

            product_type = next((tx.productType for tx in inv_txs), None)

            if product_type == "REAL_STATE_CF":
                inv = RealStateCFDetail(**inv)
            elif product_type == "FACTORING":
                inv = FactoringDetail(**inv)
            else:
                print(f"Skipping investment with unsupported product type {product_type}")
                continue

            returned, fees, retentions, interests, net_return, last_maturity_tx = None, None, None, None, None, None
            if maturity_txs:
                returned = sum([tx.amount for tx in maturity_txs])
                fees = sum([tx.fees for tx in maturity_txs])
                retentions = sum([tx.retentions for tx in maturity_txs])
                interests = sum([tx.interests for tx in maturity_txs])
                net_return = sum([tx.netAmount for tx in maturity_txs])

                last_maturity_tx = max(maturity_txs, key=lambda txx: txx.date)
                if last_maturity_tx:
                    last_maturity_tx = last_maturity_tx.date

            last_tx_date = max(related_inv_txs, key=lambda txx: txx.date).date

            historic_entry_base = {
                "name": inv_name,
                "invested": inv.amount,
                "returned": returned,
                "currency": inv.currency,
                "currencySymbol": inv.currencySymbol,
                "lastInvestDate": inv.lastInvestDate,
                "lastTxDate": last_tx_date,
                "effectiveMaturity": last_maturity_tx,
                "netReturn": net_return,
                "fees": fees,
                "retentions": retentions,
                "interests": interests,
                "state": inv.state,
                "entity": entity.name,
                "productType": product_type,
                "relatedTxs": related_inv_txs
            }

            historic_entry = None
            if product_type == "REAL_STATE_CF":
                historic_entry = RealStateCFEntry(
                    **historic_entry_base,
                    interestRate=inv.interestRate,
                    months=inv.months,
                    potentialExtension=inv.potentialExtension,
                    type=inv.type,
                    businessType=inv.businessType
                )

            elif product_type == "FACTORING":
                historic_entry = FactoringEntry(
                    **historic_entry_base,
                    interestRate=inv.interestRate,
                    netInterestRate=inv.netInterestRate,
                    maturity=inv.maturity,
                    type=inv.type
                )

            historic_entries.append(historic_entry)

        return Historic(
            entries=historic_entries
        )
