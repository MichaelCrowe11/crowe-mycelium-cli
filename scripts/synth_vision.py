"""Modal-wrapped vision-language synth for grow-room photo Q&A pairs.

Uses a VL teacher (Qwen2.5-VL-7B by default) to caption local mushroom-grow
photos as multi-turn instruction/response pairs for Gemma 4 E4B multimodal
fine-tuning. Each photo yields 5-8 Q&A examples spanning growth stage,
contamination, species ID, substrate, environment, next action, and morphology.

Cost guide (Modal pricing, 2026):
  A10G  ~$1.10/hr  — ~80-150 photos/hr at 6 Q&A each
  L40S  ~$2.00/hr  — ~200-350 photos/hr, fits 7B-VL more comfortably

Usage:
    modal run scripts/synth_vision.py --photos-dir data/photos
    modal run scripts/synth_vision.py --photos-dir data/photos --manifest data/photos.csv --shard-size 500
"""
import json
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("crowe-mycelium-synth-vision")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "build-essential")
    .pip_install(
        "torch>=2.7",
        "transformers>=4.50,<5",
        "accelerate", "bitsandbytes", "peft",
        "huggingface-hub", "sentencepiece", "protobuf",
        "pillow", "qwen-vl-utils",
    )
)

photos_volume = modal.Volume.from_name("crowe-mycelium-photos", create_if_missing=True)

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

QUESTIONS = [
    "What stage of growth is shown in this photo?",
    "Are there any signs of contamination visible? If yes, identify and describe them.",
    "What species or genus is this most likely, and what features support that ID?",
    "What substrate type does this appear to be growing on?",
    "What environmental conditions does this image indicate (humidity, airflow, temperature signs)?",
    "What action should the grower take next based on what is visible?",
    "Identify the morphological features visible in the fruit body (cap, stipe, hymenium, etc.).",
    "Is there anything in this image that warrants a safety or sanitation check before proceeding?",
]


CAPTION_PROMPT = """You are a senior mycologist and commercial mushroom-cultivation expert reviewing a grower's photo.

Context for this photo (may be partial or empty): {context}

Answer the following question about the image, drawing on real cultivation knowledge. Be specific, accurate, and concrete. If the image is ambiguous, say so and explain what additional evidence would resolve it. 80-400 words.

Question: {question}

Respond with ONLY the answer text — no preamble, no JSON, no quotes."""


@app.function(image=image, volumes={"/photos": photos_volume})
def upload_photos(content_map: dict) -> int:
    """Receive {filename: image_bytes} mapping, write to /photos volume."""
    import os
    n = 0
    for name, content in content_map.items():
        path = f"/photos/{os.path.basename(name)}"
        with open(path, "wb") as f:
            f.write(content)
        n += 1
    photos_volume.commit()
    return n


@app.function(image=image, volumes={"/photos": photos_volume})
def list_photos() -> list:
    import os
    if not os.path.isdir("/photos"):
        return []
    return sorted([f for f in os.listdir("/photos")
                   if os.path.splitext(f)[1].lower() in IMG_EXTS])


