import copy
from datetime import date, datetime
from hashlib import sha1
from typing import Optional

from pytz import utc

from application.ports.entity_scraper import EntityScraper
from domain.currency_symbols import SYMBOL_CURRENCY_MAP
from domain.financial_entity import Entity
from domain.global_position import FactoringDetail, FactoringInvestments, Investments, \
    GlobalPosition, SourceType, Account, HistoricalPosition
from domain.transactions import Transactions, TxType, ProductType, FactoringTx
from infrastructure.scrapers.sego.sego_client import SegoAPIClient

DATETIME_FORMAT = "%d/%m/%Y %H:%M"
TAG_TIME_FORMAT = "%H:%M:%S"

ACTIVE_SEGO_STATES = ["disputa", "gestionando-cobro", "no-llego-fecha-cobro"]
FINISHED_SEGO_STATES = frozenset({"cobrado", "fallido"})


def parse_tag(tag: str) -> dict:
    tag_props = {}
    for e in tag.split(";"):
        k, v = e.split(":", 1)
        tag_props[k] = v

    return tag_props


def map_txs(ref: str,
            tx: dict,
            name: str,
            tx_type: TxType,
            fee: float,
            tax: float,
            interests: float) -> Optional[FactoringTx]:
    tx_date = tx["date"]
    currency_symbol = tx["currencySymbol"]
    currency = tx["currency"]
    base_amount = tx["amount"]

    amount = base_amount + interests
    net_amount = base_amount + interests - fee - tax

    return FactoringTx(
        id=ref,
        name=name,
        amount=amount,
        currency=currency,
        currencySymbol=currency_symbol,
        type=tx_type,
        date=tx_date,
        entity=Entity.SEGO,
        productType=ProductType.FACTORING,
        fees=fee,
        retentions=tax,
        interests=interests,
        netAmount=net_amount,
        sourceType=SourceType.REAL)


