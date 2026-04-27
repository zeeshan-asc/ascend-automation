from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import mongomock


class AsyncCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self._iterator: Iterator[dict[str, Any]] | None = None

    def sort(self, key_or_list: Any, direction: int | None = None) -> AsyncCursor:
        if direction is None:
            self._cursor = self._cursor.sort(key_or_list)
        else:
            self._cursor = self._cursor.sort(key_or_list, direction)
        return self

    def skip(self, amount: int) -> AsyncCursor:
        self._cursor = self._cursor.skip(amount)
        return self

    def limit(self, amount: int) -> AsyncCursor:
        self._cursor = self._cursor.limit(amount)
        return self

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        self._iterator = iter(self._cursor)
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._iterator is None:
            self._iterator = iter(self._cursor)
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class AsyncCollection:
    def __init__(self, collection: Any) -> None:
        self._collection = collection

    async def create_index(self, *args: Any, **kwargs: Any) -> str:
        return self._collection.create_index(*args, **kwargs)

    async def insert_one(self, *args: Any, **kwargs: Any) -> Any:
        return self._collection.insert_one(*args, **kwargs)

    async def insert_many(self, *args: Any, **kwargs: Any) -> Any:
        return self._collection.insert_many(*args, **kwargs)

    async def find_one(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._collection.find_one(*args, **kwargs)

    async def find_one_and_update(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._collection.find_one_and_update(*args, **kwargs)

    async def update_one(self, *args: Any, **kwargs: Any) -> Any:
        return self._collection.update_one(*args, **kwargs)

    async def count_documents(self, *args: Any, **kwargs: Any) -> int:
        return self._collection.count_documents(*args, **kwargs)

    def find(self, *args: Any, **kwargs: Any) -> AsyncCursor:
        return AsyncCursor(self._collection.find(*args, **kwargs))

    async def aggregate(self, *args: Any, **kwargs: Any) -> AsyncCursor:
        return AsyncCursor(self._collection.aggregate(*args, **kwargs))


class AsyncDatabase:
    def __init__(self, database: Any) -> None:
        self._database = database

    def __getitem__(self, name: str) -> AsyncCollection:
        return AsyncCollection(self._database[name])


class FakeMongoManager:
    def __init__(self, database_name: str = "test-db") -> None:
        self._client = mongomock.MongoClient()
        self.database = AsyncDatabase(self._client[database_name])
        self.closed = False

    async def close(self) -> None:
        self.closed = True
