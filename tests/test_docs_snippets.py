import re
from pathlib import Path
from urllib.parse import urlparse

import click
import pytest

# API app import (source of truth for routes)
from redis_sre_agent.api.app import app

# CLI entrypoint (source of truth for commands)
from redis_sre_agent.cli.main import main as cli_main


def _iter_markdown_files() -> list[Path]:
    root = Path(".")
    files = [root / "README.md"]
    files += list((root / "docs").rglob("*.md"))
    return files


def _iter_codeblock_lines(md: Path):
    try:
        lines = md.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    in_block = False
    lang = None
    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            if not in_block:
                in_block = True
                lang = line.strip().lstrip("`").strip()
            else:
                in_block = False
                lang = None
            continue
        if in_block:
            yield i, line, (lang or "")


def _iter_curl_examples() -> list[tuple[str, str, Path, int]]:
    """Yield (method, path, file, lineno) for curl examples strictly in code blocks.

    - Detects method via '-X METHOD' or defaults to GET
    - Extracts URL and keeps only the path component
    - Skips websocket (ws://) and non-API host examples
    """
    results: list[tuple[str, str, Path, int]] = []
    curl_re = re.compile(r"^\s*curl\s+(.*)$")
    method_re = re.compile(r"-X\s+([A-Z]+)")

    for md in _iter_markdown_files():
        for i, line, _lang in _iter_codeblock_lines(md):
            m = curl_re.match(line)
            if not m:
                continue
            cmd = m.group(1)
            if "ws://" in cmd or "wss://" in cmd:
                continue
            parts = cmd.split()
            url_token = next(
                (p for p in parts if p.startswith("http://") or p.startswith("https://")), None
            )
            if not url_token:
                continue
            parsed = urlparse(url_token)
            if not parsed.netloc.endswith(":8000"):
                continue
            if not parsed.path:
                continue
            method_match = method_re.search(cmd)
            method = (method_match.group(1) if method_match else "GET").upper()
            results.append((method, parsed.path, md, i))
    return results


def _route_methods_and_paths() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for r in app.routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        if not methods or not path:
            continue
        for m in methods:
            routes.add((m.upper(), path))
    return routes


def _path_matches(route_path: str, doc_path: str) -> bool:
    rp = route_path.rstrip("/") or "/"
    dp = doc_path.rstrip("/") or "/"
    rsegs = [s for s in rp.split("/") if s]
    dsegs = [s for s in dp.split("/") if s]
    if len(rsegs) != len(dsegs):
        return False
    for rs, ds in zip(rsegs, dsegs):
        if rs.startswith("{") and rs.endswith("}"):
            continue
        if ds.startswith("<") and ds.endswith(">"):
            continue
        if rs != ds:
            return False
    return True


@pytest.mark.parametrize("method,path,file,lineno", _iter_curl_examples())
def test_docs_curl_examples_exist(method: str, path: str, file: Path, lineno: int):
    routes = _route_methods_and_paths()
    candidates = [rp for rp in routes if rp[0] in {method, "HEAD"}]
    ok = any(_path_matches(rp[1], path) for rp in candidates)
    assert ok, f"Missing route for {method} {path} (in {file}:{lineno})"


def _iter_cli_examples() -> list[tuple[list[str], Path, int]]:
    results: list[tuple[list[str], Path, int]] = []
    cli_re = re.compile(r"redis-sre-agent\s+(.+)$")
    for md in _iter_markdown_files():
        for i, line, lang in _iter_codeblock_lines(md):
            if "redis-sre-agent" not in line:
                continue
            m = cli_re.search(line)
            if not m:
                continue
            tail = m.group(1).strip()
            if tail.endswith("\\"):
                continue
            raw_tokens = tail.split()
            tokens: list[str] = []
            for t in raw_tokens:
                if t.startswith("-"):
                    break
                t = t.strip("`\"'")
                if not t or t.isnumeric():
                    continue
                tokens.append(t)
                if len(tokens) == 2:
                    break
            if not tokens:
                continue
            # If the top-level command is not a group, only validate the top-level token
            ctx = click.Context(cli_main)
            top = cli_main.get_command(ctx, tokens[0])
            if top is None:
                chain = tokens[:1]
            elif not hasattr(top, "get_command"):
                chain = tokens[:1]
            else:
                chain = tokens
            results.append((chain, md, i))
    return results


def _cli_has_chain(chain: list[str]) -> bool:
    ctx = click.Context(cli_main)
    top = cli_main.get_command(ctx, chain[0])
    if top is None:
        return False
    if len(chain) == 1:
        return True
    sub = top.get_command(ctx, chain[1]) if hasattr(top, "get_command") else None
    return sub is not None


@pytest.mark.parametrize("chain,file,lineno", _iter_cli_examples())
def test_docs_cli_examples_exist(chain: list[str], file: Path, lineno: int):
    assert _cli_has_chain(chain), f"Missing CLI command: {' '.join(chain)} (in {file}:{lineno})"