class SegoScraper(EntityScraper):
    SEGO_FEE = 0.2

    def __init__(self):
        self.__client = SegoAPIClient()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        username, password = credentials
        return self.__client.login(username, password)

    async def global_position(self) -> GlobalPosition:
        raw_wallet = self.__client.get_wallet()
        wallet_amount = raw_wallet["importe"]
        account = Account(total=round(wallet_amount, 2))

        investment_movements = self._get_normalized_movements(["TRANSFER"], ["Inversión Factoring"])

        raw_sego_investments = self.__client.get_investments() + self.__client.get_pending_investments()
        active_sego_investments = [
            investment for investment in raw_sego_investments if
            investment["tipoEstadoOperacionCodigo"] in ACTIVE_SEGO_STATES
        ]

        factoring_investments = []
        for investment in active_sego_investments:
            factoring_investments.append(self.map_investment(investment_movements, investment))

        total_invested = sum([investment.amount for investment in factoring_investments])
        weighted_net_interest_rate = round(
            (
                    sum(
                        [
                            investment.amount * investment.netInterestRate
                            for investment in factoring_investments
                        ]
                    )
                    / total_invested
            ),
            4,
        )

        sego_data = FactoringInvestments(
            invested=total_invested,
            weightedInterestRate=weighted_net_interest_rate,
            details=factoring_investments,
        )

        return GlobalPosition(
            account=account,
            investments=Investments(
                factoring=sego_data,
            ),
        )

    def map_investment(self, investment_movements, investment):
        raw_proj_type = investment["tipoOperacionCodigo"]
        proj_type = None
        if raw_proj_type == "admin-publica":
            proj_type = "PUBLIC_ADMIN"
        elif raw_proj_type == "con-seguro":
            proj_type = "INSURED"
        elif raw_proj_type == "sin-seguro":
            proj_type = "NON_INSURED"

        raw_state = investment["tipoEstadoOperacionCodigo"]
        state = "disputado"
        if raw_state == "no-llego-fecha-cobro":
            state = "MATURITY_NOT_REACHED"
        elif raw_state == "gestionando-cobro":
            state = "MANAGING_COLLECTION"
        elif raw_state == "fallido":
            state = "FAILED"
        elif raw_state == "cobrado":
            state = "COLLECTED"

        name = investment["nombreOperacion"].strip()
        interest_rate = investment["tasaInteres"]

        last_invest_date = next(
            (
                movement["date"]
                for movement in investment_movements
                if name in movement["mensajeCompleto"]
            ),
            None,
        )

        return FactoringDetail(
            name=name,
            amount=round(float(investment["importe"]), 2),
            currency="EUR",
            currencySymbol="€",
            interestRate=round(interest_rate / 100, 4),
            netInterestRate=round(interest_rate * (1 - self.SEGO_FEE) / 100, 4),
            lastInvestDate=last_invest_date,
            maturity=(
                date.fromisoformat(investment["fechaDevolucion"][:10])
                if investment["fechaDevolucion"]
                else None
            ),
            type=proj_type,
            state=state
        )

    def _get_normalized_movements(self, types=None, subtypes=None) -> list[dict]:
        if subtypes is None:
            subtypes = []
        if types is None:
            types = []

        raw_movements = copy.deepcopy(self.__client.get_movements())
        normalized_movs = []
        for movement in raw_movements:
            if (not types or movement["type"] in types) and (not subtypes or movement["tipo"] in subtypes):
                tag = movement.get("tag", None)
                parsed_tag_time = None
                if tag:
                    tag_props = parse_tag(tag)
                    if raw_tag_time := tag_props.get("date", None):
                        parsed_tag_time = datetime.strptime(raw_tag_time.split(" ")[-1], TAG_TIME_FORMAT)

                mov_datetime = datetime.strptime(movement["creationDate"], DATETIME_FORMAT)
                if parsed_tag_time:
                    mov_datetime = mov_datetime.replace(second=parsed_tag_time.second)

                movement["date"] = mov_datetime.replace(tzinfo=utc)

                currency_symbol = movement["amount"][-1]
                currency = SYMBOL_CURRENCY_MAP.get(currency_symbol, "EUR")
                raw_formated_amount = movement["amount"]
                movement["amount"] = float(raw_formated_amount[2:-1].replace(".", "").replace(",", "."))
                movement["currency"] = currency
                movement["currencySymbol"] = currency_symbol

                normalized_movs.append(movement)

        return sorted(normalized_movs, key=lambda m: m["date"])

    async def transactions(self, registered_txs: set[str]) -> Transactions:
        factoring_txs = self.scrape_factoring_txs(registered_txs)

        return Transactions(investment=factoring_txs)

    def scrape_factoring_txs(self, registered_txs: set[str]) -> list[FactoringTx]:
        completed_investments = self.__client.get_investments(FINISHED_SEGO_STATES)

        txs = self._get_normalized_movements(["TRANSFER"], ["Inversión Factoring", "Devolución Capital"])

        investment_txs = []

        for tx in txs:
            tag_props = parse_tag(tx["tag"]) if tx.get("tag", None) else None
            if not tag_props:
                print(f"No tag in SEGO transaction: {tx}")
                continue

            investment_name = tag_props["operacion"].strip()
            tx_date = tx["date"]
            raw_tx_type = tx["tipo"].lower()
            tx_type = TxType.INVESTMENT if "inversión" in raw_tx_type else TxType.MATURITY

            amount = tx["amount"]
            ref = self.calc_sego_tx_id(investment_name, tx_date, amount, tx_type)
            if ref in registered_txs:
                continue

            fee, tax, interests = 0, 0, 0
            if tx_type == TxType.MATURITY:
                matching_investment = next(
                    (investment for investment in completed_investments if
                     investment["nombreOperacion"].strip() == investment_name),
                    None,
                )
                fee = round(float(matching_investment["comision"]), 2)
                tax = round(float(matching_investment["retencion"]), 2)
                interests = round(
                    float(matching_investment["gananciasOrdinarias"] + matching_investment["gananciasExtraOrdinarias"]),
                    2)

            stored_tx = map_txs(ref, tx, investment_name, tx_type, fee, tax, interests)
            investment_txs.append(stored_tx)

        return investment_txs

    @staticmethod
    def calc_sego_tx_id(inv_name: str,
                        tx_date: datetime,
                        amount: float,
                        tx_type: TxType) -> str:
        return sha1(
            f"S_{inv_name}_{tx_date.isoformat()}_{amount}_{tx_type}".encode("UTF-8")).hexdigest()

    async def historical_position(self) -> HistoricalPosition:
        investment_movements = self._get_normalized_movements(["TRANSFER"], ["Inversión Factoring"])

        raw_sego_investments = self.__client.get_investments() + self.__client.get_pending_investments()
        active_sego_investments = [
            investment for investment in raw_sego_investments
        ]

        factoring_investments = []
        for investment in active_sego_investments:
            factoring_investments.append(self.map_investment(investment_movements, investment))

        return HistoricalPosition(
            investments=Investments(
                factoring=FactoringInvestments(
                    invested=0,
                    weightedInterestRate=0,
                    details=factoring_investments
                )
            )
        )
