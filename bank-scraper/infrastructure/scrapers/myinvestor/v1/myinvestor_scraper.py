from datetime import date, datetime

from itertools import chain

from application.ports.entity_scraper import EntityScraper
from domain.auto_contributions import PeriodicContribution, ContributionFrequency, AutoContributions
from domain.currency_symbols import CURRENCY_SYMBOL_MAP, SYMBOL_CURRENCY_MAP
from domain.financial_entity import Entity
from domain.global_position import Account, AccountAdditionalData, Cards, Card, StockDetail, StockInvestments, \
    FundDetail, \
    FundInvestments, Investments, GlobalPosition, PositionAdditionalData, \
    Deposit, Deposits, SourceType
from domain.transactions import Transactions, FundTx, TxType, StockTx, ProductType
from infrastructure.scrapers.myinvestor.v1.myinvestor_client import MyInvestorAPIV1Client

OLD_DATE_FORMAT = "%d/%m/%Y"
TIME_FORMAT = "%H:%M:%S"
OLD_DATE_TIME_FORMAT = OLD_DATE_FORMAT + " " + TIME_FORMAT
DASH_OLD_DATE_TIME_FORMAT = "%Y-%m-%d " + TIME_FORMAT


class MyInvestorScraperV1(EntityScraper):

    def __init__(self):
        self.__client = MyInvestorAPIV1Client()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        username, password = credentials
        return self.__client.login(username, password)

    async def global_position(self) -> GlobalPosition:
        maintenance = self.__client.check_maintenance()

        account_id, securities_account_id, account_data = self.scrape_account()

        cards_data = self.scrape_cards(account_id)

        investments_data = self.scrape_investments(securities_account_id)

        return GlobalPosition(
            account=account_data,
            cards=cards_data,
            investments=investments_data,
            additionalData=PositionAdditionalData(maintenance=maintenance["enMantenimeinto"]),
        )

    async def auto_contributions(self) -> AutoContributions:
        return self.scrape_auto_contributions()

    async def transactions(self, registered_txs: set[str]) -> Transactions:
        accounts = self.__client.get_accounts()
        securities_account_id = accounts[0]["idCuentaValores"]

        fund_txs, stock_txs = [], []

        try:
            fund_txs = self.scrape_fund_txs(securities_account_id, registered_txs)
        except Exception as e:
            print(f"Error getting fund txs: {e}")

        try:
            stock_txs = self.scrape_stock_txs(securities_account_id, registered_txs)
        except Exception as e:
            print(f"Error getting stock txs: {e}")

        investment_txs = fund_txs + stock_txs

        return Transactions(investment=investment_txs)

    def scrape_account(self):
        accounts = self.__client.get_accounts()

        account_id = accounts[0]["idCuenta"]
        securities_account_id = accounts[0]["idCuentaValores"]

        current_interest_rate = None
        avg_interest_rate = None
        remuneration_type = None

        try:
            remuneration_details = self.__client.get_account_remuneration(account_id)
            current_interest_rate = round(remuneration_details["taePromocion"] / 100, 4)
            avg_interest_rate = round(
                remuneration_details["taeMediaCalculada"] / 100, 4
            )
            remuneration_type = remuneration_details["tipo"]
        except Exception as e:
            print(f"Error getting account remuneration: {e}")

        return account_id, securities_account_id, Account(
            total=accounts[0]["importeCuenta"],
            retained=accounts[0]["retencionesSaldoCuenta"],
            interest=current_interest_rate,
            additionalData=AccountAdditionalData(
                averageInterestRate=avg_interest_rate,
                remunerationType=remuneration_type,
            ),
        )

    def scrape_cards(self, account_id: str):
        cards = self.__client.get_cards(account_id=account_id)
        credit_card = next(
            (card for card in cards if card["cardType"] == "CREDIT"), None
        )
        debit_card = next((card for card in cards if card["cardType"] == "DEBIT"), None)

        credit_card_tx = self.__client.get_card_transactions(credit_card["cardId"])
        debit_card_tx = self.__client.get_card_transactions(debit_card["cardId"])

        return Cards(
            credit=Card(limit=credit_card_tx["limit"], used=abs(credit_card_tx["consumedMonth"])),
            debit=Card(limit=debit_card_tx["limit"], used=abs(debit_card_tx["consumedMonth"])),
        )

    def scrape_deposits(self):
        deposits_raw = self.__client.get_deposits()
        if not deposits_raw:
            return None

        deposit_list = [
            Deposit(
                name=deposit["depositName"],
                amount=round(deposit["amount"], 2),
                totalInterests=round(deposit["grossInterest"], 2),
                interestRate=round(deposit["tae"] / 100, 4),
                maturity=datetime.strptime(deposit["expirationDate"], "%Y-%m-%dT%H:%M:%S.%fZ").date(),
                creation=datetime.strptime(deposit["creationDate"], "%Y-%m-%dT%H:%M:%S.%fZ").date(),
            )
            for deposit in deposits_raw
        ]

        total_amount = sum([deposit["amount"] for deposit in deposits_raw])
        return Deposits(
            total=total_amount,
            totalInterests=sum([deposit["grossInterest"] for deposit in deposits_raw]),
            weightedInterestRate=round(
                (sum([deposit["amount"] * deposit["tae"] for deposit in deposits_raw])
                 / total_amount) / 100,
                4,
            ),
            details=deposit_list,
        )

    def scrape_investments(self, securities_account_id: str):
        stocks_account = None
        for account in self.__client.get_stocks_summary():
            if account["idCuenta"] == securities_account_id:
                stocks_account = account
                break

        stock_list = []
        if stocks_account:
            stock_list = [
                StockDetail(
                    name=stock["nombre"],
                    ticker=stock["ticker"],
                    isin=stock["isin"],
                    market=stock["codigoMercado"],
                    shares=stock["titulos"],
                    initialInvestment=round(stock["inversionInicial"], 4),
                    averageBuyPrice=round(stock["inversionInicial"] / stock["titulos"], 4),
                    marketValue=round(stock["valorMercado"], 4),
                    currency=stock["divisa"],
                    currencySymbol=CURRENCY_SYMBOL_MAP.get(stock["divisa"], stock["divisa"]),
                    type=stock["tipoProductoBrokerEnum"],
                    subtype=stock.get("codigoTipoActivo"),
                )
                for stock in stocks_account["accionesEtfDtoList"]
            ]

        stock_data = StockInvestments(
            initialInvestment=round(stocks_account["inversionInicial"], 4) if stocks_account else 0,
            marketValue=round(stocks_account["valorMercado"], 4) if stocks_account else 0,
            details=stock_list,
        )

        funds_account = None
        for account in self.__client.get_funds_and_portfolios_summary():
            if (
                    account["idCuenta"] == securities_account_id
                    and account["tipoCuentaEnum"] == "VALORES"
            ):
                funds_account = account
                break

        fund_list = []
        if funds_account:
            all_account_funds = map(
                lambda cat: cat["inversionesDtoList"],
                funds_account["inversionesCuentaValores"].values(),
            )
            raw_fund_list = list(chain(*list(all_account_funds)))
            fund_list = [
                FundDetail(
                    name=fund["nombreInversion"],
                    isin=fund["isin"],
                    market=fund["codigoMercado"],
                    shares=fund["participaciones"],
                    initialInvestment=round(fund["inversionInicial"], 4),
                    averageBuyPrice=round(fund["inversionInicial"] / fund["participaciones"], 4),
                    marketValue=round(fund["valorMercado"], 4),
                    currency=SYMBOL_CURRENCY_MAP.get(
                        fund["divisaValorLiquidativo"], fund["divisaValorLiquidativo"]
                    ),
                    currencySymbol=fund["divisaValorLiquidativo"],
                    lastUpdate=datetime.strptime(fund["fechaCotizacion"], OLD_DATE_FORMAT).date(),
                )
                for fund in raw_fund_list
            ]

        fund_data = FundInvestments(
            initialInvestment=round(funds_account["totalInvertido"], 4) if funds_account else 0,
            marketValue=round(funds_account["valorMercado"], 4) if funds_account else 0,
            details=fund_list,
        )

        deposits = self.scrape_deposits()

        return Investments(
            stocks=stock_data,
            funds=fund_data,
            deposits=deposits,
        )

    def scrape_auto_contributions(self) -> AutoContributions:
        auto_contributions = self.__client.get_auto_contributions()

        def get_frequency(frequency) -> ContributionFrequency:
            return {
                "UNA_SEMANA": ContributionFrequency.WEEKLY,
                "DOS_SEMANAS": ContributionFrequency.BIWEEKLY,
                "UN_MES": ContributionFrequency.MONTHLY,
                "DOS_MESES": ContributionFrequency.BIMONTHLY,
                "TRES_MESES": ContributionFrequency.QUARTERLY,
                "SEIS_MESES": ContributionFrequency.SEMIANNUAL,
                "UN_ANYO": ContributionFrequency.YEARLY,
            }[frequency]

        def get_date(date_str):
            if not date_str:
                return None
            return datetime.strptime(date_str, OLD_DATE_FORMAT).date()

        def get_alias(auto_contribution):
            alias = auto_contribution["alias"]
            if alias:
                return alias
            fund_name = auto_contribution["nombreFondo"]
            if fund_name:
                return fund_name
            return None

        periodic_contributions = [
            PeriodicContribution(
                alias=get_alias(auto_contribution),
                isin=auto_contribution["codigoIsin"],
                amount=round(auto_contribution["importe"], 2),
                since=get_date(auto_contribution["periodicidadAportacionDto"]["fechaDesde"]),
                until=get_date(auto_contribution["periodicidadAportacionDto"]["fechaHasta"]),
                frequency=get_frequency(auto_contribution["periodicidadAportacionDto"]["periodicidad"]),
                active=auto_contribution["estadoAportacionEnum"] == "ACTIVA",
            )
            for auto_contribution in auto_contributions
        ]

        return AutoContributions(
            periodic=periodic_contributions
        )

    def scrape_fund_txs(self, securities_account_id: str, registered_txs: set[str]) -> list[FundTx]:
        raw_fund_orders = self.__client.get_fund_orders(securities_account_id=securities_account_id,
                                                        from_date=date.fromisocalendar(2020, 1, 1))

        fund_txs = []
        for order in raw_fund_orders:
            ref = order["referencia"]

            if ref in registered_txs:
                continue

            raw_order_details = self.__client.get_fund_order_details(ref)
            order_date = datetime.strptime(raw_order_details["fechaOrden"] + " " + raw_order_details["horaOrden"],
                                           OLD_DATE_TIME_FORMAT)
            execution_op = None
            linked_ops = raw_order_details["operacionesAsociadas"]
            if linked_ops:
                execution_op = linked_ops[0]
            execution_date = datetime.strptime(execution_op["fechaHoraEjecucion"], OLD_DATE_TIME_FORMAT)

            raw_operation_type = order["tipoOperacion"]
            if "SUSCRIP" in raw_operation_type:
                operation_type = TxType.BUY
            elif "REEMBOLSO" in raw_operation_type:
                operation_type = TxType.SELL
            else:
                print(f"Unknown operation type: {raw_operation_type}")
                continue

            fund_txs.append(
                FundTx(
                    id=ref,
                    name=order["nombreFondo"].strip(),
                    amount=round(execution_op["efectivoBruto"], 2),
                    netAmount=round(execution_op["efectivoNeto"], 2),
                    currency=SYMBOL_CURRENCY_MAP.get(order["divisa"], order["divisa"]),
                    currencySymbol=order["divisa"],
                    type=operation_type,
                    orderDate=order_date,
                    entity=Entity.MY_INVESTOR,
                    isin=order["codIsin"],
                    shares=round(raw_order_details["titulosEjecutados"], 4),
                    price=round(execution_op["precioBruto"], 4),
                    market=order["mercado"],
                    fees=round(execution_op["comisiones"], 2),
                    retentions=0,
                    date=execution_date,
                    productType=ProductType.FUND,
                    sourceType=SourceType.REAL
                )
            )

        return fund_txs

    def scrape_stock_txs(self, securities_account_id: str, registered_txs: set[str]) -> list[StockTx]:
        raw_stock_orders = self.__client.get_stock_orders(securities_account_id=securities_account_id,
                                                          from_date=date.fromisocalendar(2020, 1, 1),
                                                          completed=False)

        stock_txs = []
        for order in raw_stock_orders:
            ref = order["referencia"]

            if ref in registered_txs:
                break

            raw_order_details = self.__client.get_stock_order_details(ref)
            order_date = datetime.strptime(raw_order_details["fechaOrden"], OLD_DATE_TIME_FORMAT)
            linked_ops = raw_order_details["operacionesAsociadas"]
            if not linked_ops:
                print(f"Order {ref} has no linked operations")
                continue
            execution_op = linked_ops[0]
            execution_date = datetime.strptime(execution_op["fechaHoraEjecucion"], DASH_OLD_DATE_TIME_FORMAT)

            raw_operation_type = order["operacion"]
            if "COMPRA" in raw_operation_type:
                operation_type = TxType.BUY
            elif "VENTA" in raw_operation_type:
                operation_type = TxType.SELL
            else:
                print(f"Unknown operation type: {raw_operation_type}")
                continue

            amount = round(execution_op["efectivoBruto"], 2)
            net_amount = round(execution_op["efectivoNeto"], 2)

            fees = 0
            if operation_type == TxType.BUY:
                # Financial Tx Tax not included in "comisionCorretaje", "comisionMiembroMercado" and "costeCanon"
                fees = net_amount - amount
            elif operation_type == TxType.SELL:
                fees = execution_op["comisionCorretaje"] + execution_op["comisionMiembroMercado"] + execution_op[
                    "costeCanon"]

            stock_txs.append(
                StockTx(
                    id=ref,
                    name=order["nombreInstrumento"].strip(),
                    ticker=order["ticker"],
                    amount=amount,
                    netAmount=net_amount,
                    currency=order["divisa"],
                    currencySymbol=CURRENCY_SYMBOL_MAP.get(order["divisa"], order["divisa"]),
                    type=operation_type,
                    orderDate=order_date,
                    entity=Entity.MY_INVESTOR,
                    isin=raw_order_details["codIsin"],
                    shares=round(raw_order_details["titulosEjecutados"], 4),
                    price=round(execution_op["precioBruto"], 4),
                    market=order["codMercado"],
                    fees=round(fees, 2),
                    retentions=0,
                    date=execution_date,
                    productType=ProductType.STOCK_ETF,
                    sourceType=SourceType.REAL,
                    linkedTx=None
                )
            )

        return stock_txs
