"""Configuração lida do .env. A chave da API nunca é exibida nem gravada em log."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def raiz_projeto() -> Path:
    """Raiz do repositório (onde ficam prompts/, sql/ e dados/)."""
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    deepseek_api_key: str = field(repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    forum_database_url: str = field(default="", repr=False)
    controllers: tuple[str, ...] = ()
    teto_chamadas: int = 100
    teto_usd: float = 0.50
    dados_dir: Path = field(default_factory=lambda: raiz_projeto() / "dados")

    def descrever(self) -> str:
        """Resumo seguro para log: mostra só o tamanho da chave e esconde a senha do banco."""
        banco = "definido" if self.forum_database_url else "ausente"
        return (
            f"modelo={self.deepseek_model} base_url={self.deepseek_base_url} "
            f"chave=len:{len(self.deepseek_api_key)} banco={banco} "
            f"controllers={len(self.controllers)} teto={self.teto_chamadas} chamadas/US${self.teto_usd:.2f}"
        )

    def exigir_api(self) -> None:
        if not self.deepseek_api_key or not self.deepseek_base_url or not self.deepseek_model:
            raise SystemExit("ERRO: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL e DEEPSEEK_MODEL precisam estar no .env.")

    def exigir_banco(self) -> None:
        if not self.forum_database_url:
            raise SystemExit("ERRO: FORUM_DATABASE_URL precisa estar no .env.")
        if not self.controllers:
            raise SystemExit("ERRO: TRATAMENTO_CONTROLLERS precisa listar os nomes separados por ';'.")


def _controllers(valor: str | None) -> tuple[str, ...]:
    if not valor:
        return ()
    return tuple(nome.strip() for nome in valor.split(";") if nome.strip())


def carregar(env_path: Path | None = None) -> Config:
    """Lê o .env da raiz do projeto (ou o caminho dado) e devolve a configuração."""
    load_dotenv(env_path or raiz_projeto() / ".env")
    return Config(
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        forum_database_url=os.environ.get("FORUM_DATABASE_URL", ""),
        controllers=_controllers(os.environ.get("TRATAMENTO_CONTROLLERS")),
        teto_chamadas=int(os.environ.get("TETO_CHAMADAS", "100")),
        teto_usd=float(os.environ.get("TETO_USD", "0.50")),
    )
