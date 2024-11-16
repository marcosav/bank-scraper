import datetime

from domain.bank import Bank

FUNDS_SHEET = "Funds"


def update_funds(sheet, summary: dict, sheet_id: str):
    fund_rows = map_funds(summary)

    request = sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"{FUNDS_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": fund_rows},
    )

    request.execute()


def map_funds(summary):
    try:
        details = summary.get(Bank.MY_INVESTOR.name, None).investments.funds.details
    except AttributeError:
        return []

    return [
        [None, datetime.datetime.now(datetime.timezone.utc).isoformat()],
        [],
        *[
            [
                fund.name,
                fund.isin,
                fund.market,
                fund.shares,
                fund.initialInvestment,
                fund.averageBuyPrice,
                fund.marketValue,
                fund.currency,
                "MYI",
            ]
            for fund in details
        ],
        *[["" for _ in range(20)] for _ in range(20)],
    ]
