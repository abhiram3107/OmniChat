"""
CLI to ingest: website pages, orders CSV/JSON, and conversation logs JSONL.
Usage examples:
  python ingest.py --site https://example.com --max_pages 40
  python ingest.py --orders ./orders.csv --domain myshop.com
  python ingest.py --convos ./logs.jsonl --domain myshop.com

Notes:
- If --domain is provided, it is applied to metadata.domain for all documents.
- If --domain is omitted, pages use the site's domain (derived from URL),
  while orders and convos default to "global" for backward compatibility.
"""
import csv, json, argparse
from store import _upsert, pages, orders, chats
import urllib.parse
from crawler import crawl

parser = argparse.ArgumentParser()
parser.add_argument("--site")
parser.add_argument("--max_pages", type=int, default=40)
parser.add_argument("--orders")
parser.add_argument("--convos")
parser.add_argument("--domain", help="Override metadata.domain for all docs. If omitted, pages use site domain; orders/convos default to 'global'.")
args = parser.parse_args()

if args.site:
    docs = []
    derived = urllib.parse.urlparse(args.site).netloc or args.site
    page_domain = args.domain or derived
    for i, p in enumerate(crawl(args.site, max_pages=args.max_pages)):
        if not p["text"].strip():
            continue
        docs.append(
            {
                "id": f"{page_domain}-page-{i}",
                "text": p["text"][:5000],
                "metadata": {"url": p["url"], "type": "page", "domain": page_domain},
            }
        )
    _upsert(pages, docs)
    print(f"Ingested {len(docs)} pages for domain '{page_domain}'")

if args.orders:
    docs = []
    with open(args.orders, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            oid = row.get("order_id") or row.get("id")
            text = json.dumps(row, ensure_ascii=False)
            docs.append(
                {
                    "id": f"order-{oid}",
                    "text": text,
                    "metadata": {"type": "order", "order_id": oid, "domain": (args.domain or "global")},
                }
            )
    _upsert(orders, docs)
    print(f"Ingested {len(docs)} orders for domain '{args.domain or 'global'}'")

if args.convos:
    docs = []
    with open(args.convos, encoding="utf-8") as f:
        for i, line in enumerate(f):
            try:
                obj = json.loads(line)
                text = obj.get("text") or obj.get("content") or ""
                docs.append(
                    {
                        "id": f"chat-{i}",
                        "text": text,
                        "metadata": {"type": "chat", "speaker": obj.get("role"), "domain": (args.domain or "global")},
                    }
                )
            except Exception:
                continue
    _upsert(chats, docs)
    print(f"Ingested {len(docs)} chat turns for domain '{args.domain or 'global'}'")
