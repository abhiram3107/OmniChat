"""
Chroma collections for pages, orders, and conversations. + lightweight session memory (SQLite)
"""
from typing import Dict, Any, List
import os, sqlite3, json, time

# Silence OpenTelemetry from Chroma to avoid noisy warnings
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
import chromadb
from chromadb.config import Settings
from embedder import embed_texts

PERSIST_DIR = os.getenv("PERSIST_DIR", "./chroma_store")
TENANT_ID = os.getenv("TENANT_ID", "default")

client = chromadb.PersistentClient(path=PERSIST_DIR, settings=Settings(anonymized_telemetry=False))

COLL_PAGES = f"pages_{TENANT_ID}"
COLL_ORDERS = f"orders_{TENANT_ID}"
COLL_CHATS = f"chats_{TENANT_ID}"

pages = client.get_or_create_collection(COLL_PAGES, metadata={"hnsw:space": "cosine"})
orders = client.get_or_create_collection(COLL_ORDERS, metadata={"hnsw:space": "cosine"})
chats = client.get_or_create_collection(COLL_CHATS, metadata={"hnsw:space": "cosine"})

# Minimal session memory for per-user history (for dialogue continuity)
DB_PATH = os.path.join(PERSIST_DIR, f"sessions_{TENANT_ID}.db")
os.makedirs(PERSIST_DIR, exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("CREATE TABLE IF NOT EXISTS sessions (session_id TEXT, role TEXT, content TEXT, ts REAL)")
conn.commit()

def add_session_turn(session_id: str, role: str, content: str):
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?)", (session_id, role, content, time.time()))
    conn.commit()

def get_recent_session(session_id: str, k: int = 10) -> List[Dict[str, Any]]:
    cur = conn.execute("SELECT role, content FROM sessions WHERE session_id=? ORDER BY ts DESC LIMIT ?", (session_id, k))
    rows = cur.fetchall()[::-1]
    return [{"role": r, "content": c} for (r, c) in rows]

def _upsert(collection, docs: List[Dict[str, Any]]):
    if not docs:
        return
    ids = [d["id"] for d in docs]
    texts = [d["text"] for d in docs]
    metas = [d.get("metadata", {}) for d in docs]
    embs = embed_texts([f"passage: {t}" for t in texts])
    collection.upsert(ids=ids, documents=texts, metadatas=metas, embeddings=embs)

def query(collection, query_text: str, k: int = 5, where: Dict[str, Any] | None = None):
    where = where or {}
    q_emb = embed_texts([f"query: {query_text}"])
    # Request distances to enable score filtering downstream
    res = collection.query(
        query_embeddings=q_emb,
        n_results=k,
        where=where,
        include=["distances", "metadatas", "documents", "embeddings"],
    )
    out = []
    n = len(res["ids"][0]) if res.get("ids") else 0
    for i in range(n):
        item: Dict[str, Any] = {
            "id": res["ids"][0][i],
            "text": res["documents"][0][i],
            "metadata": res["metadatas"][0][i],
        }
        # Attach distance if provided by Chroma
        try:
            dists = res.get("distances") or [[]]
            if dists and len(dists[0]) > i:
                item["distance"] = dists[0][i]
        except Exception:
            pass
        out.append(item)
    return out
