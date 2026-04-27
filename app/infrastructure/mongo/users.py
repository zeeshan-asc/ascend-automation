from __future__ import annotations

from datetime import datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.domain.errors import DuplicateResourceError
from app.domain.models import User
from app.infrastructure.mongo.base import MongoRepository


class UserRepository(MongoRepository[User]):
    collection_name = "users"
    model = User

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("user_id", unique=True)
        await self.collection.create_index("email", unique=True)

    async def create(self, user: User) -> User:
        try:
            await self.collection.insert_one(self.to_document(user))
        except DuplicateKeyError as exc:
            raise DuplicateResourceError("An account with that email already exists.") from exc
        return user

    async def get_by_email(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        return self.from_document(await self.collection.find_one({"email": normalized_email}))

    async def get_by_user_id(self, user_id: str) -> User | None:
        return self.from_document(await self.collection.find_one({"user_id": user_id}))

    async def bump_token_version(self, *, user_id: str, now: datetime) -> User | None:
        document = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {"token_version": 1},
                "$set": {"updated_at": now},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.from_document(document)
