from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import and_
from typing_extensions import final

from app.commons import tracing
from app.commons.database.infra import DB
from app.payout.models import TransferMethodType
from app.payout.repository.maindb.base import PayoutMainDBRepository
from app.payout.repository.maindb.model import transfers
from app.payout.repository.maindb.model.transfer import (
    Transfer,
    TransferCreate,
    TransferUpdate,
)


class TransferRepositoryInterface(ABC):
    @abstractmethod
    async def create_transfer(self, data: TransferCreate) -> Transfer:
        pass

    @abstractmethod
    async def get_transfer_by_id(self, transfer_id: int) -> Optional[Transfer]:
        pass

    @abstractmethod
    async def update_transfer_by_id(
        self, transfer_id: int, data: TransferUpdate
    ) -> Optional[Transfer]:
        pass

    @abstractmethod
    async def get_transfers_by_ids(self, transfer_ids: List[int]) -> List[Transfer]:
        pass

    @abstractmethod
    async def get_transfers_by_submitted_at_and_method(
        self, start_time: datetime
    ) -> List[int]:
        pass


@final
@tracing.track_breadcrumb(repository_name="transfer")
class TransferRepository(PayoutMainDBRepository, TransferRepositoryInterface):
    def __init__(self, database: DB):
        super().__init__(_database=database)

    async def create_transfer(self, data: TransferCreate) -> Transfer:
        stmt = (
            transfers.table.insert()
            .values(
                data.dict(skip_defaults=True), created_at=datetime.now(timezone.utc)
            )
            .returning(*transfers.table.columns.values())
        )
        row = await self._database.master().fetch_one(stmt)
        assert row is not None
        return Transfer.from_row(row)

    async def get_transfer_by_id(self, transfer_id: int) -> Optional[Transfer]:
        stmt = transfers.table.select().where(transfers.id == transfer_id)
        row = await self._database.replica().fetch_one(stmt)
        return Transfer.from_row(row) if row else None

    async def get_transfers_by_ids(self, transfer_ids: List[int]) -> List[Transfer]:
        stmt = transfers.table.select().where(transfers.id.in_(transfer_ids))
        rows = await self._database.master().fetch_all(stmt)
        results = [Transfer.from_row(row) for row in rows] if rows else []
        return results

    async def get_transfers_by_submitted_at_and_method(
        self, start_time: datetime
    ) -> List[int]:
        query = and_(
            transfers.submitted_at.__ge__(start_time),
            transfers.method == TransferMethodType.STRIPE,
        )
        stmt = transfers.table.select().where(query)
        rows = await self._database.replica().fetch_all(stmt)

        if rows:
            results = [Transfer.from_row(row) for row in rows]
            return [transfer.id for transfer in results]
        else:
            return []

    async def update_transfer_by_id(
        self, transfer_id: int, data: TransferUpdate
    ) -> Optional[Transfer]:
        stmt = (
            transfers.table.update()
            .where(transfers.id == transfer_id)
            .values(data.dict(skip_defaults=True))
            .returning(*transfers.table.columns.values())
        )
        row = await self._database.master().fetch_one(stmt)
        return Transfer.from_row(row) if row else None
