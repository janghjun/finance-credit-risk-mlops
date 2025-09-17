# rag_agent/ingest/chunk_and_index.py
import json, re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib

ROOT = Path(__file__).resolve().parents[2]
BRONZE_DIR = ROOT / "data" / "bronze"
RAW_DIR = ROOT / "data" / "raw"
INDEX_DIR = ROOT / "data" / "index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

MIN_CHARS_PER_DOC = 120
MAX_CHARS = 700
OVERLAP = 80

def split_into_chunks(text: str, max_chars=MAX_CHARS, overlap=OVERLAP):
    if not text:
        return []
    sents = re.split(r'(?<=[\.!\?])\s+', text)
    chunks, buf = [], ""
    for s in sents:
        if not s:
            continue
        if len(buf) + len(s) + 1 > max_chars:
            if buf.strip():
                chunks.append(buf.strip())
                buf = buf[-overlap:] if overlap and len(buf) > overlap else ""
        buf = (buf + " " + s).strip()
    if buf.strip():
        chunks.append(buf.strip())
    # 만약 여전히 비어있다면 fallback으로 통문을 chunk화
    if not chunks and len(text) > 0:
        chunks = [text[:max_chars]]
    return chunks

def load_url_safe(doc_id: str, bronze_obj: dict) -> str:
    u = (bronze_obj.get("url") or "").strip()
    if u:
        return u
    raw_path = RAW_DIR / f"{doc_id}.json"
    if raw_path.exists():
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            u = (raw.get("url") or "").strip()
            if u:
                return u
        except Exception:
            pass
    return ""

def main():
    texts, metas = [], []
    doc_count = 0
    for f in BRONZE_DIR.glob("*.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc_id = doc["doc_id"]
        text = doc.get("text_norm") or ""
        if len(text) < MIN_CHARS_PER_DOC:
            continue
        doc_count += 1
        chunks = split_into_chunks(text)
        if not chunks:
            continue
        source_url = load_url_safe(doc_id, doc)
        for i, ch in enumerate(chunks):
            texts.append(ch)
            metas.append({"doc_id": doc_id, "chunk_id": i, "url": source_url})

    if not texts:
        print("⚠️ No eligible chunks to index after parsing. Consider lowering MIN_CHARS_PER_DOC or improving parsing.")
        return

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    X = vec.fit_transform(texts)
    joblib.dump({"vectorizer": vec, "matrix": X, "metas": metas}, INDEX_DIR / "tfidf.joblib")
    print(f"✅ Indexed {len(texts)} chunks from {len(set(m['doc_id'] for m in metas))} documents (processed_docs={doc_count})")

if __name__ == "__main__":
    main()
