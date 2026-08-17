"""Configuration loading for the local prototype."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from hr_chatbot.domain import ParserLimits, TokenProfile

HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)


def _section(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise TypeError(f"invalid_config:{name}")
    return value


def _integer(section: Mapping[str, object], name: str) -> int:
    value = section.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"invalid_config:{name}")
    return value


@dataclass(frozen=True, slots=True)
class AppConfig:
    token_profile: TokenProfile
    parser_limits: ParserLimits
    top_k: int
    allowed_source_hosts: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("invalid_config:top_k")
        if any(HOSTNAME.fullmatch(host) is None for host in self.allowed_source_hosts):
            raise ValueError("invalid_config:allowed_hosts")

    @classmethod
    def load(cls, path: Path) -> AppConfig:
        with path.open("rb") as handle:
            data: dict[str, object] = tomllib.load(handle)

        token = _section(data, "token_profile")
        parser = _section(data, "parser_limits")
        retrieval = _section(data, "retrieval")
        sources = _section(data, "sources")
        hosts = sources.get("allowed_hosts")
        if not isinstance(hosts, list) or not all(isinstance(host, str) for host in hosts):
            raise ValueError("invalid_config:allowed_hosts")

        return cls(
            token_profile=TokenProfile(
                model_n_ctx=_integer(token, "model_n_ctx"),
                max_input_tokens=_integer(token, "max_input_tokens"),
                max_history_tokens=_integer(token, "max_history_tokens"),
                max_evidence_tokens=_integer(token, "max_evidence_tokens"),
                max_output_tokens=_integer(token, "max_output_tokens"),
            ),
            parser_limits=ParserLimits(
                max_file_mib=_integer(parser, "max_file_mib"),
                max_pdf_pages=_integer(parser, "max_pdf_pages"),
                max_archive_mib=_integer(parser, "max_archive_mib"),
                max_archive_entries=_integer(parser, "max_archive_entries"),
                max_compression_ratio=_integer(parser, "max_compression_ratio"),
                timeout_seconds=_integer(parser, "timeout_seconds"),
                max_rss_mib=_integer(parser, "max_rss_mib"),
            ),
            top_k=_integer(retrieval, "top_k"),
            allowed_source_hosts=tuple(hosts),
        )
