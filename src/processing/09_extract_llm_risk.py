#!/usr/bin/env python3
"""
09_extract_llm_risk.py — Phase 7 LLM extraction runner (multi-provider, config-driven).

Reads risk-section .md files, sends each to one or more models, writes one CSV row
per (file x model). Supports BOTH providers so free vs paid can be compared on the
same files with the same schema + prompt:
    * OpenAI  gpt-5.6-*   -> Responses API (client.responses.parse)
    * Gemini  gemini-*    -> google-genai   (response_schema=RiskExtraction)

The schema (risk_extraction_schema.py) and the system prompt are IDENTICAL across
providers; only the API call differs, and that is handled here.

Keys live in .env / environment (never in config): OpenAI reads [openai].api_key_env
(default OPENAI_API_KEY), Gemini reads [gemini].api_key_env (default GEMINI_API_KEY).
Only the SDK for the providers you actually use needs to be installed:
    pip install openai        # if using gpt-* models
    pip install google-genai  # if using gemini-* models

Run:  python src/processing/09_extract_llm_risk.py         # uses config.toml
CLI flags override config; precedence = CLI > config.toml > built-in default.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from risk_extraction_schema import RiskExtraction  # same folder

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]  # src/processing -> src -> root
DEFAULT_CONFIG = PROJECT_ROOT / "config.toml"

# USD per 1M tokens (input, output). Gemini free-tier Flash = 0. Batch halves OpenAI.
PRICES = {
    "gpt-5.6-luna": (1.0, 6.0),
    "gpt-5.6-terra": (2.5, 15.0),
    "gpt-5.6-sol": (5.0, 30.0),
    "gemini-2.5-flash": (0.0, 0.0),
    "gemini-3-flash": (0.0, 0.0),
    "gemini-2.5-flash-lite": (0.0, 0.0),
}

SCHEMA_FIELDS = list(RiskExtraction.model_fields.keys())
META_FIELDS = [
    "stem", "model_requested", "model_resolved", "status", "refusal", "error",
    "input_tokens", "output_tokens", "est_cost_usd", "timestamp",
]
CSV_COLUMNS = META_FIELDS + SCHEMA_FIELDS


# --------------------------- config + secrets ---------------------------
def load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        return
    except ImportError:
        pass
    envf = root / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def resolve(p: str | None) -> Path | None:
    if not p:
        return None
    q = Path(p)
    return q if q.is_absolute() else PROJECT_ROOT / q


def provider_of(model: str) -> str:
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith("gemini"):
        return "gemini"
    raise ValueError(f"Cannot infer provider for model '{model}'. "
                     f"Use a gpt-* or gemini-* model id.")


# ------------------------------- I/O -----------------------------------
def load_done(out_path: Path) -> set[tuple[str, str]]:
    if not out_path.exists():
        return set()
    done = set()
    with out_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "ok":          # only real successes block a rerun
                done.add((row["stem"], row["model_requested"]))
    return done


def append_row(out_path: Path, row: dict) -> None:
    new = not out_path.exists()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


def est_cost(model: str, in_tok: int, out_tok: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return in_tok / 1e6 * pin + out_tok / 1e6 * pout


# ---------------------------- provider calls ---------------------------
def call_openai(client, model, system_prompt, text, effort, max_out):
    import openai
    transient = (openai.RateLimitError, openai.APITimeoutError,
                 openai.APIConnectionError, openai.InternalServerError)
    last = None
    for attempt in range(5):
        try:
            resp = client.responses.parse(
                model=model,
                input=[{"role": "system", "content": system_prompt},
                       {"role": "user", "content": text}],
                text_format=RiskExtraction,
                reasoning={"effort": effort},
                max_output_tokens=max_out,
            )
            parsed = resp.output_parsed
            refusal = ""
            if parsed is None:
                for item in getattr(resp, "output", []) or []:
                    for c in getattr(item, "content", []) or []:
                        if getattr(c, "type", "") == "refusal":
                            refusal = getattr(c, "refusal", "") or "refused"
            u = getattr(resp, "usage", None)
            in_tok = getattr(u, "input_tokens", 0) or 0
            out_tok = getattr(u, "output_tokens", 0) or 0
            status = "ok" if parsed is not None else (
                "refusal" if refusal else getattr(resp, "status", "empty"))
            return (parsed, getattr(resp, "model", model), getattr(resp, "id", ""),
                    status, refusal, in_tok, out_tok, "")
        except transient as e:
            last = e
            time.sleep(2 ** attempt)
        except Exception as e:
            return (None, model, "", "error", "", 0, 0, repr(e))
    return (None, model, "", "error", "", 0, 0, repr(last))


def call_gemini(client, model, system_prompt, text, max_out):
    # google-genai retries 408/429/5xx internally (tenacity); we log the rest.
    from google.genai import types
    try:
        resp = client.models.generate_content(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=RiskExtraction,
                max_output_tokens=max_out,
            ),
        )
        parsed = resp.parsed  # RiskExtraction instance, or None
        refusal, status = "", "ok"
        if parsed is None:
            fr = ""
            try:
                fr = str(resp.candidates[0].finish_reason)
            except Exception:
                pass
            pf = getattr(resp, "prompt_feedback", None)
            refusal = (f"finish_reason={fr}" + (f" prompt_feedback={pf}" if pf else "")
                       ).strip()
            status = "refusal" if ("SAFETY" in refusal.upper()
                                   or "BLOCK" in refusal.upper()) else "empty"
        um = getattr(resp, "usage_metadata", None)
        in_tok = getattr(um, "prompt_token_count", 0) or 0
        out_tok = ((getattr(um, "candidates_token_count", 0) or 0)
                   + (getattr(um, "thoughts_token_count", 0) or 0))
        return (parsed, getattr(resp, "model_version", model) or model, "",
                status, refusal, in_tok, out_tok, "")
    except Exception as e:
        return (None, model, "", "error", "", 0, 0, repr(e))


def dry_row(stem, model):
    stub = RiskExtraction(
        issuer_name_as_stated="<dry-run>",
        extraction_reasoning="dry run — no API call made",
        source_currency_unit="not_stated",
        criminal_cases_against_count=None, regulatory_actions_against_count=None,
        tax_proceedings_against_count=None,
        total_litigation_against_amount_cr=None,
        contingent_liabilities_total_cr=None,
        going_concern_status="not_mentioned", auditor_report_status="not_mentioned",
        top5_customer_revenue_pct=None, top10_customer_revenue_pct=None,
    )
    row = {"stem": stem, "model_requested": model, "model_resolved": "dry-run",
           "status": "dry_run", "refusal": "", "error": "", "input_tokens": 0,
           "output_tokens": 0, "est_cost_usd": 0.0,
           "timestamp": datetime.now(timezone.utc).isoformat()}
    row.update(stub.model_dump())
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 7 LLM risk extraction runner")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--models", nargs="+", default=None)
    ap.add_argument("--reasoning", default=None,
                    choices=["none", "low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--risk-dir", default=None)
    ap.add_argument("--system-prompt", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--max-output-tokens", type=int, default=None)
    ap.add_argument("--dry-run", dest="dry_run", action="store_true", default=None)
    ap.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    oi = cfg.get("openai", {})
    gm = cfg.get("gemini", {})
    pa = cfg.get("paths", {})
    rn = cfg.get("run", {})

    models = args.models or oi.get("models", ["gpt-5.6-luna"])
    reasoning = args.reasoning or oi.get("reasoning_effort", "low")
    max_out = args.max_output_tokens or oi.get("max_output_tokens", 8000)
    gem_interval = float(gm.get("request_interval_seconds", 0) or 0)

    risk_dir = resolve(args.risk_dir) or resolve(pa.get("risk_dir")) or \
        (PROJECT_ROOT / "data" / "processed" / "risk_sections")
    prompt_path = resolve(args.system_prompt) or resolve(pa.get("system_prompt")) or \
        (SCRIPT_DIR / "system_prompt_risk_extraction.md")
    out_path = resolve(args.out) or resolve(pa.get("out")) or \
        (PROJECT_ROOT / "data" / "features" / "_trial_llm_risk.csv")
    raw_dir = resolve(args.raw_dir) or resolve(pa.get("raw_dir"))

    dry_run = args.dry_run if args.dry_run is not None else rn.get("dry_run", False)
    files = args.files if args.files is not None else rn.get("files", [])
    limit = args.limit if args.limit is not None else rn.get("limit", 0)

    if not prompt_path.exists():
        print(f"System prompt not found: {prompt_path}", file=sys.stderr)
        return 1
    system_prompt = prompt_path.read_text(encoding="utf-8")

    stems = ([s[:-3] if s.endswith(".md") else s for s in files] if files
             else sorted(p.stem for p in risk_dir.glob("*.md")))
    if limit:
        stems = stems[:limit]
    if not stems:
        print(f"No .md files found in {risk_dir}", file=sys.stderr)
        return 1

    # validate providers up front
    try:
        providers_used = {provider_of(m) for m in models}
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    clients = {}
    if not dry_run:
        load_env(PROJECT_ROOT)
        if "openai" in providers_used:
            env = oi.get("api_key_env", "OPENAI_API_KEY")
            if not os.environ.get(env):
                print(f"{env} not set (needed for gpt-* models). Put it in "
                      f"{PROJECT_ROOT/'.env'} or export it.", file=sys.stderr)
                return 1
            from openai import OpenAI
            clients["openai"] = OpenAI(api_key=os.environ[env])
        if "gemini" in providers_used:
            genv = gm.get("api_key_env", "GEMINI_API_KEY")
            if not os.environ.get(genv):
                print(f"{genv} not set (needed for gemini-* models). Put it in "
                      f"{PROJECT_ROOT/'.env'} or export it.", file=sys.stderr)
                return 1
            from google import genai
            clients["gemini"] = genai.Client(api_key=os.environ[genv])

    done = load_done(out_path)
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)

    total_cost = 0.0
    n_ok = n_skip = n_fail = 0
    print(f"config: {args.config}")
    print(f"{len(stems)} file(s) x {len(models)} model(s) -> {out_path}")
    print(f"models={models}  reasoning.effort={reasoning}  dry_run={dry_run}\n")

    for stem in stems:
        md = risk_dir / f"{stem}.md"
        if not md.exists():
            print(f"  MISSING  {stem}"); n_fail += 1; continue
        text = md.read_text(encoding="utf-8", errors="replace")
        for model in models:
            if (stem, model) in done:
                print(f"  skip     {stem[:34]:34} [{model}] (done)"); n_skip += 1
                continue

            if dry_run:
                row = dry_row(stem, model)
            else:
                prov = provider_of(model)
                if prov == "gemini" and gem_interval > 0:
                    time.sleep(gem_interval)
                if prov == "openai":
                    res = call_openai(clients["openai"], model, system_prompt,
                                      text, reasoning, max_out)
                else:
                    res = call_gemini(clients["gemini"], model, system_prompt,
                                      text, max_out)
                parsed, resolved, rid, status, refusal, in_tok, out_tok, err = res
                cost = est_cost(model, in_tok, out_tok); total_cost += cost
                row = {"stem": stem, "model_requested": model,
                       "model_resolved": resolved, "status": status,
                       "refusal": refusal, "error": err, "input_tokens": in_tok,
                       "output_tokens": out_tok, "est_cost_usd": round(cost, 4),
                       "timestamp": datetime.now(timezone.utc).isoformat()}
                if parsed is not None:
                    row.update(parsed.model_dump())
                    if raw_dir:
                        (raw_dir / f"{stem}__{model}.json").write_text(
                            parsed.model_dump_json(indent=2), encoding="utf-8")

            append_row(out_path, row)
            st = row["status"]
            if st in {"ok", "dry_run"}:
                n_ok += 1
                print(f"  {st:8} {stem[:34]:34} [{model}]  "
                      f"crim={row.get('criminal_cases_against_count')} "
                      f"reg={row.get('regulatory_actions_against_count')} "
                      f"tax={row.get('tax_proceedings_against_count')} "
                      f"cont={row.get('contingent_liabilities_total_cr')} "
                      f"${row.get('est_cost_usd', 0)}")
            else:
                n_fail += 1
                print(f"  {st:8} {stem[:34]:34} [{model}]  "
                      f"{row.get('refusal') or row.get('error')}")

    print(f"\nDone. ok={n_ok} skipped={n_skip} failed={n_fail}  "
          f"est_total=${total_cost:.4f}  (Gemini free-tier calls cost $0)")
    print(f"Wrote {out_path}")
    if not dry_run:
        print("Next: python src/processing/score_extraction.py --csv " + str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())