"""Tra cứu quy chuẩn / phong thủy (RAG).

Mặc định dùng BM25 thuần Python trên các file .md/.txt/.pdf trong data/quy_chuan và
data/phong_thuy, nên không cần mạng hay mô hình embedding. Nếu đặt USE_CHROMA=1 và đã
cài chromadb thì dùng ChromaDB (vector search) thay thế.
"""
from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger(__name__)

SOURCES = [DATA_DIR / "quy_chuan", DATA_DIR / "phong_thuy"]
_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _read(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _chunk(text: str, source: str, size: int = 700) -> list[dict]:
    """Chia văn bản theo đoạn, gộp tới ~size ký tự, giữ tiêu đề mục gần nhất."""
    chunks, buf, heading = [], "", ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if para.startswith("#"):
            heading = para.lstrip("# ").split("\n")[0]
        if len(buf) + len(para) > size and buf:
            chunks.append({"source": source, "heading": heading, "text": buf.strip()})
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        chunks.append({"source": source, "heading": heading, "text": buf.strip()})
    return chunks


def _source_version() -> tuple:
    version = []
    for folder in SOURCES:
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in {".md", ".txt", ".pdf"}:
                try:
                    stat = path.stat()
                    if path.is_file():
                        version.append((path, stat.st_mtime_ns, stat.st_size))
                except OSError:
                    continue
    return tuple(version)


def reference_files() -> list[Path]:
    """Liệt kê tệp tra cứu hiện có mà không nạp hoặc lập chỉ mục."""
    return [path for path, _, _ in _source_version()]


@lru_cache(maxsize=2)
def _load_corpus(version: tuple) -> list[dict]:
    docs = []
    for path, _, _ in version:
        try:
            docs.extend(_chunk(_read(path), path.name))
        except Exception as error:
            log.warning("Không đọc được tài liệu %s (%s)", path.name, type(error).__name__)
    for d in docs:
        d["tokens"] = _tokens(d["heading"] + " " + d["text"])
    return docs


def _corpus() -> list[dict]:
    return _load_corpus(_source_version())


class BM25Retriever:
    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(len(d["tokens"]) for d in docs) / max(len(docs), 1)
        df = Counter()
        for d in docs:
            df.update(set(d["tokens"]))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d["tokens"]) for d in docs]

    def search(self, query: str, k: int = 3) -> list[dict]:
        q = _tokens(query)
        scores = []
        for i, d in enumerate(self.docs):
            dl = len(d["tokens"])
            s = 0.0
            for t in q:
                if t not in self.tf[i]:
                    continue
                f = self.tf[i][t]
                s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        return [{**{k_: v for k_, v in self.docs[i].items() if k_ != "tokens"}, "score": round(s, 3)}
                for s, i in scores[:k] if s > 0]


class ChromaRetriever:  # pragma: no cover - tùy chọn
    def __init__(self, docs: list[dict]):
        import chromadb

        client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
        self.col = client.get_or_create_collection("quy_chuan")
        if self.col.count() != len(docs):
            ids = [f"c{i}" for i in range(len(docs))]
            self.col.upsert(ids=ids, documents=[d["text"] for d in docs],
                            metadatas=[{"source": d["source"], "heading": d["heading"]} for d in docs])

    def search(self, query: str, k: int = 3) -> list[dict]:
        r = self.col.query(query_texts=[query], n_results=k)
        return [{"source": m["source"], "heading": m["heading"], "text": t, "score": 1 - dist}
                for t, m, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]


@lru_cache(maxsize=1)
def get_retriever():
    docs = _corpus()
    if os.getenv("USE_CHROMA") == "1":
        try:
            return ChromaRetriever(docs)
        except Exception:  # noqa: BLE001 - quay về BM25 nếu Chroma lỗi
            pass
    return BM25Retriever(docs)


def search(query: str, k: int = 3) -> list[dict]:
    return get_retriever().search(query, k)


def cite(query: str, source_prefix: str | None = None) -> dict | None:
    """Trả về đoạn trích ngắn gọn nhất liên quan để đính kèm vào lỗi kiểm định."""
    if source_prefix:
        docs = [d for d in _corpus() if d["source"].lower().startswith(source_prefix)]
        hits = BM25Retriever(docs).search(query, 1)
    else:
        hits = search(query, k=1)
    if not hits:
        return None
    h = hits[0]
    q = set(_tokens(query))
    lines = [ln.strip("-• ").strip() for ln in h["text"].split("\n")
             if ln.strip() and not ln.startswith(("#", ">"))]
    best = max(lines, key=lambda ln: len(q & set(_tokens(ln))), default=h["text"][:200])
    return {"nguon": h["source"], "muc": h["heading"], "trich": best[:300]}
