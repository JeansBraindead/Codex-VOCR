from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import urllib.error
import urllib.request

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
        self.embeddings_path = self.vocr_home / "graph_embeddings.json"

    def save(self, graph: RepoGraph) -> None:
        self.vocr_home.mkdir(parents=True, exist_ok=True)
        self.path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    def refresh(self, root: Path | str = ".") -> RepoGraph:
        previous = self.load() if self.exists() else None
        graph = RepoGraphBuilder(root, previous=previous).build()
        self.save(graph)
        if _embedding_retrieval_enabled():
            try:
                self.refresh_embeddings(graph)
            except EmbeddingUnavailable:
                pass
        return graph

    def load(self) -> RepoGraph:
        return RepoGraph.model_validate_json(self.path.read_text(encoding="utf-8"))

    def exists(self) -> bool:
        return self.path.exists()

    def context_pack(self, query: str | None = None, limit: int = 20, span_token_budget: int = 900) -> str:
        boosts: dict[str, float] | None = None
        learning = LearningStore(self.vocr_home)
        if learning.exists():
            boosts = learning.file_boosts(query=query)
        graph = self.load()
        if _embedding_retrieval_enabled() and query:
            try:
                ranked_nodes = self._embedding_fused_rank(graph, query, learning_boosts=boosts)
                return graph.context_brief(
                    limit=limit, query=query, ranked_nodes=ranked_nodes, span_token_budget=span_token_budget
                )
            except EmbeddingUnavailable:
                return graph.context_brief(
                    limit=limit,
                    query=query,
                    learning_boosts=boosts,
                    note="embedding retrieval unavailable, lexical only",
                    span_token_budget=span_token_budget,
                )
        return graph.context_brief(limit=limit, query=query, learning_boosts=boosts, span_token_budget=span_token_budget)

    def refresh_embeddings(self, graph: RepoGraph) -> None:
        cache = self._load_embedding_cache()
        changed = False
        for node in graph.nodes:
            if node.content_hash in cache:
                continue
            cache[node.content_hash] = _embed_text(_node_embedding_text(node))
            changed = True
        if changed:
            self._save_embedding_cache(cache)

    def _embedding_fused_rank(
        self,
        graph: RepoGraph,
        query: str,
        learning_boosts: dict[str, float] | None = None,
    ) -> list[GraphNode]:
        cache = self._load_embedding_cache()
        query_embedding = _embed_text(query)
        lexical_rank = graph._rank_nodes_bm25(query, learning_boosts=learning_boosts)
        semantic_scored: list[tuple[float, GraphNode]] = []
        for node in graph.nodes:
            embedding = cache.get(node.content_hash)
            if embedding is None:
                continue
            semantic_scored.append((_cosine_similarity(query_embedding, embedding), node))
        semantic_rank = [
            node for score, node in sorted(semantic_scored, key=lambda item: (-item[0], item[1].path)) if score > 0
        ]
        return _reciprocal_rank_fusion([lexical_rank, semantic_rank])

    def _load_embedding_cache(self) -> dict[str, list[float]]:
        if not self.embeddings_path.exists():
            return {}
        data = json.loads(self.embeddings_path.read_text(encoding="utf-8"))
        return {str(key): [float(item) for item in value] for key, value in data.items()}

    def _save_embedding_cache(self, cache: dict[str, list[float]]) -> None:
        self.vocr_home.mkdir(parents=True, exist_ok=True)
        self.embeddings_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


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


class EmbeddingUnavailable(RuntimeError):
    pass


def _embedding_retrieval_enabled() -> bool:
    return os.getenv("VOCR_EMBED_RETRIEVAL", "").strip().lower() in {"1", "true", "yes", "on"}


def _embed_text(text: str) -> list[float]:
    base_url = os.getenv("VOCR_EMBED_BASE_URL", "").rstrip("/")
    model = os.getenv("VOCR_EMBED_MODEL", "")
    if not base_url or not model:
        raise EmbeddingUnavailable("Embedding endpoint or model is not configured.")
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    endpoint = base_url if base_url.endswith("/embeddings") else f"{base_url}/embeddings"
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise EmbeddingUnavailable(str(exc)) from exc
    try:
        embedding = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise EmbeddingUnavailable("Embedding response did not contain data[0].embedding.") from exc
    return [float(item) for item in embedding]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _reciprocal_rank_fusion(rankings: list[list[GraphNode]], *, k: int = 60) -> list[GraphNode]:
    by_path: dict[str, GraphNode] = {}
    scores: dict[str, float] = {}
    for ranking in rankings:
        for index, node in enumerate(ranking, start=1):
            by_path[node.path] = node
            scores[node.path] = scores.get(node.path, 0.0) + 1.0 / (k + index)
    return [by_path[path] for path, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


def _node_embedding_text(node: GraphNode) -> str:
    return " ".join([node.path, node.summary, " ".join(node.imports), " ".join(node.symbols)])
