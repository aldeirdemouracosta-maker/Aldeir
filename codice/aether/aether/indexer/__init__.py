from typing import Any

__all__ = ["CodebaseIndexer", "Embedder", "VectorStore"]
def __getattr__(name: str) -> Any:
    from importlib import import_module
    modules = {"CodebaseIndexer": "indexer", "Embedder": "embedder", "VectorStore": "vectorstore"}
    if name not in modules:
        raise AttributeError(name)
    return getattr(import_module(f"aether.indexer.{modules[name]}"), name)
