"""Create embeddings via the existing OllamaGateway (nomic-embed-text)."""

from __future__ import annotations

from app.gateways.ollama_gateway import OllamaError, OllamaGateway


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the embedding model is missing or misconfigured."""


class EmbeddingService:
    """Thin wrapper so RAG code does not call Ollama HTTP details directly."""

    def __init__(self, gateway: OllamaGateway | None = None) -> None:
        self._gateway = gateway or OllamaGateway()

    @property
    def model_name(self) -> str:
        return self._gateway.embed_model

    def ensure_ready(self) -> None:
        try:
            self._gateway.ensure_embed_model_ready()
        except OllamaError as exc:
            raise EmbeddingConfigurationError(str(exc)) from exc

    def embed(self, text: str) -> list[float]:
        """Embed a single string. Fails clearly if the model is unavailable."""
        try:
            return self._gateway.embed(text)
        except OllamaError as exc:
            if exc.reason in {"model_missing", "model_not_configured", "connection_failure"}:
                raise EmbeddingConfigurationError(str(exc)) from exc
            raise

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
