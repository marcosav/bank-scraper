from application.ports.entity_scraper import EntityScraper
from domain.global_position import GlobalPosition, Account, Investments, Crowdlending
from infrastructure.scrapers.mintos.mintos_client import MintosAPIClient


def map_loan_distribution(input_json):
    mapping = {
        "active": {"count_key": "activeCount", "sum_key": "activeSum"},
        "gracePeriod": {"count_key": "delayedWithinGracePeriodCount", "sum_key": "delayedWithinGracePeriodSum"},
        "late1_15": {"count_key": "late115Count", "sum_key": "late115Sum"},
        "late16_30": {"count_key": "late1630Count", "sum_key": "late1630Sum"},
        "late31_60": {"count_key": "late3160Count", "sum_key": "late3160Sum"},
        "default": {"count_key": "defaultCount", "sum_key": "defaultSum"},
        "badDebt": {"count_key": "badDebtCount", "sum_key": "badDebtSum"},
        "recovery": {"count_key": "recoveryCount", "sum_key": "recoverySum"},
        "total": {"count_key": "totalCount", "sum_key": "totalSum"}
    }

    output_json = {}
    for key, value in mapping.items():
        count = input_json.get(value["count_key"], 0)
        sum_value = input_json.get(value["sum_key"], "0")

        output_json[key] = {
            "total": round(float(sum_value), 2),
            "count": count
        }

    return output_json


class MintosScraper(EntityScraper):

    def __init__(self):
        self.__client = MintosAPIClient()

    async def login(self, credentials: tuple, **kwargs) -> dict:
        username, password = credentials
        return await self.__client.login(username, password)

    async def global_position(self) -> GlobalPosition:
        user_json = self.__client.get_user()
        wallet = user_json["aggregates"][0]
        wallet_currency_id = wallet["currency"]
        balance = wallet["accountBalance"]

        overview_json = self.__client.get_overview(wallet_currency_id)
        loans = overview_json["loans"]["value"]

        overview_net_annual_returns_json = self.__client.get_net_annual_returns(wallet_currency_id)
        net_annual_returns = overview_net_annual_returns_json["netAnnualReturns"][str(wallet_currency_id)]

        portfolio_data_json = self.__client.get_portfolio(wallet_currency_id)
        total_investment_distribution = portfolio_data_json["totalInvestmentDistribution"]

        account_data = Account(
            total=round(float(balance), 2)
        )

        return GlobalPosition(
            account=account_data,
            investments=Investments(
                crowdlending=Crowdlending(
                    total=round(float(loans), 2),
                    weightedInterestRate=round(float(net_annual_returns) / 100, 4),
                    distribution=map_loan_distribution(total_investment_distribution),
                    details=[]
                )
            )
        )
