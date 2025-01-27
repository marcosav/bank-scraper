from datetime import datetime, date

from dateutil.relativedelta import relativedelta

from application.ports.entity_scraper import EntityScraper
from domain.global_position import Account, Cards, Card, Mortgage, GlobalPosition, AccountAdditionalData
from infrastructure.scrapers.unicaja.unicaja_client import UnicajaClient


class UnicajaScraper(EntityScraper):

    def __init__(self):
        self.__client = UnicajaClient()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        username, password = credentials
        return self.__client.login(username, password)

    async def global_position(self) -> GlobalPosition:
        accounts_response = self.__client.list_accounts()
        account_data_raw = accounts_response["cuentas"][0]

        account_balance = account_data_raw["saldo"]["cantidad"]
        account_available = account_data_raw["disponible"]["cantidad"]
        account_allowed_overdraft = account_data_raw["importeExcedido"]["cantidad"]
        account_pending_payments = round(
            account_balance + account_allowed_overdraft - account_available, 2
        )
        last_week_date = date.today() - relativedelta(weeks=1)
        account_pending_transfers_raw = self.__client.get_transfers_historic(from_date=last_week_date)
        account_pending_transfer_amount = 0
        if "noDatos" not in account_pending_transfers_raw:
            account_pending_transfer_amount = sum(
                transfer["importe"]["cantidad"] for transfer in account_pending_transfers_raw["transferencias"] if
                transfer["estadoTransferencia"] == "P"
            )

        account_data = Account(
            total=account_balance,
            retained=account_pending_payments,
            interest=0,  # :(
            additionalData=AccountAdditionalData(
                pendingTransfers=account_pending_transfer_amount
            )
        )

        card_list = self.__client.get_cards()
        debit_card_raw = card_list["tarjetas"][0]
        credit_card_raw = card_list["tarjetas"][1]

        cards_data = Cards(
            credit=Card(
                limit=credit_card_raw["limite"]["cantidad"],
                used=credit_card_raw["limite"]["cantidad"] - credit_card_raw["disponible"]["cantidad"],
            ),
            debit=Card(
                limit=debit_card_raw["limite"]["cantidad"],
                used=debit_card_raw["pagadoMesActual"]["cantidad"],
            ),
        )

        self.__client.get_loans()
        mortgage_response = self.__client.get_loan(p="2", ppp="001")
        mortgage_data = None
        # When its near invoicing period, the mortgage is not returned
        if mortgage_response:
            mortgage_data = Mortgage(
                currentInstallment=mortgage_response["currentInstallment"],
                loanAmount=mortgage_response["loanAmount"],
                principalPaid=mortgage_response["principalPaid"],
                principalOutstanding=mortgage_response["principalOutstanding"],
                interestRate=mortgage_response["interestRate"],
                nextPaymentDate=datetime.strptime(mortgage_response["nextPaymentDate"], "%Y-%m-%d").date(),
            )

        return GlobalPosition(
            account=account_data,
            cards=cards_data,
            mortgage=mortgage_data,
        )
