"""Configuration for Memory Guardian."""

from pathlib import Path
from typing import Optional


class Config:
    """Memory Guardian configuration."""

    def __init__(
        self,
        data_dir: Optional[str] = None,
        max_context_tokens: int = 4000,
        enable_embeddings: bool = False,
        consolidation_interval_hours: int = 24,
    ):
        """Initialize configuration."""
        if data_dir is None:
            # Default to package data directory
            data_dir = Path(__file__).parent.parent / "data"
        
        self.data_dir = Path(data_dir)
        self.max_context_tokens = max_context_tokens
        self.enable_embeddings = enable_embeddings
        self.consolidation_interval_hours = consolidation_interval_hours
        
        # Ensure directories exist
        (self.data_dir / "memory").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "daily").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "indexes").mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables."""
        import os
        
        return cls(
            data_dir=os.environ.get("MEMORY_GUARDIAN_DATA_DIR"),
            max_context_tokens=int(os.environ.get("MEMORY_GUARDIAN_MAX_TOKENS", "4000")),
            enable_embeddings=os.environ.get("MEMORY_GUARDIAN_EMBEDDINGS", "").lower() == "true",
        )

    def __repr__(self) -> str:
        return f"Config(data_dir={self.data_dir}, max_tokens={self.max_context_tokens})"