@app.function(
    image=image, gpu="A10G", timeout=7200,
    volumes={"/photos": photos_volume},
    secrets=[modal.Secret.from_name("huggingface")],
)
def caption_photos(model: str, photos: list, contexts: dict,
                   questions_per_photo: int = 6, max_new_tokens: int = 512,
                   seed: int = 42) -> list:
    """Run VL inference over each photo; emit Q&A example dicts."""
    import hashlib, os, random
    import torch
    from PIL import Image
    from transformers import AutoProcessor, BitsAndBytesConfig

    print(f"[vision-synth] Loading {model}...")
    used_model = model
    try:
        from transformers import AutoModelForImageTextToText
        proc = AutoProcessor.from_pretrained(model, trust_remote_code=True)
        if "bnb-4bit" in model or "4bit" in model.lower():
            m = AutoModelForImageTextToText.from_pretrained(
                model, torch_dtype=torch.bfloat16, device_map="auto",
                trust_remote_code=True,
            )
        else:
            bnb = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            )
            m = AutoModelForImageTextToText.from_pretrained(
                model, quantization_config=bnb, device_map="auto",
                trust_remote_code=True,
            )
    except Exception as e:
        fallback = "Qwen/Qwen2.5-VL-7B-Instruct"
        print(f"[vision-synth] {model} failed ({e}); falling back to {fallback}")
        from transformers import AutoModelForImageTextToText
        used_model = fallback
        proc = AutoProcessor.from_pretrained(fallback, trust_remote_code=True)
        bnb = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
        )
        m = AutoModelForImageTextToText.from_pretrained(
            fallback, quantization_config=bnb, device_map="auto",
            trust_remote_code=True,
        )
    m.eval()

    def ok(instr, resp, image):
        if not image: return False
        if not instr or len(instr) < 10: return False
        if not resp or len(resp) < 40: return False
        low = resp.lower().strip()
        if low.startswith(("i can't", "i'm sorry", "as an ai", "i cannot")): return False
        return True

    rng = random.Random(seed)
    seen = set()
    out = []
    n_q = max(1, min(questions_per_photo, len(QUESTIONS)))

    for idx, fname in enumerate(photos):
        path = f"/photos/{fname}"
        if not os.path.isfile(path):
            print(f"[vision-synth] missing {fname}, skip")
            continue
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            print(f"[vision-synth] cannot open {fname}: {e}")
            continue

        ctx_row = contexts.get(fname, {}) or {}
        ctx_str = ", ".join(f"{k}={v}" for k, v in ctx_row.items() if v) or "none provided"

        # Sample n_q questions for this photo, always including stage + contamination if present.
        chosen = QUESTIONS[:n_q] if n_q <= len(QUESTIONS) else QUESTIONS
        if n_q < len(QUESTIONS):
            chosen = list(dict.fromkeys([QUESTIONS[0], QUESTIONS[1]] +
                                        rng.sample(QUESTIONS[2:], n_q - 2)))[:n_q]

        for question in chosen:
            prompt_text = CAPTION_PROMPT.format(context=ctx_str, question=question)
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": prompt_text},
                ],
            }]
            try:
                chat = proc.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                )
                inputs = proc(text=[chat], images=[img], return_tensors="pt", padding=True)
                inputs = {k: v.to(m.device) for k, v in inputs.items()}
                with torch.no_grad():
                    gen = m.generate(
                        **inputs, max_new_tokens=max_new_tokens,
                        do_sample=True, temperature=0.7, top_p=0.9,
                    )
                prompt_len = inputs["input_ids"].shape[1]
                new_tokens = gen[0][prompt_len:]
                answer = proc.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            except Exception as e:
                print(f"[vision-synth] gen failed on {fname} q={question[:40]}: {e}")
                continue

            if not ok(question, answer, fname):
                continue
            h = hashlib.md5((fname + "||" + question).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            out.append({
                "image": fname,
                "instruction": question,
                "output": answer,
                "context": ctx_row,
                "source": "vision",
                "teacher": used_model,
                "ts": datetime.utcnow().isoformat(timespec="seconds"),
            })
        print(f"[vision-synth] {idx+1}/{len(photos)} {fname}: kept {sum(1 for e in out if e['image']==fname)}")

    return out


def load_manifest(path: Path) -> dict:
    """Load optional per-photo context CSV/JSON keyed by filename."""
    if not path or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                return {r.get("filename") or r.get("image"): {k: v for k, v in r.items()
                        if k not in ("filename", "image")} for r in data if isinstance(r, dict)}
            if isinstance(data, dict):
                return data
            return {}
        # CSV
        import csv, io
        reader = csv.DictReader(io.StringIO(text))
        out = {}
        for r in reader:
            key = r.get("filename") or r.get("image")
            if not key:
                continue
            out[key] = {k: v for k, v in r.items() if k not in ("filename", "image") and v}
        return out
    except Exception as e:
        print(f"[vision-synth] manifest parse failed: {e}; ignoring")
        return {}


def update_manifest(shards_dir, shard_name, n_examples, teacher):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try: data = json.loads(mf.read_text())
        except: pass
    data.setdefault("shards", []).append({
        "file": shard_name, "examples": n_examples, "teacher": teacher,
        "source": "vision",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))


@app.local_entrypoint()
def main(photos_dir: str = "data/photos", manifest: str = "",
         shard_size: int = 300, seed: int = 42,
         max_new_tokens: int = 512, questions_per_photo: int = 6,
         model: str = "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit",
         yes: bool = False):
    repo_root = Path(__file__).resolve().parent.parent
    photos_path = (repo_root / photos_dir) if not Path(photos_dir).is_absolute() else Path(photos_dir)
    shards_dir = repo_root / "shards"
    shards_dir.mkdir(exist_ok=True)

    if not photos_path.exists() or not photos_path.is_dir():
        print(f"No photos found in {photos_path}. Place jpg/png/webp files there and rerun. Skipping.")
        return

    local_photos = sorted([p for p in photos_path.iterdir()
                           if p.is_file() and p.suffix.lower() in IMG_EXTS])
    if not local_photos:
        print(f"No photos found in {photos_path}. Place jpg/png/webp files there and rerun. Skipping.")
        return

    ctx_path = Path(manifest) if manifest else None
    if ctx_path and not ctx_path.is_absolute():
        ctx_path = repo_root / manifest
    contexts = load_manifest(ctx_path) if ctx_path else {}

    print(f"[vision-synth] {len(local_photos)} photos, manifest={'yes' if contexts else 'no'}, "
          f"~{len(local_photos) * questions_per_photo} examples expected")
    if not yes:
        try:
            ans = input("Proceed? [y/N]: ").strip().lower()
        except EOFError:
            ans = "y"
        if ans not in ("y", "yes"):
            print("[vision-synth] aborted")
            return

    print(f"[vision-synth] uploading {len(local_photos)} photos to Modal Volume...")
    content_map = {p.name: p.read_bytes() for p in local_photos}
    n = upload_photos.remote(content_map)
    print(f"[vision-synth] uploaded {n} photos. running VL teacher...")

    photo_names = sorted(content_map.keys())
    examples = caption_photos.remote(
        model=model, photos=photo_names, contexts=contexts,
        questions_per_photo=questions_per_photo,
        max_new_tokens=max_new_tokens, seed=seed,
    )
    print(f"[vision-synth] received {len(examples)} examples from teacher")

    if not examples:
        print("[vision-synth] nothing kept. exit.")
        return

    existing = list(shards_dir.glob("vision_*.jsonl"))
    next_idx = (max((int(p.stem.split("_")[1]) for p in existing), default=-1) + 1)

    teacher_used = examples[0].get("teacher", model)
    written = 0
    for i in range(0, len(examples), shard_size):
        chunk = examples[i:i + shard_size]
        fp = shards_dir / f"vision_{next_idx:04d}.jsonl"
        with open(fp, "w", encoding="utf-8") as f:
            for ex in chunk:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, fp.name, len(chunk), teacher_used)
        print(f"[vision-synth] wrote {fp.name} ({len(chunk)} ex)")
        next_idx += 1
        written += len(chunk)

    print(f"[vision-synth] done. {written} examples across {(written + shard_size - 1)//shard_size} shard(s). "
          f"teacher={teacher_used}. Next: scripts/shard_and_push.ps1")
