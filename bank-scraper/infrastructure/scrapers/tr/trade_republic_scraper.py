import re
from datetime import datetime

from application.ports.entity_scraper import EntityScraper
from domain.currency_symbols import CURRENCY_SYMBOL_MAP
from domain.financial_entity import Entity
from domain.global_position import StockDetail, Investments, Account, GlobalPosition, StockInvestments, SourceType
from domain.transactions import Transactions, StockTx, ProductType, TxType, AccountTx
from infrastructure.scrapers.tr.trade_republic_client import TradeRepublicClient


def parse_sub_section_float(section: dict):
    if not section:
        return 0.0

    value = section["detail"]["text"]
    return parse_float(value)


def parse_float(value: str):
    value = value.replace("\xa0", "").strip()
    value = value.replace(",", "")
    numeric_value = re.sub(r"[^\d.]", "", value)
    return float(numeric_value)


def get_section(d, title):
    for section in d:
        if title.lower() in section.get("title", "").lower():
            return section
    return None


def map_investment_tx(raw_tx: dict, date: datetime) -> StockTx:
    name = raw_tx["title"].strip()
    amount_obj = raw_tx["amount"]
    currency = amount_obj["currency"]
    net_amount_val = round(amount_obj["value"], 2)
    net_amount = abs(net_amount_val)

    tx_type = TxType.SELL if net_amount_val > 0 else TxType.BUY

    detail_sections = raw_tx["details"]["sections"]

    isin = detail_sections[0]["action"]["payload"]
    tx_section = get_section(detail_sections, "Transaction")["data"]
    shares = parse_sub_section_float(get_section(tx_section, "Shares"))
    taxes = parse_sub_section_float(get_section(tx_section, "Tax"))
    fees = parse_sub_section_float(get_section(tx_section, "Fee"))

    amount = abs(net_amount_val + fees + taxes)
    # Provided price sometimes doesn't match with the executed price
    price = round(amount / shares, 4)

    return StockTx(
        id=raw_tx["id"],
        name=name,
        amount=amount,
        currency=currency,
        currencySymbol=CURRENCY_SYMBOL_MAP.get(currency, currency),
        type=tx_type,
        date=date,
        entity=Entity.TRADE_REPUBLIC,
        netAmount=net_amount,
        isin=isin,
        ticker=None,
        shares=shares,
        price=price,
        market=None,
        fees=fees + taxes,
        retentions=0,
        orderDate=None,
        productType=ProductType.STOCK_ETF,
        sourceType=SourceType.REAL,
        linkedTx=None
    )


def map_account_tx(raw_tx: dict, date: datetime) -> AccountTx:
    title = raw_tx["title"].strip()
    subtitle = raw_tx["subtitle"].strip().replace("\xa0", "")
    name = f"{title} - {subtitle}"
    amount_obj = raw_tx["amount"]
    currency = amount_obj["currency"]

    detail_sections = raw_tx["details"]["sections"]

    ov_section = get_section(detail_sections, "Overview")["data"]
    avg_balance = parse_sub_section_float(get_section(ov_section, "Average balance"))
    annual_rate = parse_sub_section_float(get_section(ov_section, "Annual rate"))

    if not annual_rate:
        annual_rate = parse_float(subtitle.split(" ")[0])

    if raw_tx["eventType"] == "INTEREST_PAYOUT":
        tx_section = get_section(detail_sections, "Transaction")["data"]
        accrued = parse_sub_section_float(get_section(tx_section, "Accrued"))
        taxes = parse_sub_section_float(get_section(tx_section, "Tax"))
    else:
        taxes = 0
        accrued = amount_obj["value"]

    return AccountTx(
        id=raw_tx["id"],
        name=name,
        amount=round(accrued, 2),
        currency=currency,
        currencySymbol=CURRENCY_SYMBOL_MAP.get(currency, currency),
        fees=0,
        retentions=round(taxes, 2),
        interestRate=round(annual_rate / 100, 4),
        avgBalance=round(avg_balance, 2),
        type=TxType.INTEREST,
        date=date,
        entity=Entity.TRADE_REPUBLIC,
        sourceType=SourceType.REAL
    )


