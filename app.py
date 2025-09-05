from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import urllib.parse, os, re
from store import pages, orders, chats, query, add_session_turn, get_recent_session, _upsert
from crawler import crawl
from prompts import SYSTEM_PROMPT, REFUSAL
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_ID = os.getenv("MODEL_ID", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
_tok = None
_llm = None

def get_llm():
    global _tok, _llm
    if _tok is None or _llm is None:
        _tok = AutoTokenizer.from_pretrained(MODEL_ID)
        _llm = AutoModelForCausalLM.from_pretrained(MODEL_ID)
    return _tok, _llm

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

@app.options("/{path:path}", include_in_schema=False)
def options_catch_all(path: str):
    return Response(status_code=204)

# ---------------------------- Schemas ----------------------------
class ChatIn(BaseModel):
    session_id: str
    message: str
    k: int = 4
    domain_only: bool = True
    domain: str | None = None
    open_book: bool = True   # <— allow general knowledge if context is empty

class ChatOut(BaseModel):
    reply: str
    sources: List[Dict[str, Any]]

class IngestIn(BaseModel):
    site: str
    max_pages: int = 40

# --------------------- Retrieval helper -------------------------
def _filter_by_score(hits: List[Dict[str, Any]], min_score: float) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for h in hits:
        score = h.get("score")
        if score is None:
            dist = h.get("distance")
            if dist is not None:
                try:
                    score = 1.0 - min(1.0, float(dist))
                except Exception:
                    score = 0.0
            else:
                score = 0.0
        if score >= min_score:
            out.append(h)
    return out

def retrieve_context(
    q: str,
    k: int,
    domain: str | None = None,
    domain_only: bool = True,
    min_score: float = 0.35,
    require_page_hit: bool = True,
) -> List[Dict[str, Any]]:
    where_pages = {"domain": domain} if (domain_only and domain) else ({"domain": domain} if domain else None)
    where_other = {"domain": domain} if (domain_only and domain) else None

    R: List[Dict[str, Any]] = []
    R += query(pages, q, k=k, where=where_pages)
    R += query(orders, q, k=max(1, k // 2), where=where_other)
    R += query(chats, q, k=max(1, k // 2), where=where_other)
    R = _filter_by_score(R, min_score)

    seen, out = set(), []
    for r in R:
        key = r["metadata"].get("url") or r["id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    out = out[:k]

    if require_page_hit and not any(c.get("metadata", {}).get("type") == "page" for c in out):
        return []
    return out

# --------------------- Prompting / Generation --------------------
def is_site_specific(msg: str, domain: str | None) -> bool:
    msg_l = (msg or "").lower()
    if not msg_l:
        return False
    if any(w in msg_l for w in ["this site", "website", "on this site", "on the website", "from this site"]):
        return True
    if domain and (domain.lower() in msg_l):
        return True
    return False

def build_prompt(history: List[Dict[str, str]], ctx: List[Dict[str, Any]], user: str, domain: str | None, open_book: bool) -> str:
    citations = "\n".join([f"[{i+1}] {c['metadata']}\n{(c['text'] or '')[:300]}" for i, c in enumerate(ctx)])
    hist_txt = "\n".join([f"{h['role'].capitalize()}: {h['content']}" for h in history])

    guard = (
        "You are answering questions for a site assistant.\n"
        f"Loaded site domain: {domain or 'unknown'}\n"
        "Use ONLY the facts in [CONTEXT] when the question is about the site.\n"
        "If the site context does not contain the answer and the question is about the site, reply with REFUSAL exactly.\n"
    )
    # If open_book True, allow general answers when the question is *not* about the site.
    if open_book:
        guard += (
            "If the question is general knowledge and not about the site, you may answer briefly using your own knowledge.\n"
            "Prefer concise, factual responses."
        )
    else:
        guard += "Do not use outside knowledge at all."

    prompt = (
        f"<s>[SYSTEM]\n{SYSTEM_PROMPT}\n\n{guard}\n\n"
        f"[CONTEXT]\n{citations}\n\n"
        f"[HISTORY]\n{hist_txt}\n\n"
        f"[USER]\n{user}\n\n[ASSISTANT]"
    )
    return prompt

def generate(prompt: str, max_new_tokens=256) -> str:
    tok, llm = get_llm()
    input_ids = tok.encode(prompt, return_tensors="pt")
    output_ids = llm.generate(
        input_ids,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        temperature=0.0,
        repetition_penalty=1.05,
    )
    text = tok.decode(output_ids[0], skip_special_tokens=True)
    return text.split("[ASSISTANT]")[-1].strip()

# ------------------------------- API --------------------------------
@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    try:
        add_session_turn(body.session_id, "user", body.message)
        history = get_recent_session(body.session_id, k=8)

        ctx = retrieve_context(
            body.message, body.k,
            domain=body.domain, domain_only=body.domain_only,
            min_score=0.35, require_page_hit=True,
        )

        site_q = is_site_specific(body.message, body.domain)
        if not ctx and site_q and not body.open_book:
            reply = REFUSAL
            add_session_turn(body.session_id, "assistant", reply)
            return {"reply": reply, "sources": []}

        # Build prompt; pass ctx (can be empty if open_book & not site-specific)
        prompt = build_prompt(history, ctx, body.message, body.domain, body.open_book)
        reply = generate(prompt)

        if ctx:
            reply = reply + "\n\nSources: " + ", ".join([f"[{i+1}]" for i in range(len(ctx))])

        add_session_turn(body.session_id, "assistant", reply)
        srcs = [{"id": c["id"], "url": c["metadata"].get("url"), "type": c["metadata"].get("type")} for c in ctx]
        return {"reply": reply, "sources": srcs}
    except Exception:
        import traceback
        with open("last_error.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise

@app.post("/ingest")
def ingest_site(body: IngestIn):
    site = body.site.strip()
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    domain = urllib.parse.urlparse(site).netloc or site

    docs = []
    for i, p in enumerate(crawl(site, max_pages=body.max_pages)):
        text = (p.get("text") or "").strip()
        if not text:
            continue
        docs.append({
            "id": f"{domain}-page-{i}",
            "text": text[:5000],
            "metadata": {"url": p.get("url", site), "type": "page", "domain": domain},
        })
    _upsert(pages, docs)
    return {"ok": True, "domain": domain, "pages": len(docs)}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/echo")
def echo(body: ChatIn):
    return body.model_dump()
