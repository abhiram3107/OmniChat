from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import urllib.parse
import os
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

# Permissive CORS: allow all origins/headers/methods
# Note: if you need credentials (cookies/Authorization), specify explicit origins instead of "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


# Handle bare OPTIONS preflight requests (some clients omit headers)
@app.options("/{path:path}", include_in_schema=False)
def options_catch_all(path: str):
    # CORS middleware will attach the appropriate headers
    return Response(status_code=204)


class ChatIn(BaseModel):
    session_id: str
    message: str
    k: int = 4  # retrieval depth
    domain_only: bool = True
    domain: str | None = None


class ChatOut(BaseModel):
    reply: str
    sources: List[Dict[str, Any]]


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

    if require_page_hit:
        has_page = any(c.get("metadata", {}).get("type") == "page" for c in out)
        if not has_page:
            return []

    return out


def build_prompt(history: List[Dict[str, str]], ctx: List[Dict[str, Any]], user: str) -> str:
    citations = "\n".join(
        [f"[{i+1}] {c['metadata']}\n{c['text'][:300]}" for i, c in enumerate(ctx)]
    )
    hist_txt = "\n".join([f"{h['role'].capitalize()}: {h['content']}" for h in history])
    strict_guard = (
        "You must answer ONLY using the information in [CONTEXT]. "
        "If the answer is not in [CONTEXT], reply with REFUSAL. "
        "Never use outside knowledge."
    )
    prompt = (
        f"<s>[SYSTEM]\n{SYSTEM_PROMPT}\n\n"
        f"{strict_guard}\n\n"
        f"[CONTEXT]\n{citations}\n\n"
        f"[HISTORY]\n{hist_txt}\n\n"
        f"[USER]\n{user}\n\n[ASSISTANT]"
    )
    return prompt


def generate(prompt: str, max_new_tokens=128) -> str:
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


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    try:
        with open("entered.txt", "w", encoding="utf-8") as _f:
            _f.write("entered chat")
        add_session_turn(body.session_id, "user", body.message)
        history = get_recent_session(body.session_id, k=8)
        ctx = retrieve_context(
            body.message,
            body.k,
            domain=body.domain,
            domain_only=body.domain_only,
            min_score=0.35,
            require_page_hit=True,
        )
        if not ctx:
            reply = REFUSAL
            add_session_turn(body.session_id, "assistant", reply)
            return {"reply": reply, "sources": []}
        prompt = build_prompt(history, ctx, body.message)
        reply = generate(prompt)
        if ctx:
            reply = reply + f"\n\nSources: " + ", ".join([f"[{i+1}]" for i in range(len(ctx))])
        add_session_turn(body.session_id, "assistant", reply)
        srcs = [
            {"id": c["id"], "url": c["metadata"].get("url"), "type": c["metadata"].get("type")}
            for c in ctx
        ]
        return {"reply": reply, "sources": srcs}
    except Exception:
        import traceback
        with open("last_error.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise


class IngestIn(BaseModel):
    site: str
    max_pages: int = 40


@app.post("/ingest")
def ingest_site(body: IngestIn):
    site = body.site.strip()
    if not site.startswith("http://") and not site.startswith("https://"):
        site = "https://" + site
    domain = urllib.parse.urlparse(site).netloc or site
    docs = []
    for i, p in enumerate(crawl(site, max_pages=body.max_pages)):
        text = (p.get("text") or "").strip()
        if not text:
            continue
        docs.append(
            {
                "id": f"{domain}-page-{i}",
                "text": text[:5000],
                "metadata": {"url": p.get("url", site), "type": "page", "domain": domain},
            }
        )
    _upsert(pages, docs)
    return {"ok": True, "domain": domain, "pages": len(docs)}


@app.get("/health")
def health():
    return {"ok": True}

@app.post("/echo")
def echo(body: ChatIn):
    return body.model_dump()
