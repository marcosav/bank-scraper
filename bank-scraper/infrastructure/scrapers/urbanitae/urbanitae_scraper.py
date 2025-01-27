from datetime import datetime

from application.ports.entity_scraper import EntityScraper
from domain.currency_symbols import CURRENCY_SYMBOL_MAP
from domain.financial_entity import Entity
from domain.global_position import Investments, GlobalPosition, RealStateCFInvestments, RealStateCFDetail, SourceType, \
    Account, HistoricalPosition
from domain.transactions import Transactions, RealStateCFTx, TxType, ProductType
from infrastructure.scrapers.urbanitae.urbanitae_client import UrbanitaeAPIClient

FUNDED_STATES = ["FUNDED", "POST_PREFUNDING", "FORMALIZED"]
CANCELLED_STATES = ["CLOSED", "CANCELED", "CANCELED_WITH_COMPENSATION"]


class UrbanitaeScraper(EntityScraper):
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"

    def __init__(self):
        self.__client = UrbanitaeAPIClient()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        username, password = credentials
        return self.__client.login(username, password)

    async def global_position(self) -> GlobalPosition:
        wallet = self.__client.get_wallet()
        balance = wallet["balance"]

        account = Account(total=round(balance, 2))

        investments_data = self.__client.get_investments()

        real_state_cf_inv_details = [
            self.map_investment(inv)
            for inv in investments_data if inv["projectPhase"] in FUNDED_STATES
        ]

        total_invested = round(sum([inv.amount for inv in real_state_cf_inv_details]), 2)
        weighted_interest_rate = round(
            (sum([inv.amount * inv.interestRate for inv in real_state_cf_inv_details])
             / sum([inv.amount for inv in real_state_cf_inv_details])),
            4,
        )
        investments = Investments(
            realStateCF=RealStateCFInvestments(
                invested=total_invested,
                weightedInterestRate=weighted_interest_rate,
                details=real_state_cf_inv_details
            )
        )

        return GlobalPosition(
            account=account,
            investments=investments
        )

    def map_investment(self, inv):
        project_details = self.__client.get_project_detail(inv["projectId"])

        months = project_details["details"]["investmentPeriod"]
        interest_rate = project_details["fund"]["apreciationProfitability"]

        return RealStateCFDetail(
            name=inv["projectName"],
            amount=round(inv["investedQuantityActive"], 2),
            currency="EUR",
            currencySymbol="€",
            interestRate=round(interest_rate / 100, 4),
            lastInvestDate=datetime.strptime(inv["lastInvestDate"], self.DATETIME_FORMAT),
            months=int(months),
            potentialExtension=None,
            type=inv["projectType"],
            businessType=inv["projectBusinessModel"],
            state=inv["projectPhase"],
        )

    async def transactions(self, registered_txs: set[str]) -> Transactions:
        raw_txs = self.__client.get_transactions()

        txs = []
        for tx in raw_txs:
            ref = tx["id"]
            if ref in registered_txs:
                continue

            tx_type_raw = tx["type"]
            tx_type = TxType.INVESTMENT if tx_type_raw == "INVESTMENT" else None
            if tx_type != TxType.INVESTMENT:
                print(f"Skipping tx {ref} with type {tx_type_raw}")
                continue

            currency = tx["externalProviderData"]["currency"]
            name = tx["externalProviderData"]["argumentValue"]

            txs.append(RealStateCFTx(
                id=tx["id"],
                name=name,
                amount=round(tx["amount"], 2),
                currency=currency,
                currencySymbol=CURRENCY_SYMBOL_MAP.get(currency, currency),
                type=tx_type,
                date=datetime.strptime(tx["timestamp"], self.DATETIME_FORMAT),
                entity=Entity.URBANITAE,
                productType=ProductType.REAL_STATE_CF,
                fees=round(tx["fee"], 2),
                retentions=0,
                interests=0,
                netAmount=0,
                sourceType=SourceType.REAL
            ))

        return Transactions(investment=txs)

    async def historical_position(self) -> HistoricalPosition:
        investments_data = self.__client.get_investments()

        real_state_cf_inv_details = [
            self.map_investment(inv)
            for inv in investments_data
        ]

        return HistoricalPosition(
            investments=Investments(
                realStateCF=RealStateCFInvestments(
                    invested=0,
                    weightedInterestRate=0,
                    details=real_state_cf_inv_details
                )
            )
        )
