# %% [markdown]
# # Gemma 4 Mycelium — LoRA Fine-Tune
#
# Cultivation-domain LoRA adapter on Gemma 4 E4B, trained on:
# - Lion's Mane Commercial SOP
# - The Mushroom Grower Vol 1 & Vol 2
# - Mycelium EI Engine technical docs
#
# Targets Kaggle's free GPU tier (P100 16GB) but runs equally on a local A100
# or Modal/Replicate. ~3-4 hours wall time on P100 for 3 epochs over 3k
# chunks at sequence length 2048.
#
# **Conversion to .ipynb**: `jupytext --to ipynb scripts/finetune_lora.py`
# Or import directly into Kaggle as a .py notebook (Kaggle supports both).
#
# **Cell markers**: Cells are separated by `# %%`. The notebook layout
# matches the typical LoRA-SFT pipeline so each cell can be re-run
# independently while iterating.

# %% [markdown]
# ## 1. Environment

# %%
import os
import sys
import subprocess

# Install dependencies. Gemma 4 is bleeding-edge; Kaggle's pre-installed
# transformers raises ``KeyError: 'gemma4'`` when loading. Always install
# transformers from main on Kaggle until a tagged release adds Gemma 4
# support. The rest are version-pinned to known-compatible releases.
def _ensure_deps():
    in_kaggle = "KAGGLE_KERNEL_RUN_TYPE" in os.environ
    try:
        import transformers
        if hasattr(transformers.models, "gemma4") or not in_kaggle:
            import peft, trl, bitsandbytes, datasets, accelerate  # noqa
            print(f"deps already installed (transformers {transformers.__version__})")
            return
        print(f"transformers {transformers.__version__} lacks gemma4 — upgrading")
    except ImportError:
        pass
    pkgs = [
        # transformers from main covers Gemma 4 + Gemma 3 + every recent release.
        "transformers @ git+https://github.com/huggingface/transformers.git",
        "peft>=0.13.0",
        "trl>=0.12.0",
        "bitsandbytes>=0.44.0",
        "datasets>=3.0.0",
        "accelerate>=1.0.0",
        "sentencepiece",
        "protobuf",
    ]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *pkgs])

_ensure_deps()

import torch
print(f"torch: {torch.__version__}")
print(f"cuda available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"gpu: {torch.cuda.get_device_name(0)}")
    print(f"vram total: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")

# %% [markdown]
# ## 2. HuggingFace authentication
#
# Gemma 4 is gated. The user must have accepted the Gemma terms at
# https://huggingface.co/google/gemma-4-e4b *and* set HF_TOKEN as a Kaggle
# secret named `HF_TOKEN`. Locally, `huggingface-cli login` works equally.

# %%
from huggingface_hub import login

hf_token = os.environ.get("HF_TOKEN", "")
if not hf_token:
    # Kaggle secrets shim
    try:
        from kaggle_secrets import UserSecretsClient
        hf_token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:
        pass
if hf_token:
    login(token=hf_token, add_to_git_credential=False)
    print("HF authenticated")
else:
    raise RuntimeError(
        "HF_TOKEN is not set. Add it as a Kaggle secret named 'HF_TOKEN':\n"
        "  1. Open this notebook on Kaggle\n"
        "  2. Add-ons -> Secrets -> Add a new secret\n"
        "  3. Label: HF_TOKEN, Value: <your hf token from huggingface.co/settings/tokens>\n"
        "  4. Toggle 'Attached' so the notebook can read it\n"
        "Gemma 4 is a gated model; loading it without auth will 401."
    )

# %% [markdown]
# ## 3. Model + tokenizer
#
# Loads Gemma 4 E4B in 4-bit (QLoRA) to fit P100/T4. If you have an A100
# 40GB, set `LOAD_4BIT = False` for full bf16 LoRA — converges faster and
# usually yields better adapter quality.

# %%
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

BASE_MODEL = os.environ.get("BASE_MODEL", "google/gemma-4-e4b")
LOAD_4BIT = os.environ.get("LOAD_4BIT", "true").lower() == "true"

# QLoRA quantization config — nf4 + double quant + bf16 compute is the
# Tim Dettmers recipe that the QLoRA paper recommends for Gemma-class
# models. Don't tweak unless you've measured loss/throughput on a calibration
# set.
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
) if LOAD_4BIT else None

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
    attn_implementation="eager",  # Gemma 4 uses fused attention by default;
                                  # eager is more compatible with PEFT hooks.
)
model.config.use_cache = False
model.gradient_checkpointing_enable()
print(f"loaded {BASE_MODEL} ({'4-bit' if LOAD_4BIT else 'bf16'})")

