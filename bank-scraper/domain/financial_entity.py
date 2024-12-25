from enum import Enum


class Entity(str, Enum):
    MY_INVESTOR = "MY_INVESTOR",
    UNICAJA = "UNICAJA",
    TRADE_REPUBLIC = "TRADE_REPUBLIC"
    URBANITAE = "URBANITAE"
    WECITY = "WECITY"
    SEGO = "SEGO"


class Feature(str, Enum):
    POSITION = "POSITION",
    AUTO_CONTRIBUTIONS = "AUTO_CONTRIBUTIONS",
    TRANSACTIONS = "TRANSACTIONS"


ENTITY_DETAILS = {
    Entity.MY_INVESTOR: {
        "id": Entity.MY_INVESTOR,
        "name": "MyInvestor",
        "features": [Feature.POSITION, Feature.AUTO_CONTRIBUTIONS, Feature.TRANSACTIONS]
    },
    Entity.UNICAJA: {
        "id": Entity.UNICAJA,
        "name": "Unicaja",
        "features": [Feature.POSITION]
    },
    Entity.TRADE_REPUBLIC: {
        "id": Entity.TRADE_REPUBLIC,
        "name": "Trade Republic",
        "features": [Feature.POSITION, Feature.TRANSACTIONS],
        "pin": {
            "positions": 4
        }
    },
    Entity.URBANITAE: {
        "id": Entity.URBANITAE,
        "name": "Urbanitae",
        "features": [Feature.POSITION, Feature.TRANSACTIONS]
    },
    Entity.WECITY: {
        "id": Entity.WECITY,
        "name": "Wecity",
        "features": [Feature.POSITION, Feature.TRANSACTIONS],
        "pin": {
            "positions": 6
        }
    },
    Entity.SEGO: {
        "id": Entity.SEGO,
        "name": "SEGO",
        "features": [Feature.POSITION, Feature.TRANSACTIONS]
    }
}
