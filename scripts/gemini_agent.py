"""
gemini_agent.py
----------------
Agentic refinement layer on top of the deterministic rule-based matcher.

Why an agent and not just "call the LLM once": the rule-based layer already
narrows 102 chaotic meshes down to a short, well-justified candidate list per
step (with explicit reasons: tag overlap, side match, spatial-anchor
proximity...). What it *can't* do well is resolve genuine ties (e.g. "6
near-identical bolts, which exact 6 of the 8 nearby candidates are the
flange bolts") or catch cases where the deterministic count doesn't match
the geometry. So the agent runs a bounded self-critique loop per step:

  1. Propose: ask Gemini to pick exactly `expected_count` node indices from
     the candidate list, given the step text + each candidate's name/tags/
     geometry/score/reasoning, and to explain why.
  2. Verify: check the response is well-formed, uses only offered node
     indices, and returns the requested count.
  3. Retry (<=2 extra attempts): if verification fails, re-prompt with the
     specific problem ("you returned 5, I need 6" / "node 87 was not in the
     candidate list") -- this is the "agentic loop" the challenge asks for.
  4. Fall back to the top-N rule-based candidates untouched if Gemini is
     unavailable (no API key) or all retries are exhausted, so the pipeline
     always produces a complete mapping either way.

Uses the plain REST endpoint so the only dependency is `requests` --
no extra SDK needed.
"""
import json
import os
import time
import requests

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

SYSTEM_INSTRUCTIONS = """You are a mechanical-service-to-3D mapping assistant.
You are given ONE service step (text instruction from a gearbox workshop
manual) and a shortlist of CANDIDATE 3D mesh nodes that a geometric+lexical
matcher already narrowed down from a much larger chaotic scene.

Each candidate includes: node_index, raw (messy, possibly bilingual DE/EN)
mesh name, its assigned part-type tags (may be empty), which structural side
of the assembly it sits on (drive_end / output_end / center), its bounding
box size, and the rule-based reasons it was shortlisted.

Task: choose EXACTLY the requested number of node_index values that best
correspond to the physical part(s) named in the step. Only choose from the
given candidate list -- never invent a node_index. If you are genuinely
uncertain among several visually/geometrically identical candidates (e.g.
several bolts in the same bolt-circle), prefer the ones flagged as
'near_anchor' to the most relevant structural landmark, and prefer ones
NOT flagged 'deprecated'.

Respond ONLY with strict JSON, no markdown fences, no commentary:
{"node_indices": [int, ...], "reasoning": "one or two sentences"}
"""


def _call_gemini(prompt: str, retries=4, timeout=30):
    if not GEMINI_API_KEY:
        return None
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTIONS}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"},
    }
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                GEMINI_URL, params={"key": GEMINI_API_KEY}, json=body, timeout=timeout
            )
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else 15 * (attempt + 1)
                print(f"  [gemini_agent] 429 rate-limited, waiting {wait:.0f}s "
                      f"(attempt {attempt+1}/{retries+1})...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip().strip("`")
            if text.startswith("json"):
                text = text[4:]
            return json.loads(text)
        except Exception as e:
            if attempt == retries:
                print(f"  [gemini_agent] giving up after {attempt+1} attempts: {e}")
                return None
            time.sleep(2.0 * (attempt + 1))
    print("  [gemini_agent] giving up: exhausted retries after repeated 429s")
    return None


def _candidate_payload(cand, by_idx):
    f = by_idx[cand.node_index]
    return {
        "node_index": cand.node_index,
        "raw_name": cand.raw_name,
        "tags": f.tags,
        "side": f.side,
        "dims": [round(d, 2) for d in f.dims],
        "deprecated": cand.deprecated,
        "rule_based_score": round(cand.score, 2),
        "rule_based_reasons": cand.reasons,
    }


def refine_step(step, candidates, by_idx, max_attempts=3):
    """Returns (node_indices, reasoning, source) where source is
    'gemini' or 'rule_based_fallback'."""
    expected = step.expected_count
    fallback_ids = [c.node_index for c in candidates[:expected]]

    if not GEMINI_API_KEY:
        return fallback_ids, "No GEMINI_API_KEY set -- used top rule-based candidates.", "rule_based_fallback"

    cand_payload = [_candidate_payload(c, by_idx) for c in candidates]
    base_prompt = (
        f"STEP {step.step_id}: {step.title}\n"
        f"INSTRUCTION: {step.instruction}\n"
        f"EXPECTED PART COUNT: {expected}\n\n"
        f"CANDIDATES:\n{json.dumps(cand_payload, indent=2)}\n"
    )
    valid_ids = {c.node_index for c in candidates}
    prompt = base_prompt
    last_reasoning = ""
    for attempt in range(max_attempts):
        result = _call_gemini(prompt)
        if result is None:
            break
        ids = result.get("node_indices", [])
        last_reasoning = result.get("reasoning", "")
        bad = [i for i in ids if i not in valid_ids]
        if bad:
            prompt = base_prompt + (
                f"\nYour previous answer included node_index values not in the "
                f"candidate list: {bad}. Choose only from the listed node_index values."
            )
            continue
        if len(ids) != expected:
            prompt = base_prompt + (
                f"\nYour previous answer returned {len(ids)} node_indices but "
                f"EXPECTED PART COUNT is {expected}. Return exactly {expected}."
            )
            continue
        return ids, last_reasoning, "gemini"

    return fallback_ids, (last_reasoning or "Gemini refinement failed/unavailable; used rule-based fallback."), "rule_based_fallback"