# %% [markdown]
# ## 4. LoRA adapter
#
# Target modules cover Gemma's attention + MLP linear layers. r=16 with
# alpha=32 (2× r is the standard ratio) lands the adapter at ~30MB — small
# enough to ship with the model card and merge cleanly.

# %%
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

if LOAD_4BIT:
    model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# %% [markdown]
# ## 5. Dataset
#
# The corpus is built by ``scripts/prepare_corpus.py`` and ships in
# ``data/instruct.jsonl``. On Kaggle, attach this repo as a dataset and the
# file lands at ``/kaggle/input/crowe-mycelium-cli/data/instruct.jsonl``.

# %%
from datasets import load_dataset

DATA_PATH = os.environ.get(
    "INSTRUCT_JSONL",
    str(next(
        (p for p in [
            "data/instruct.jsonl",
            "/kaggle/input/gemma-4-mycelium-corpus/instruct.jsonl",
            "/kaggle/input/crowe-mycelium-cli/data/instruct.jsonl",
            "/kaggle/working/instruct.jsonl",
        ] if os.path.exists(p)),
        "data/instruct.jsonl",  # fallback path even if missing
    )),
)
print(f"loading: {DATA_PATH}")
ds = load_dataset("json", data_files=DATA_PATH, split="train")
print(f"records: {len(ds)}")

# Gemma chat template — chat_template applies the model's native
# <start_of_turn> / <end_of_turn> tokens. Each row becomes one assistant
# turn keyed on the instruction; we drop the empty ``input`` field.
SYSTEM = (
    "You are Gemma 4 Mycelium, an offline cultivation intelligence built on "
    "Gemma 4 by Crowe Logic. Ground every claim in commercial mycology "
    "practice. Be direct and concrete."
)

def format_example(example):
    messages = [
        {"role": "user", "content": f"{SYSTEM}\n\n{example['instruction']}"},
        {"role": "assistant", "content": example["output"]},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return {"text": text}

ds = ds.map(format_example, remove_columns=ds.column_names)
print(f"sample formatted record (first 400 chars):\n{ds[0]['text'][:400]}")

# %% [markdown]
# ## 6. Training
#
# 3 epochs at lr=2e-4 is the QLoRA paper's recipe for instruction tuning;
# it overfits on 1-2k examples and undertrains on 10k+. Our corpus sits
# at ~3k examples so 3 epochs is the right zone. Drop to 1-2 epochs if
# your run shows loss converging by epoch 2.

# %%
from trl import SFTConfig, SFTTrainer

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "lora-gemma-4-mycelium-e4b")

sft_config = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,    # effective batch 16
    gradient_checkpointing=True,
    optim="paged_adamw_8bit",
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.01,
    max_grad_norm=0.3,
    bf16=True,
    logging_steps=10,
    save_steps=200,
    save_total_limit=3,
    report_to="none",                 # set to "wandb" if you've wired it
    max_seq_length=2048,
    packing=False,                    # packing hurts instruction-tuning loss
    dataset_text_field="text",
)

trainer = SFTTrainer(
    model=model,
    args=sft_config,
    train_dataset=ds,
    tokenizer=tokenizer,
)
trainer.train()
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"saved adapter to {OUTPUT_DIR}")

