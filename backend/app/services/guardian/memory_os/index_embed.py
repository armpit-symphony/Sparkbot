"""Embedding-based semantic search index (optional v1+ feature)."""

from pathlib import Path
from typing import Iterator

from .schemas import Event


class EmbedIndex:
    """Semantic search index using embeddings (optional)."""

    def __init__(self, data_dir: str | Path | None = None):
        """Initialize embedding index."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "indexes"
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "embed.sqlite"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._model = None  # Lazy load

    def _ensure_model(self) -> None:
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install memory-guardian[embeddings]"
                )

    def index_event(self, event: Event) -> None:
        """Index a single event with its embedding."""
        self._ensure_model()
        # Placeholder - full implementation would store embeddings in vector DB
        pass

    def index_events(self, events: Iterator[Event]) -> None:
        """Bulk index events with embeddings."""
        # Placeholder for v1+
        pass

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search using embeddings."""
        # Placeholder for v1+
        self._ensure_model()
        return []

    def is_available(self) -> bool:
        """Check if embeddings are available."""
        try:
            self._ensure_model()
            return True
        except ImportError:
            return False
