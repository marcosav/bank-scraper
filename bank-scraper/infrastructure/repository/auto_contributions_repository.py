from pymongo import MongoClient

from application.ports.auto_contributions_port import AutoContributionsPort
from domain.auto_contributions import AutoContributions, PeriodicContribution
from domain.bank import Bank
from infrastructure.repository.bank_data_repository import map_serializable


def map_contributions_to_domain(data: dict) -> AutoContributions:
    periodic_contributions = []

    periodic_contributions_data = data.get("periodic", [])
    for contribution_data in periodic_contributions_data:
        periodic_contributions.append(
            PeriodicContribution(**contribution_data)
        )

    return AutoContributions(
        periodic=periodic_contributions,
    )


class AutoContributionsRepository(AutoContributionsPort):

    def __init__(self, client: MongoClient, db_name: str):
        self.client = client
        self.db = self.client[db_name]
        self.collection = self.db["auto_contributions"]

    def save(self, source: Bank, data: AutoContributions):
        self.collection.update_one(
            {"bank": source.name},
            {"$set": map_serializable(data)},
            upsert=True,
        )

    def get_all_grouped_by_source(self) -> dict[str, AutoContributions]:
        pipeline = [
            {
                "$group": {
                    "_id": "$bank",
                    "data": {"$first": "$$ROOT"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "bank": "$_id",
                    "data": {
                        "$arrayToObject": {
                            "$filter": {
                                "input": {"$objectToArray": "$data"},
                                "cond": {"$ne": ["$$this.k", "_id"]}
                            }
                        }
                    }
                }
            }
        ]
        result = list(self.collection.aggregate(pipeline))

        mapped_result = {}
        for entry in result:
            bank_name = entry["bank"]
            raw_data = entry["data"]

            bank_data = map_contributions_to_domain(raw_data)

            mapped_result[bank_name] = bank_data

        return mapped_result
