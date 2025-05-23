from datetime import datetime
from typing import Dict, Set, List
from uuid import UUID

from dateutil.tz import tzlocal

from application.ports.transaction_port import TransactionPort
from domain.dezimal import Dezimal
from domain.financial_entity import FinancialEntity
from domain.transactions import (
    Transactions, StockTx, FundTx, BaseInvestmentTx,
    AccountTx, ProductType, TxType, FactoringTx, RealStateCFTx
)
from infrastructure.repository.db.client import DBClient


def _map_account_row(row) -> AccountTx:
    entity = FinancialEntity(
        id=UUID(row["entity_id"]),
        name=row["entity_name"],
        is_real=row["entity_is_real"]
    )

    return AccountTx(
        id=UUID(row["id"]),
        ref=row["ref"],
        name=row["name"],
        amount=Dezimal(row["amount"]),
        currency=row["currency"],
        type=TxType(row["type"]),
        date=datetime.fromisoformat(row["date"]),
        entity=entity,
        is_real=bool(row["is_real"]),
        fees=Dezimal(row["fees"]),
        retentions=Dezimal(row["retentions"]),
        interest_rate=Dezimal(row["interest_rate"]),
        avg_balance=Dezimal(row["avg_balance"])
    )


def _map_investment_row(row) -> BaseInvestmentTx:
    entity = FinancialEntity(
        id=UUID(row["entity_id"]),
        name=row["entity_name"],
        is_real=row["entity_is_real"]
    )

    common = {
        "id": UUID(row["id"]),
        "ref": row["ref"],
        "name": row["name"],
        "amount": Dezimal(row["amount"]),
        "currency": row["currency"],
        "type": TxType(row["type"]),
        "date": datetime.fromisoformat(row["date"]),
        "entity": entity,
        "is_real": bool(row["is_real"]),
        "product_type": ProductType(row["product_type"])
    }

    if row["product_type"] == ProductType.STOCK_ETF.value:
        return StockTx(
            **common,
            isin=row["isin"] if "isin" in row else None,
            ticker=row["ticker"],
            market=row["market"],
            shares=Dezimal(row["shares"]),
            price=Dezimal(row["price"]),
            net_amount=Dezimal(row["net_amount"]),
            fees=Dezimal(row["fees"]),
            retentions=Dezimal(row["retentions"]) if "retentions" in row else None,
            order_date=datetime.fromisoformat(row["order_date"]) if "order_date" in row else None,
            linked_tx=row["linked_tx"]
        )
    elif row["product_type"] == ProductType.FUND.value:
        return FundTx(
            **common,
            isin=row["isin"],
            market=row["market"],
            shares=Dezimal(row["shares"]),
            price=Dezimal(row["price"]),
            net_amount=Dezimal(row["net_amount"]),
            fees=Dezimal(row["fees"]),
            retentions=Dezimal(row["retentions"]) if "retentions" in row else None,
            order_date=datetime.fromisoformat(row["order_date"]) if "order_date" in row else None,
        )
    elif row["product_type"] == ProductType.FACTORING.value:
        return FactoringTx(
            **common,
            net_amount=Dezimal(row["net_amount"]),
            fees=Dezimal(row["fees"]),
            retentions=Dezimal(row["retentions"]),
            interests=Dezimal(row["interests"])
        )
    elif row["product_type"] == ProductType.REAL_STATE_CF.value:
        return RealStateCFTx(
            **common,
            net_amount=Dezimal(row["net_amount"]),
            fees=Dezimal(row["fees"]),
            retentions=Dezimal(row["retentions"]),
            interests=Dezimal(row["interests"])
        )