# %% [markdown]
# ## 7. Sanity check — sample generations
#
# Run a few cultivation queries through the adapter to confirm it
# learned the corpus voice (and didn't catastrophically forget).

# %%
from peft import PeftModel

eval_model = model
eval_model.eval()

probes = [
    "What is the optimal substrate composition for commercial Lion's Mane production?",
    "My agar plate has turned pink. What's happening and what should I do?",
    "Walk me through the spawn run phase for oyster mushrooms.",
]

for q in probes:
    messages = [{"role": "user", "content": f"{SYSTEM}\n\n{q}"}]
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, return_tensors="pt", add_generation_prompt=True
    ).to(eval_model.device)
    with torch.no_grad():
        out = eval_model.generate(
            inputs, max_new_tokens=256, temperature=0.4, top_p=0.9,
            do_sample=True, pad_token_id=tokenizer.eos_token_id,
        )
    reply = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    print(f"\nQ: {q}\nA: {reply}\n{'-'*60}")

# %% [markdown]
# ## 8. Push adapter to HuggingFace
#
# Pushes the LoRA adapter (~30MB) to a public HF repo. The full merged
# model is built separately — see cell 9.

# %%
HF_REPO = os.environ.get("HF_REPO", "crowelogic/gemma-4-mycelium-e4b-lora")
PUSH_TO_HF = os.environ.get("PUSH_TO_HF", "false").lower() == "true"

if PUSH_TO_HF and hf_token:
    from huggingface_hub import HfApi, create_repo
    create_repo(HF_REPO, repo_type="model", exist_ok=True, private=False)
    trainer.model.push_to_hub(HF_REPO, use_auth_token=hf_token)
    tokenizer.push_to_hub(HF_REPO, use_auth_token=hf_token)
    print(f"pushed adapter to https://huggingface.co/{HF_REPO}")
else:
    print(f"skipping HF push (PUSH_TO_HF={PUSH_TO_HF}, hf_token set={bool(hf_token)})")

# %% [markdown]
# ## 9. Merge + GGUF conversion (optional, for Ollama)
#
# To ship via Ollama, merge the LoRA into the base weights and convert to
# GGUF. This requires llama.cpp's convert scripts; bigger compute than
# Kaggle's free tier usually has, so this cell is meant for the post-
# training step on a beefier machine.

# %%
# !pip install -q llama-cpp-python  # adds the convert_hf_to_gguf utility
#
# from peft import PeftModel
# merged = PeftModel.from_pretrained(model, OUTPUT_DIR).merge_and_unload()
# merged.save_pretrained("merged-gemma-4-mycelium-e4b", safe_serialization=True)
# tokenizer.save_pretrained("merged-gemma-4-mycelium-e4b")
#
# # Convert to GGUF (run from a shell):
# # python -m llama_cpp.convert_hf_to_gguf merged-gemma-4-mycelium-e4b \
# #   --outfile gemma-4-mycelium-e4b.gguf --outtype q4_k_m
#
# # Then point the project Modelfile at the GGUF:
# # FROM ./gemma-4-mycelium-e4b.gguf
# # ollama create crowelogic/gemma-4-mycelium-e4b -f modelfile/Modelfile

# %% [markdown]
# ## 10. Final notes
#
# - On a P100 the run takes ~3-4 hours for 3 epochs on this corpus size.
#   Watch the loss curve; if it plateaus by step ~1000 you can early-stop.
# - For the Gemma 4 Good Hackathon submission, the artifact to publish is
#   the adapter at ``crowelogic/gemma-4-mycelium-e4b-lora`` on HF. The
#   merged + GGUF version is convenience packaging for Ollama users.
# - The Modelfile in this repo currently uses ``FROM gemma4:e4b`` plus a
#   system prompt overlay. After the LoRA ships, swap to a merged GGUF
#   and the system prompt becomes secondary (the model will have learned
#   the cultivation voice).
