import datetime

from dateutil.tz import tzlocal

from domain.bank import Bank

RSCF_SHEET = "Real State CF"


def update_rscf(sheet, global_position: dict, sheet_id: str):
    stock_rows = map_investments(global_position)

    request = sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"{RSCF_SHEET}!A1",
        valueInputOption="RAW",
        body={"values": stock_rows},
    )

    request.execute()


def map_investments(global_position):
    return [
        [None, datetime.datetime.now(tzlocal()).isoformat()],
        [],
        *map_rscf_urbanitae_investments(global_position),
        *map_rscf_wecity_investments(global_position),
        *[["" for _ in range(20)] for _ in range(20)],
    ]


def map_rscf_urbanitae_investments(global_position):
    try:
        details = global_position.get(Bank.URBANITAE.name, None).investments.realStateCF.details
    except AttributeError:
        return []

    return [
        [
            i.name,
            i.amount,
            "EUR",
            i.type,
            i.businessType,
            i.interestRate,
            i.lastInvestDate.isoformat()[:10],
            i.months,
            i.potentialExtension,
            i.state,
            "URBANITAE",
        ]
        for i in details
    ]


def map_rscf_wecity_investments(global_position):
    try:
        details = global_position.get(Bank.WECITY.name, None).investments.realStateCF.details
    except AttributeError:
        return []

    return [
        [
            i.name,
            i.amount,
            "EUR",
            i.type,
            i.businessType,
            i.interestRate,
            i.lastInvestDate.isoformat()[:10],
            i.months,
            i.potentialExtension,
            i.state,
            "WECITY",
        ]
        for i in details
    ]