class TransactionSQLRepository(TransactionPort):

    def __init__(self, client: DBClient):
        self._db_client = client

    def save(self, data: Transactions):
        if data.investment:
            self._save_investment(data.investment)
        if data.account:
            self._save_account(data.account)

    def _save_investment(self, txs: List[BaseInvestmentTx]):
        with self._db_client.tx() as cursor:
            for tx in txs:
                entry = {
                    "id": str(tx.id),
                    "ref": tx.ref,
                    "name": tx.name,
                    "amount": str(tx.amount),
                    "currency": tx.currency,
                    "type": tx.type.value,
                    "date": tx.date.isoformat(),
                    "entity_id": str(tx.entity.id),
                    "is_real": tx.is_real,
                    "product_type": tx.product_type.value,
                    "created_at": datetime.now(tzlocal()).isoformat(),

                    "isin": None,
                    "ticker": None,
                    "market": None,
                    "shares": None,
                    "price": None,
                    "net_amount": None,
                    "fees": None,
                    "retentions": None,
                    "order_date": None,
                    "linked_tx": None,
                    "interests": None
                }

                if isinstance(tx, StockTx):
                    entry.update({
                        "isin": tx.isin,
                        "ticker": tx.ticker,
                        "market": tx.market,
                        "shares": str(tx.shares),
                        "price": str(tx.price),
                        "net_amount": str(tx.net_amount),
                        "fees": str(tx.fees),
                        "retentions": str(tx.retentions) if tx.retentions else None,
                        "order_date": tx.order_date.isoformat() if tx.order_date else None,
                        "linked_tx": tx.linked_tx
                    })
                elif isinstance(tx, FundTx):
                    entry.update({
                        "isin": tx.isin,
                        "market": tx.market,
                        "shares": str(tx.shares),
                        "price": str(tx.price),
                        "net_amount": str(tx.net_amount),
                        "fees": str(tx.fees),
                        "retentions": str(tx.retentions) if tx.retentions else None,
                        "order_date": tx.order_date.isoformat() if tx.order_date else None,
                    })
                elif isinstance(tx, (FactoringTx, RealStateCFTx)):
                    entry.update({
                        "net_amount": str(tx.net_amount),
                        "fees": str(tx.fees),
                        "retentions": str(tx.retentions),
                        "interests": str(tx.interests)
                    })

                cursor.execute(
                    """
                    INSERT INTO investment_transactions (id, ref, name, amount, currency, type, date,
                                                         entity_id, is_real, product_type, created_at,
                                                         isin, ticker, market, shares, price, net_amount,
                                                         fees, retentions, order_date, linked_tx, interests)
                    VALUES (:id, :ref, :name, :amount, :currency, :type, :date,
                            :entity_id, :is_real, :product_type, :created_at,
                            :isin, :ticker, :market, :shares, :price, :net_amount,
                            :fees, :retentions, :order_date, :linked_tx, :interests)
                    """,
                    entry
                )

    def _save_account(self, txs: List[AccountTx]):
        with self._db_client.tx() as cursor:
            for tx in txs:
                cursor.execute(
                    """
                    INSERT INTO account_transactions (id, ref, name, amount, currency, type, date,
                                                      entity_id, is_real, created_at,
                                                      fees, retentions, interest_rate, avg_balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(tx.id),
                        tx.ref,
                        tx.name,
                        str(tx.amount),
                        tx.currency,
                        tx.type.value,
                        tx.date.isoformat(),
                        str(tx.entity.id),
                        tx.is_real,
                        datetime.now(tzlocal()).isoformat(),
                        str(tx.fees),
                        str(tx.retentions),
                        str(tx.interest_rate),
                        str(tx.avg_balance)
                    )
                )

    def get_all(self) -> Transactions:
        return Transactions(
            investment=self._get_investment_txs(),
            account=self._get_account_txs()
        )

    def _get_investment_txs(self) -> List[BaseInvestmentTx]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT it.*, e.name AS entity_name, e.id AS entity_id, e.is_real AS entity_is_real
                           FROM investment_transactions it
                                    JOIN financial_entities e ON it.entity_id = e.id
                           """)
            return [_map_investment_row(row) for row in cursor.fetchall()]

    def _get_account_txs(self) -> List[AccountTx]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT at.*, e.name AS entity_name, e.id AS entity_id, e.is_real AS entity_is_real
                           FROM account_transactions at
                                    JOIN financial_entities e ON at.entity_id = e.id
                           """)
            return [_map_account_row(row) for row in cursor.fetchall()]

    def _get_investment_txs_by_entity(self, entity_id: UUID) -> List[BaseInvestmentTx]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT it.*, e.name AS entity_name, e.id AS entity_id, e.is_real AS entity_is_real
                           FROM investment_transactions it
                                    JOIN financial_entities e ON it.entity_id = e.id
                           WHERE it.entity_id = ?
                           """, (str(entity_id),))
            return [_map_investment_row(row) for row in cursor.fetchall()]

    def _get_account_txs_by_entity(self, entity_id: UUID) -> List[AccountTx]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT at.*, e.name AS entity_name, e.id AS entity_id, e.is_real AS entity_is_real
                           FROM account_transactions at
                                    JOIN financial_entities e ON at.entity_id = e.id
                           WHERE at.entity_id = ?
                           """, (str(entity_id),))
            return [_map_account_row(row) for row in cursor.fetchall()]

    def get_refs_by_entity(self, entity_id: UUID) -> Set[str]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT ref
                           FROM investment_transactions
                           WHERE entity_id = ?
                           UNION
                           SELECT ref
                           FROM account_transactions
                           WHERE entity_id = ?
                           """, (str(entity_id), str(entity_id)))
            return {row[0] for row in cursor.fetchall()}

    def get_by_entity(self, entity_id: UUID) -> Transactions:
        return Transactions(
            investment=self._get_investment_txs_by_entity(entity_id),
            account=self._get_account_txs_by_entity(entity_id)
        )

    def get_refs_by_source_type(self, real: bool) -> Set[str]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT ref
                           FROM investment_transactions
                           WHERE is_real = ?
                           UNION
                           SELECT ref
                           FROM account_transactions
                           WHERE is_real = ?
                           """, (real, real))
            return {row[0] for row in cursor.fetchall()}

    def get_last_created_grouped_by_entity(self) -> Dict[FinancialEntity, datetime]:
        with self._db_client.read() as cursor:
            cursor.execute("""
                           SELECT e.*, MAX(created_at) AS last_created
                           FROM (SELECT entity_id, created_at
                                 FROM investment_transactions
                                 UNION ALL
                                 SELECT entity_id, created_at
                                 FROM account_transactions) txs
                                    JOIN financial_entities e ON txs.entity_id = e.id
                           GROUP BY e.name
                           """)

            result = {}
            for row in cursor.fetchall():
                entity = FinancialEntity(
                    id=UUID(row["id"]),
                    name=row["name"],
                    is_real=row["is_real"]
                )
                last_created = datetime.fromisoformat(row["last_created"])
                result[entity] = last_created

            return result
