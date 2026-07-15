from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

from vocr.memory.learning import LearningStore
from vocr.models import GraphEdge, GraphNode, RepoGraph, SymbolSpan


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    ".vocr",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".json", ".yaml", ".yml", ".env.example"}
DEFAULT_MAX_FILE_BYTES = 200_000


class GraphStore:
    def __init__(self, vocr_home: Path | str = ".vocr") -> None:
        self.vocr_home = Path(vocr_home)
        self.path = self.vocr_home / "graph.json"

    def save(self, graph: RepoGraph) -> None:
        self.vocr_home.mkdir(parents=True, exist_ok=True)
        self.path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    def refresh(self, root: Path | str = ".") -> RepoGraph:
        previous = self.load() if self.exists() else None
        graph = RepoGraphBuilder(root, previous=previous).build()
        self.save(graph)
        return graph

    def load(self) -> RepoGraph:
        return RepoGraph.model_validate_json(self.path.read_text(encoding="utf-8"))

    def exists(self) -> bool:
        return self.path.exists()

    def context_pack(self, query: str | None = None, limit: int = 20) -> str:
        boosts: dict[str, float] | None = None
        learning = LearningStore(self.vocr_home)
        if learning.exists():
            boosts = learning.file_boosts(query=query)
        return self.load().context_brief(limit=limit, query=query, learning_boosts=boosts)


class RepoGraphBuilder:
    def __init__(self, root: Path | str = ".", previous: RepoGraph | None = None) -> None:
        self.root = Path(root).resolve()
        self.previous = previous
        self.previous_nodes = {node.path: node for node in previous.nodes} if previous else {}

    def build(self) -> RepoGraph:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        module_to_path: dict[str, str] = {}

        for path in self._iter_files():
            rel = path.relative_to(self.root).as_posix()
            node = self._build_node_incremental(path, rel)
            nodes.append(node)
            if path.suffix == ".py":
                module_to_path[self._module_name(path)] = rel

        for node in nodes:
            for imported in node.imports:
                target = self._resolve_import(imported, module_to_path)
                if target:
                    edges.append(GraphEdge(source=node.path, target=target, relation="imports"))

        return RepoGraph(root=str(self.root), nodes=sorted(nodes, key=lambda item: item.path), edges=edges)

    def _build_node_incremental(self, path: Path, rel: str) -> GraphNode:
        if self.previous_nodes:
            previous = self.previous_nodes.get(rel)
            stat = path.stat()
            if previous and previous.size_bytes == stat.st_size:
                text = path.read_text(encoding="utf-8", errors="ignore")
                content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
                if previous.content_hash == content_hash:
                    if path.suffix == ".py" and previous.symbols and not previous.symbol_spans:
                        return self._build_node_from_text(path, rel, text, stat.st_size)
                    return previous
                return self._build_node_from_text(path, rel, text, stat.st_size)
        return self._build_node(path, rel)

    def _iter_files(self) -> list[Path]:
        files: list[Path] = []
        max_bytes = int(os.getenv("VOCR_GRAPH_MAX_FILE_BYTES", str(DEFAULT_MAX_FILE_BYTES)))
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in DEFAULT_EXCLUDES for part in path.relative_to(self.root).parts):
                continue
            if path.stat().st_size > max_bytes:
                continue
            if path.suffix in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES:
                files.append(path)
        return files

    def _build_node(self, path: Path, rel: str) -> GraphNode:
        stat = path.stat()
        text = path.read_text(encoding="utf-8", errors="ignore")
        return self._build_node_from_text(path, rel, text, stat.st_size)

    def _build_node_from_text(self, path: Path, rel: str, text: str, size_bytes: int) -> GraphNode:
        lines = text.splitlines()
        imports: list[str] = []
        symbols: list[str] = []
        symbol_spans: list[SymbolSpan] = []

        if path.suffix == ".py":
            imports, symbols, symbol_spans = self._parse_python(text)

        return GraphNode(
            path=rel,
            kind=path.suffix.lstrip(".") or path.name,
            size_bytes=size_bytes,
            line_count=len(lines),
            content_hash=hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
            summary=self._summarize(path, lines, symbols),
            imports=imports,
            symbols=symbols,
            symbol_spans=symbol_spans,
        )

    def _parse_python(self, text: str) -> tuple[list[str], list[str], list[SymbolSpan]]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [], [], []

        imports: list[str] = []
        symbols: list[str] = []
        symbol_spans: list[SymbolSpan] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                name = f"class {node.name}"
                symbols.append(name)
                symbol_spans.append(SymbolSpan(name=name, start=node.lineno, end=node.end_lineno or node.lineno))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"def {node.name}"
                symbols.append(name)
                symbol_spans.append(SymbolSpan(name=name, start=node.lineno, end=node.end_lineno or node.lineno))
        return sorted(set(imports)), symbols, symbol_spans

    def _summarize(self, path: Path, lines: list[str], symbols: list[str]) -> str:
        if path.suffix == ".py":
            doc_summary = self._python_doc_summary(path)
            if doc_summary:
                return doc_summary
        if path.suffix == ".py" and symbols:
            return f"Python module: {', '.join(symbols[:8])}"
        if path.suffix == ".md":
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.strip("# ").strip()[:160]
        for line in lines:
            stripped = line.strip("# ").strip()
            if stripped:
                return stripped[:160]
        return "Empty file"

    def _python_doc_summary(self, path: Path) -> str | None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            return None
        doc = ast.get_docstring(tree)
        if doc:
            return doc.splitlines()[0][:160]
        return None

    def _module_name(self, path: Path) -> str:
        rel = path.relative_to(self.root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _resolve_import(self, imported: str, module_to_path: dict[str, str]) -> str | None:
        candidates = [imported]
        parts = imported.split(".")
        while len(parts) > 1:
            parts.pop()
            candidates.append(".".join(parts))
        for candidate in candidates:
            if candidate in module_to_path:
                return module_to_path[candidate]
        return None


def graph_to_json(graph: RepoGraph) -> str:
    return json.dumps(graph.model_dump(mode="json"), indent=2)
