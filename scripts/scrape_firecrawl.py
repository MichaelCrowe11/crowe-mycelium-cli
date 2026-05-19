"""Firecrawl-based mycology corpus scraper.

Pulls Creative-Commons / public-domain mycology content (Wikipedia by default,
user-supplied seed URLs allowed) and chunks each page into instruction/output
pairs suitable for SFT.

Each section heading becomes an instruction; its body becomes the response.
Output JSONL shards land in shards/ following the same schema as magpie shards
(so finetune_lora_unsloth.py consumes them transparently).

Usage:
    python scripts/scrape_firecrawl.py                          # default seed list
    python scripts/scrape_firecrawl.py --urls urls.txt          # custom URLs (one per line)
    python scripts/scrape_firecrawl.py --crawl 20               # crawl 20 pages from each seed

Requires FIRECRAWL_API_KEY in .env (already stored).
"""
import argparse, hashlib, json, os, re
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Default seed URLs — Wikipedia (CC-BY-SA). Safe to redistribute with attribution.
DEFAULT_SEEDS = [
    "https://en.wikipedia.org/wiki/Hericium_erinaceus",
    "https://en.wikipedia.org/wiki/Mushroom_cultivation",
    "https://en.wikipedia.org/wiki/Fungiculture",
    "https://en.wikipedia.org/wiki/Mycology",
    "https://en.wikipedia.org/wiki/Mycelium",
    "https://en.wikipedia.org/wiki/Substrate_(biology)",
    "https://en.wikipedia.org/wiki/Edible_mushroom",
    "https://en.wikipedia.org/wiki/Psilocybin_mushroom",
    "https://en.wikipedia.org/wiki/Psilocybin",
    "https://en.wikipedia.org/wiki/Psilocin",
    "https://en.wikipedia.org/wiki/Pleurotus_ostreatus",
    "https://en.wikipedia.org/wiki/Lentinula_edodes",
    "https://en.wikipedia.org/wiki/Ganoderma_lucidum",
    "https://en.wikipedia.org/wiki/Cordyceps_militaris",
    "https://en.wikipedia.org/wiki/Trichoderma",
    "https://en.wikipedia.org/wiki/Amanita_phalloides",
    "https://en.wikipedia.org/wiki/Beta-glucan",
    "https://en.wikipedia.org/wiki/Nerve_growth_factor",
]


def chunk_markdown(md: str, source_url: str, min_section_chars: int = 200) -> list:
    """Split markdown into heading+body chunks → instruction/output pairs."""
    # Split on H2/H3 (skip H1 which is usually the page title)
    parts = re.split(r"^(##+\s+.*)$", md, flags=re.MULTILINE)
    out = []
    current_heading = None
    for part in parts:
        if part.startswith("##"):
            current_heading = re.sub(r"^#+\s+", "", part).strip()
            # strip Wikipedia edit links etc.
            current_heading = re.sub(r"\[\s*edit\s*\]", "", current_heading, flags=re.I).strip()
        else:
            body = part.strip()
            if current_heading and len(body) >= min_section_chars:
                # Strip Wikipedia reference brackets like [1] [citation needed]
                body = re.sub(r"\[\s*\d+\s*\]", "", body)
                body = re.sub(r"\[\s*citation needed\s*\]", "", body, flags=re.I)
                body = re.sub(r"\s+", " ", body).strip()
                # Cap length — over-long bodies hurt training
                if len(body) > 3000:
                    body = body[:3000].rsplit(".", 1)[0] + "."
                out.append({
                    "instruction": current_heading,
                    "output": body,
                    "source": "firecrawl",
                    "source_url": source_url,
                    "ts": datetime.utcnow().isoformat(timespec="seconds"),
                })
            current_heading = None
    return out


def hash_example(ex):
    return hashlib.md5((ex["instruction"] + "||" + ex["output"]).encode()).hexdigest()


def load_env(path: Path = REPO_ROOT / ".env"):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def main(args):
    load_env()
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        raise SystemExit("FIRECRAWL_API_KEY not set (expected in .env)")

    try:
        from firecrawl import Firecrawl
    except ImportError:
        try:
            from firecrawl import FirecrawlApp as Firecrawl
        except ImportError:
            raise SystemExit("pip install firecrawl-py")

    fc = Firecrawl(api_key=api_key)

    seeds = DEFAULT_SEEDS
    if args.urls:
        seeds = [l.strip() for l in Path(args.urls).read_text().splitlines() if l.strip()]

    shards_dir = REPO_ROOT / "shards"
    shards_dir.mkdir(exist_ok=True)

    seen = set()
    for f in shards_dir.glob("*.jsonl"):
        for line in open(f, encoding="utf-8"):
            try: seen.add(hash_example(json.loads(line)))
            except: pass
    print(f"[scrape] {len(seen)} existing examples (dedup baseline)")

    shard_idx = 0
    while (shards_dir / f"scrape_{shard_idx:04d}.jsonl").exists():
        shard_idx += 1

    pending = []
    n_pages_done = 0
    for url in seeds:
        print(f"[scrape] {url}")
        md = None
        try:
            if hasattr(fc, "scrape"):
                result = fc.scrape(url, formats=["markdown"])
            else:
                result = fc.scrape_url(url, formats=["markdown"])
            if hasattr(result, "markdown"):
                md = result.markdown
            elif isinstance(result, dict):
                md = result.get("markdown") or result.get("data", {}).get("markdown")
        except Exception as e:
            print(f"  failed: {e}")
            continue
        if not md:
            print("  no markdown content")
            continue

        chunks = chunk_markdown(md, url, min_section_chars=args.min_chars)
        kept = 0
        for ex in chunks:
            h = hash_example(ex)
            if h in seen: continue
            seen.add(h)
            pending.append(ex)
            kept += 1
            if len(pending) >= args.shard_size:
                fp = shards_dir / f"scrape_{shard_idx:04d}.jsonl"
                fp.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in pending), encoding="utf-8")
                update_manifest(shards_dir, fp.name, len(pending), "firecrawl")
                print(f"[scrape] Wrote {fp.name} ({len(pending)} ex)")
                pending = []
                shard_idx += 1
        n_pages_done += 1
        print(f"  +{kept} examples (page {n_pages_done}/{len(seeds)})")

    if pending:
        fp = shards_dir / f"scrape_{shard_idx:04d}.jsonl"
        fp.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in pending), encoding="utf-8")
        update_manifest(shards_dir, fp.name, len(pending), "firecrawl")
        print(f"[scrape] Wrote final {fp.name} ({len(pending)} ex)")


def update_manifest(shards_dir, shard_name, n_examples, source):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try: data = json.loads(mf.read_text())
        except: pass
    data.setdefault("shards", []).append({
        "file": shard_name, "examples": n_examples, "teacher": source,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--urls", help="path to file with one URL per line; overrides default seeds")
    p.add_argument("--shard-size", type=int, default=200, help="examples per JSONL shard")
    p.add_argument("--min-chars", type=int, default=200, help="minimum section body length to keep")
    main(p.parse_args())
