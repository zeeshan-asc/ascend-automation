from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def strip_mongo_id(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    document = dict(document)
    document.pop("_id", None)
    return document


class MongoRepository[ModelT: BaseModel]:
    collection_name: str
    model: type[ModelT]

    def __init__(self, database: Any) -> None:
        self._database = database

    @property
    def collection(self) -> Any:
        return self._database[self.collection_name]

    def to_document(self, model: ModelT) -> dict[str, Any]:
        return model.model_dump(mode="python")

    def from_document(self, document: dict[str, Any] | None) -> ModelT | None:
        stripped = strip_mongo_id(document)
        if stripped is None:
            return None
        return self.model.model_validate(stripped)
