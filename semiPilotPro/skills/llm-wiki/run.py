#!/usr/bin/env python3
"""LLM wiki concatenator and optional FAISS index.

Default mode (concat) uses only the standard library.
ingest/query modes require sentence-transformers and faiss-cpu.
"""
import argparse
import fnmatch
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDES = [
    "node_modules", ".git", "dist", "build", ".venv", "venv",
    ".next", ".turbo", ".nx", "__pycache__", "*.lock", "*.min.js",
    "*.d.ts", "*.map",
]

TEXT_EXTS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".go", ".rs",
    ".java", ".cs", ".rb", ".php", ".sql", ".sh",
}


def is_excluded(path: Path, excludes: list) -> bool:
    parts = path.parts
    for pattern in excludes:
        if "*" in pattern:
            if any(fnmatch.fnmatch(p, pattern) for p in parts):
                return True
        elif pattern in parts:
            return True
    return False


def iter_files(source: Path, excludes: list):
    for root, dirs, files in os.walk(source):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not is_excluded(root_path / d, excludes)]
        for f in files:
            p = root_path / f
            if is_excluded(p, excludes):
                continue
            if p.suffix.lower() not in TEXT_EXTS:
                continue
            yield p


def cmd_concat(args) -> int:
    source = Path(args.source).resolve()
    wiki_dir = source / ".wiki"
    excludes = DEFAULT_EXCLUDES + (args.exclude or [])

    if not wiki_dir.exists():
        print(f"error: {wiki_dir} does not exist. Run #wiki-init first.", file=sys.stderr)
        return 1

    chunks = []
    word_budget = args.max_words
    word_count = 0

    chunks.append(f"# LLM Wiki Context — generated for {source}\n")
    chunks.append("## Wiki\n")
    for wf in sorted(wiki_dir.glob("*.md")):
        content = wf.read_text(errors="replace")
        words = len(content.split())
        if word_count + words > word_budget:
            chunks.append(f"\n### [truncated: {wf.name} omitted, budget exhausted]\n")
            break
        chunks.append(f"\n### {wf.relative_to(source)}\n")
        chunks.append(content)
        word_count += words

    if args.include_source and word_count < word_budget:
        chunks.append("\n\n## Source files\n")
        for sf in iter_files(source, excludes):
            if wiki_dir in sf.parents:
                continue
            try:
                content = sf.read_text(errors="replace")
            except OSError:
                continue
            words = len(content.split())
            if word_count + words > word_budget:
                chunks.append(f"\n### [truncated at {sf.relative_to(source)}]\n")
                break
            chunks.append(f"\n### {sf.relative_to(source)}\n```\n{content}\n```\n")
            word_count += words

    output = "".join(chunks)
    out_path = Path(args.out) if args.out else source / ".wiki" / "wiki-context.md"

    if args.dry_run:
        print(f"[dry-run] Would write {out_path} ({word_count} words, {len(chunks)} sections)")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output)
    print(f"Wrote {out_path} ({word_count} words)")
    return 0


def cmd_ingest(args) -> int:
    try:
        from sentence_transformers import SentenceTransformer
        import faiss
        import numpy as np
        import sqlite3
    except ImportError as e:
        print(f"error: ingest requires sentence-transformers and faiss-cpu. Missing: {e}", file=sys.stderr)
        return 2

    source = Path(args.source).resolve()
    index_dir = Path(args.index_dir).resolve()
    excludes = DEFAULT_EXCLUDES + (args.exclude or [])

    if args.dry_run:
        files = list(iter_files(source, excludes))
        print(f"[dry-run] Would ingest {len(files)} files from {source} into {index_dir}")
        return 0

    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "chunks.sqlite"
    idx_path = index_dir / "faiss.index"

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    dim = model.get_sentence_embedding_dimension()
    index = faiss.IndexFlatIP(dim)

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, path TEXT, text TEXT)")

    chunks_text = []
    for path in iter_files(source, excludes):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        words = text.split()
        for i in range(0, len(words), args.chunk_size - args.overlap):
            chunk = " ".join(words[i:i + args.chunk_size])
            if not chunk.strip():
                continue
            conn.execute("INSERT INTO chunks (path, text) VALUES (?, ?)", (str(path.relative_to(source)), chunk))
            chunks_text.append(chunk)

    conn.commit()

    if chunks_text:
        embeddings = model.encode(chunks_text, convert_to_numpy=True, normalize_embeddings=True)
        index.add(np.asarray(embeddings, dtype=np.float32))
        faiss.write_index(index, str(idx_path))

    conn.close()
    print(f"Ingested {len(chunks_text)} chunks from {source} into {index_dir}")
    return 0


def cmd_query(args) -> int:
    try:
        from sentence_transformers import SentenceTransformer
        import faiss
        import numpy as np
        import sqlite3
    except ImportError as e:
        print(f"error: query requires sentence-transformers and faiss-cpu. Missing: {e}", file=sys.stderr)
        return 2

    index_dir = Path(args.index_dir).resolve()
    db_path = index_dir / "chunks.sqlite"
    idx_path = index_dir / "faiss.index"

    if not idx_path.exists() or not db_path.exists():
        print(f"error: no index found in {index_dir}. Run `ingest` first.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] Would query {idx_path} with: {args.q}")
        return 0

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    index = faiss.read_index(str(idx_path))
    q_emb = model.encode([args.q], convert_to_numpy=True, normalize_embeddings=True)
    scores, ids = index.search(np.asarray(q_emb, dtype=np.float32), args.k)

    conn = sqlite3.connect(db_path)
    for score, idx in zip(scores[0], ids[0]):
        row = conn.execute("SELECT path, text FROM chunks WHERE id = ?", (int(idx) + 1,)).fetchone()
        if row:
            path, text = row
            print(f"\n--- {path} (score {score:.3f}) ---")
            print(text[:500])
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM wiki concatenator and optional FAISS index.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    concat_p = sub.add_parser("concat", help="Concatenate wiki (default) into a single context file.")
    concat_p.add_argument("--source", default=".")
    concat_p.add_argument("--out")
    concat_p.add_argument("--max-words", type=int, default=40000)
    concat_p.add_argument("--include-source", action="store_true", help="Also include source files after wiki content.")
    concat_p.add_argument("--exclude", action="append")
    concat_p.add_argument("--dry-run", action="store_true")

    ingest_p = sub.add_parser("ingest", help="Build a FAISS index. Requires sentence-transformers and faiss-cpu.")
    ingest_p.add_argument("--source", required=True)
    ingest_p.add_argument("--index-dir", required=True)
    ingest_p.add_argument("--chunk-size", type=int, default=200)
    ingest_p.add_argument("--overlap", type=int, default=50)
    ingest_p.add_argument("--exclude", action="append")
    ingest_p.add_argument("--dry-run", action="store_true")

    query_p = sub.add_parser("query", help="Semantic search against an ingested index.")
    query_p.add_argument("--index-dir", required=True)
    query_p.add_argument("--q", required=True)
    query_p.add_argument("--k", type=int, default=5)
    query_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "concat":
        return cmd_concat(args)
    if args.cmd == "ingest":
        return cmd_ingest(args)
    if args.cmd == "query":
        return cmd_query(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
