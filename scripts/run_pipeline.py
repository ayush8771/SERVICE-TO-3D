"""
run_pipeline.py
----------------
End-to-end entrypoint.

    python run_pipeline.py <path/to/model.glb> <path/to/service_steps.json> \
        [--out mapping.json] [--top-k 12] [--no-gemini]

Produces mapping.json:
{
  "step_id": {
    "title": ...,
    "expected_count": N,
    "matched_node_indices": [...],
    "matched_mesh_names": [...],
    "confidence": "high"|"medium"|"low",
    "source": "gemini" | "rule_based_fallback",
    "reasoning": "...",
    "all_candidates_considered": [...]   # transparency / audit trail
  },
  ...
}

Set the GEMINI_API_KEY environment variable to enable the agentic
refinement layer (gemini_agent.py); otherwise the pipeline still runs to
completion using the deterministic rule-based ranking only.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from matcher import build_all_candidates
from gemini_agent import refine_step


def confidence_label(candidates, chosen_ids, expected_count):
    if not candidates:
        return "low"
    top_scores = [c.score for c in candidates[:max(expected_count, 1)]]
    avg = sum(top_scores) / len(top_scores)
    n_found = len([c for c in candidates if c.node_index in chosen_ids])
    if avg >= 3.5 and n_found >= expected_count:
        return "high"
    if avg >= 1.5:
        return "medium"
    return "low"


def run(glb_path, steps_path, out_path, top_k=12, use_gemini=True):
    print(f"[1/4] Extracting GLB geometry + lexical features from {glb_path} ...")
    result, features, by_idx = build_all_candidates(glb_path, steps_path, top_k=top_k)
    print(f"      {len(features)} mesh nodes processed.")

    print(f"[2/4] Ranked candidates for {len(result)} service steps.")

    if use_gemini and not os.environ.get("GEMINI_API_KEY"):
        print("      NOTE: GEMINI_API_KEY not set -- agentic refinement will be "
              "skipped and the top rule-based candidates will be used directly. "
              "Export GEMINI_API_KEY to enable the LLM refinement/self-critique loop.")

    mapping = {}
    print("[3/4] Refining selections" + (" via Gemini agentic loop..." if use_gemini else " (rule-based only)..."))
    for step_id, r in result.items():
        step, candidates = r["step"], r["candidates"]
        if use_gemini:
            if os.environ.get("GEMINI_API_KEY"):
                time.sleep(4)  # stay under free-tier requests-per-minute cap
            ids, reasoning, source = refine_step(step, candidates, by_idx)
        else:
            ids = [c.node_index for c in candidates[:step.expected_count]]
            reasoning = "Rule-based ranking only (Gemini disabled)."
            source = "rule_based_fallback"

        names = [by_idx[i].raw_name for i in ids if i in by_idx]
        mapping[step_id] = {
            "title": step.title,
            "instruction": step.instruction,
            "expected_count": step.expected_count,
            "matched_node_indices": ids,
            "matched_mesh_names": names,
            "confidence": confidence_label(candidates, set(ids), step.expected_count),
            "source": source,
            "reasoning": reasoning,
            "all_candidates_considered": [
                {"node_index": c.node_index, "raw_name": c.raw_name,
                 "score": round(c.score, 2), "reasons": c.reasons}
                for c in candidates
            ],
        }
        print(f"      {step_id:6s} -> {names} ({source}, confidence={mapping[step_id]['confidence']})")

    print(f"[4/4] Writing {out_path}")
    Path(out_path).write_text(json.dumps(mapping, indent=2))
    print("Done.")
    return mapping


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("glb_path")
    ap.add_argument("steps_path")
    ap.add_argument("--out", default="mapping.json")
    ap.add_argument("--top-k", type=int, default=12)
    ap.add_argument("--no-gemini", action="store_true")
    args = ap.parse_args()
    run(args.glb_path, args.steps_path, args.out, top_k=args.top_k, use_gemini=not args.no_gemini)