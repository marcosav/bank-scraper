from datetime import datetime, timezone

from dateutil.tz import tzlocal
from pymongo import MongoClient

from application.ports.transaction_port import TransactionPort
from domain.bank import Bank
from domain.transactions import Transactions, StockTx, FundTx, BaseInvestmentTx, SegoTx, TxProductType, RealStateCFTx
from infrastructure.repository.bank_data_repository import map_serializable


def map_transactions(result) -> Transactions:
    return Transactions(
        investment=[
            map_investment_tx(doc)
            for doc in result
        ]
    )


def map_investment_tx(doc: dict) -> BaseInvestmentTx:
    if doc["productType"] == "STOCK_ETF":
        return StockTx(
            **{**doc,
               'retentions': doc.get("retentions", None)}
        )
    elif doc["productType"] == "FUND":
        return FundTx(
            **{**doc,
               'retentions': doc.get("retentions", None)}
        )
    elif doc["productType"] == "REAL_STATE_CF":
        return RealStateCFTx(**doc)

    elif doc["productType"] == "SEGO":
        return SegoTx(**doc)

    raise ValueError(f"Unknown product type: {doc['productType']}")


class TransactionRepository(TransactionPort):

    def __init__(self, client: MongoClient, db_name: str):
        self.client = client
        self.db = self.client[db_name]
        self.collection = self.db["transactions"]

    def save(self, source: Bank, data: Transactions):
        txs = data.investment
        if not txs:
            return
        self.collection.insert_many(
            [
                {**map_serializable(tx), "createdAt": datetime.now(tzlocal())}
                for tx in txs
            ]
        )

    def get_all(self) -> Transactions:
        result = self.collection.find({}, {"_id": 0, "createdAt": 0}).sort("date", 1)
        return Transactions(
            investment=[
                map_investment_tx(doc)
                for doc in result
            ]
        )

    def get_by_product(self, product_types: list[TxProductType]) -> Transactions:
        product_types = [product_type.value for product_type in product_types]

        result = self.collection.find(
            {"productType": {"$in": product_types}},
            {"_id": 0, "createdAt": 0}
        ).sort("date", 1)

        return map_transactions(result)

    def get_ids_by_source(self, source: Bank) -> set[str]:
        pipeline = [
            {"$match": {"source": source.name}},
            {"$project": {"_id": 0, "id": 1}},
        ]
        result = self.collection.aggregate(pipeline)
        return {doc["id"] for doc in result}

    def get_last_created_grouped_by_source(self) -> dict[str, datetime]:
        pipeline = [
            {"$sort": {"createdAt": -1}},
            {
                "$group": {
                    "_id": "$source",
                    "lastCreatedAt": {"$first": "$createdAt"}
                }
            },
            {"$project": {"_id": 0, "source": "$_id", "lastCreatedAt": 1}}
        ]
        result = list(self.collection.aggregate(pipeline))
        return {doc["source"]: doc["lastCreatedAt"].replace(tzinfo=timezone.utc) for doc in result}