class TradeRepublicScraper(EntityScraper):
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"

    def __init__(self):
        self.__client = TradeRepublicClient()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        phone, pin = credentials
        process_id = kwargs.get("processId", None)
        code = kwargs.get("code", None)
        avoid_new_login = kwargs.get("avoidNewLogin", False)

        return self.__client.login(phone, pin, avoid_new_login, process_id, code)

    async def instrument_mapper(self, stock: dict, currency: str):
        isin = stock["instrumentId"]
        average_buy = round(float(stock["averageBuyIn"]), 4)
        shares = float(stock["netSize"])
        market_value = round(float(stock["netValue"]), 4)
        initial_investment = round(average_buy * shares, 4)

        details = await self.__client.get_details(isin)
        type_id = details.instrument["typeId"].upper()
        name = details.instrument["name"]
        ticker = details.instrument["homeSymbol"]
        subtype = ""

        if type_id == "FUND":
            type_id = "ETF"

        elif type_id == "STOCK":
            name = details.stock_details["company"]["name"]
            ticker = details.stock_details["company"]["tickerSymbol"]

        elif type_id == "BOND":
            name = ""
            subtype = details.instrument["bondInfo"]["issuerClassification"]
            interest_rate = details.instrument["bondInfo"]["interestRate"]
            maturity = datetime.strptime(details.instrument["bondInfo"]["maturityDate"], "%Y-%m-%d").date()

        if not subtype:
            subtype = type_id

        return StockDetail(
            name=name,
            ticker=ticker,
            isin=isin,
            market=", ".join(stock["exchangeIds"]),
            shares=shares,
            initialInvestment=initial_investment,
            averageBuyPrice=average_buy,
            marketValue=market_value,
            currency=currency,
            currencySymbol=CURRENCY_SYMBOL_MAP.get(currency, currency),
            type=type_id,
            subtype=subtype
        )

    async def global_position(self) -> GlobalPosition:
        portfolio = await self.__client.get_portfolio()

        currency = portfolio.cash[0]["currencyId"]
        cash_total = portfolio.cash[0]["amount"]

        investments = []
        for position in portfolio.portfolio["positions"]:
            investment = await self.instrument_mapper(position, currency)
            investments.append(investment)

        await self.__client.close()

        initial_investment = round(
            sum(map(lambda x: x.initialInvestment, investments)), 4
        )
        market_value = round(sum(map(lambda x: x.marketValue, investments)), 4)

        investments_data = Investments(
            stocks=StockInvestments(
                initialInvestment=initial_investment,
                marketValue=market_value,
                details=investments,
            )
        )

        return GlobalPosition(
            account=Account(
                total=cash_total,
            ),
            investments=investments_data,
        )

    async def transactions(self, registered_txs: set[str]) -> Transactions:
        raw_txs = await self.__client.get_transactions(already_registered_ids=registered_txs)
        await self.__client.close()

        investment_txs = []
        account_txs = []
        for raw_tx in raw_txs:
            status = raw_tx.get("status", None)
            event_type = raw_tx.get("eventType", None)
            if not (status == "EXECUTED" and event_type in ["TRADE_INVOICE", "ORDER_EXECUTED", "INTEREST_PAYOUT",
                                                            "INTEREST_PAYOUT_CREATED"]):
                continue

            date = datetime.strptime(raw_tx["timestamp"], self.DATETIME_FORMAT)

            if event_type in ["INTEREST_PAYOUT", "INTEREST_PAYOUT_CREATED"]:
                account_txs.append(map_account_tx(raw_tx, date))
            else:
                investment_txs.append(map_investment_tx(raw_tx, date))

        return Transactions(investment=investment_txs, account=account_txs)
