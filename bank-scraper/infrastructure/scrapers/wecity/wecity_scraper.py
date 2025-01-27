from datetime import datetime, date
from hashlib import sha1

from dateutil.tz import tzlocal

from application.ports.entity_scraper import EntityScraper
from domain.financial_entity import Entity
from domain.global_position import GlobalPosition, RealStateCFDetail, RealStateCFInvestments, Investments, SourceType, \
    Account, HistoricalPosition
from domain.transactions import Transactions, RealStateCFTx, TxType, ProductType
from infrastructure.scrapers.wecity.wecity_client import WecityAPIClient


class WecityScraper(EntityScraper):

    def __init__(self):
        self.__client = WecityAPIClient()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        username, password = credentials
        process_id = kwargs.get("processId", None)
        code = kwargs.get("code", None)
        avoid_new_login = kwargs.get("avoidNewLogin", False)

        return self.__client.login(username, password, avoid_new_login, process_id, code)

    async def global_position(self) -> GlobalPosition:
        wallet = self.__client.get_wallet()["LW"]["balance"]
        account = Account(total=round(wallet, 2))

        txs = self.scrape_transactions()
        investments = self.__client.get_investments()

        investment_details = []
        for inv_id, inv in investments.items():
            investment_details.append(self.map_investment(txs, inv_id, inv))

        total_invested = round(sum([inv.amount for inv in investment_details]), 2)
        weighted_interest_rate = round(
            (sum([inv.amount * inv.interestRate for inv in investment_details])
             / sum([inv.amount for inv in investment_details])),
            4,
        )
        investments = Investments(
            realStateCF=RealStateCFInvestments(
                invested=total_invested,
                weightedInterestRate=weighted_interest_rate,
                details=investment_details
            )
        )

        return GlobalPosition(
            account=account,
            investments=investments
        )

    def map_investment(self, txs, inv_id, inv):
        opportunity = inv["opportunity"]
        name = opportunity["name"].strip()
        amount = inv["amount"]["current"]
        investments_details = self.__client.get_investment_details(inv_id)

        raw_business_type = opportunity["investment_type_id"]
        business_type = raw_business_type
        if raw_business_type == 2:
            business_type = "LENDING"

        raw_project_type = investments_details["opportunity"]["property_type"]["es"]
        project_type = raw_project_type
        if raw_project_type == "Residencial":
            project_type = "HOUSING"
        elif raw_project_type == "Suelo":
            project_type = "FLOOR"

        state_id = opportunity["state_id"]
        state = "-"
        if state_id == 3:
            state = "FUNDED"

        last_invest_date = max(
            [tx["date"] for tx in txs if "investment" == tx["category"] and tx["name"] == name],
            default=None)

        last_invest_date = last_invest_date.replace(tzinfo=tzlocal())

        periods = inv["periods"]
        ordinary_period = periods["ordinary"]
        extended_period = periods.get("prorroga", None)
        if extended_period:
            extended_period = extended_period["plazo"]

        return RealStateCFDetail(
            name=name,
            amount=round(amount, 2),
            currency="EUR",
            currencySymbol="€",
            interestRate=round(float(opportunity["annual_profitability"]) / 100, 4),
            lastInvestDate=last_invest_date,
            months=ordinary_period["plazo"],
            potentialExtension=extended_period,
            type=project_type,
            businessType=business_type,
            state=state,
        )

    async def transactions(self, registered_txs: set[str]) -> Transactions:
        raw_transactions = self.scrape_transactions()

        txs = []
        for tx in raw_transactions:
            tx_type_raw = tx["category"]
            if tx_type_raw not in ["investment"]:
                continue
            tx_type = TxType.INVESTMENT if "investment" == tx_type_raw else None
            if not tx_type:
                print(f"Skipping tx {tx['name']} with type {tx_type_raw}")
                continue

            name = tx["name"]
            amount = round(tx["amount"], 2)
            tx_date = tx["date"].replace(tzinfo=tzlocal())

            ref = self.calc_tx_id(name, tx_date, amount, tx_type)

            if ref in registered_txs:
                continue

            txs.append(RealStateCFTx(
                id=ref,
                name=name,
                amount=amount,
                currency="EUR",
                currencySymbol="€",
                type=tx_type,
                date=tx_date,
                entity=Entity.WECITY,
                productType=ProductType.REAL_STATE_CF,
                fees=0,
                retentions=0,
                interests=0,
                netAmount=amount,
                sourceType=SourceType.REAL
            ))

        return Transactions(investment=txs)

    def scrape_transactions(self):
        raw_txs = self.__client.get_transactions()

        txs = []
        for tx in raw_txs:
            txs.append(
                {
                    "date": datetime.fromtimestamp(tx["date"]),
                    "category": tx["type"],
                    "name": tx["title"].strip(),
                    "amount": round(tx["amount"], 2)
                }
            )

        return sorted(txs, key=lambda txx: (txx["date"], txx["amount"]))

    @staticmethod
    def calc_tx_id(inv_name: str,
                   tx_date: date,
                   amount: float,
                   tx_type: TxType) -> str:
        return sha1(
            f"W_{inv_name}_{tx_date.isoformat()}_{amount}_{tx_type}".encode("UTF-8")).hexdigest()

    async def historical_position(self) -> HistoricalPosition:
        txs = self.scrape_transactions()
        investments = self.__client.get_investments()

        investment_details = []
        for inv_id, inv in investments.items():
            investment_details.append(self.map_investment(txs, inv_id, inv))

        return HistoricalPosition(
            investments=Investments(
                realStateCF=RealStateCFInvestments(
                    invested=0,
                    weightedInterestRate=0,
                    details=investment_details
                )
            )
        )
