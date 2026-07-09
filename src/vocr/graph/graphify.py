from __future__ import annotations

import ast
import json
from pathlib import Path

from vocr.models import GraphEdge, GraphNode, RepoGraph


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


class GraphStore:
    def __init__(self, vocr_home: Path | str = ".vocr") -> None:
        self.vocr_home = Path(vocr_home)
        self.path = self.vocr_home / "graph.json"

    def save(self, graph: RepoGraph) -> None:
        self.vocr_home.mkdir(parents=True, exist_ok=True)
        self.path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    def load(self) -> RepoGraph:
        return RepoGraph.model_validate_json(self.path.read_text(encoding="utf-8"))

    def exists(self) -> bool:
        return self.path.exists()

    def context_pack(self, query: str | None = None, limit: int = 20) -> str:
        return self.load().context_brief(limit=limit, query=query)


class RepoGraphBuilder:
    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root).resolve()

    def build(self) -> RepoGraph:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        module_to_path: dict[str, str] = {}

        for path in self._iter_files():
            rel = path.relative_to(self.root).as_posix()
            node = self._build_node(path, rel)
            nodes.append(node)
            if path.suffix == ".py":
                module_to_path[self._module_name(path)] = rel

        for node in nodes:
            for imported in node.imports:
                target = self._resolve_import(imported, module_to_path)
                if target:
                    edges.append(GraphEdge(source=node.path, target=target, relation="imports"))

        return RepoGraph(root=str(self.root), nodes=sorted(nodes, key=lambda item: item.path), edges=edges)

    def _iter_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in DEFAULT_EXCLUDES for part in path.relative_to(self.root).parts):
                continue
            if path.suffix in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES:
                files.append(path)
        return files

    def _build_node(self, path: Path, rel: str) -> GraphNode:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        imports: list[str] = []
        symbols: list[str] = []

        if path.suffix == ".py":
            imports, symbols = self._parse_python(text)

        return GraphNode(
            path=rel,
            kind=path.suffix.lstrip(".") or path.name,
            size_bytes=path.stat().st_size,
            line_count=len(lines),
            summary=self._summarize(path, lines, symbols),
            imports=imports,
            symbols=symbols,
        )

    def _parse_python(self, text: str) -> tuple[list[str], list[str]]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [], []

        imports: list[str] = []
        symbols: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.ClassDef):
                symbols.append(f"class {node.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(f"def {node.name}")
        return sorted(set(imports)), symbols

    def _summarize(self, path: Path, lines: list[str], symbols: list[str]) -> str:
        if path.suffix == ".py" and symbols:
            return f"Python module with {len(symbols)} top-level or nested symbols"
        for line in lines:
            stripped = line.strip("# ").strip()
            if stripped:
                return stripped[:160]
        return "Empty file"

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
