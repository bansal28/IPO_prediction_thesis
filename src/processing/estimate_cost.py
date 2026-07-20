#!/usr/bin/env python3
"""Estimate the exact Luna cost for the full 416-file run — no API calls, no cost."""
import glob, os
import tiktoken

RISK_DIR = "data/processed/risk_sections"
SYSTEM_PROMPT = "src/processing/system_prompt_risk_extraction.md"
IN_PRICE, OUT_PRICE = 1.0, 6.0          # Luna $/1M (input, output)
EST_OUTPUT_TOKENS = 1500                 # generous per-file output+reasoning estimate

enc = tiktoken.get_encoding("o200k_base")   # GPT-5-family tokenizer
sys_tokens = len(enc.encode(open(SYSTEM_PROMPT, encoding="utf-8").read()))

files = sorted(glob.glob(os.path.join(RISK_DIR, "*.md")))
rows, total_in = [], 0
for f in files:
    doc = open(f, encoding="utf-8", errors="replace").read()
    n_in = sys_tokens + len(enc.encode(doc))     # prompt sent per call
    total_in += n_in
    rows.append((os.path.basename(f), n_in))

n = len(files)
total_out = n * EST_OUTPUT_TOKENS
in_cost  = total_in  / 1e6 * IN_PRICE
out_cost = total_out / 1e6 * OUT_PRICE
total = in_cost + out_cost

rows.sort(key=lambda r: r[1], reverse=True)
print(f"Files: {n}   system prompt: {sys_tokens} tokens/call\n")
print("Top 5 largest files (input tokens):")
for name, t in rows[:5]:
    print(f"  {t:>8,}  {name}")
print(f"\nInput tokens (all files): {total_in:,}")
print(f"Output tokens (est {EST_OUTPUT_TOKENS}/file): {total_out:,}")
print(f"\nInput cost:  ${in_cost:6.2f}")
print(f"Output cost: ${out_cost:6.2f}  (estimate)")
print(f"{'='*30}\nEXPECTED TOTAL: ${total:6.2f}")
print(f"Add ~25% margin for retries/variance -> budget ~${total*1.25:.2f}")