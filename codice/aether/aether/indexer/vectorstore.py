from __future__ import annotations

from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.table import Table
from rich.console import Console

from aether.config import VectorStoreConfig

console = Console()


class VectorStore:
    """Local vector store powered by LanceDB."""

    def __init__(self, config: VectorStoreConfig, dimension: int = 768):
        self.config = config
        self.dimension = dimension
        self.db_path = Path(config.path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self._table: Table | None = None

    @property
    def table(self) -> Table:
        if self._table is None:
            self._table = self._get_or_create_table()
        return self._table

    def _get_or_create_table(self) -> Table:
        table_names = self.db.table_names()
        if self.config.table_name in table_names:
            return self.db.open_table(self.config.table_name)

        # Schema explícito
        return self.db.create_table(self.config.table_name, schema=self._schema())

    def _schema(self) -> Any:
        return pa.schema([
            pa.field("id", pa.string()), pa.field("path", pa.string()),
            pa.field("chunk_index", pa.int32()), pa.field("content", pa.string()),
            pa.field("start_line", pa.int32()), pa.field("end_line", pa.int32()),
            pa.field("language", pa.string()), pa.field("hash", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dimension)),
        ])

    def get_records(self) -> list[dict[str, Any]]:
        return self.table.to_arrow().to_pylist()

    def replace(self, records: list[dict[str, Any]]) -> None:
        data = pa.Table.from_pylist(records, schema=self._schema())
        self._table = self.db.create_table(self.config.table_name, data=data,
                                          mode="overwrite")

    def add(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        self.table.add(records)

    def search(
        self,
        query_vector: list[float],
        limit: int = 12,
        path_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        query = self.table.search(query_vector).limit(limit)

        if path_filter:
            query = query.where(f"path LIKE '%{path_filter.replace(chr(39), chr(39) * 2)}%'")

        results = query.to_list()
        return results

    def delete_by_path(self, path: str) -> None:
        self.table.delete(f"path = '{path.replace(chr(39), chr(39) * 2)}'")

    def get_indexed_paths(self) -> set[str]:
        return {record["path"] for record in self.get_records()}

    def count(self) -> int:
        return int(self.table.count_rows())

    def clear(self) -> None:
        if self.config.table_name in self.db.table_names():
            self.db.drop_table(self.config.table_name)
            self._table = None
