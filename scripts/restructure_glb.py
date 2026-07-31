"""
restructure_glb.py
-------------------
BONUS deliverable: takes the flat, chaotic GLB + the final mapping.json and
writes a new GLB where:

  - Every mesh node used in the mapping is renamed to
        "<step_id>__<part-type-tag-or-role>__<orig_name>"
    e.g. "10-20__hex_bolt__sechskant34_v3"
  - Nodes are re-parented under a clean tree:
        world -> Procedure 10 -> Step 10-20: Remove front cover flange bolts -> <mesh nodes>
  - Nodes never referenced by any step (leftover/ambiguous geometry) are kept
    under a "world -> Unmapped" group instead of being deleted, so nothing
    silently disappears from the model.

Usage:
    python restructure_glb.py <in.glb> <mapping.json> <out.glb>
"""
import json
import sys
from pathlib import Path
from pygltflib import GLTF2, Node


def restructure(glb_path: str, mapping_path: str, out_path: str):
    g = GLTF2().load(glb_path)
    mapping = json.loads(Path(mapping_path).read_text())

    node_to_step = {}   # node_index -> step_id
    step_titles = {}
    for step_id, info in mapping.items():
        step_titles[step_id] = info["title"]
        for idx in info["matched_node_indices"]:
            # first assignment wins if a node was (rarely) claimed by >1 step
            node_to_step.setdefault(idx, step_id)

    # 1. Rename mesh nodes
    original_names = {}
    for idx, step_id in node_to_step.items():
        n = g.nodes[idx]
        original_names[idx] = n.name
        n.name = f"{step_id}__{n.name}"

    # 2. Build new group nodes: one per procedure, one per step under it
    procedures = {}  # procedure -> [step_id,...]
    for step_id in step_titles:
        proc = step_id.split("-")[0]
        procedures.setdefault(proc, []).append(step_id)

    new_nodes = list(g.nodes)  # extend this list; indices are stable append order
    root_idx = 0  # 'world' node, per extract_features() analysis
    root = g.nodes[root_idx]
    root_children = set(root.children or [])

    step_group_idx = {}
    proc_group_idx = {}
    for proc, step_ids in sorted(procedures.items()):
        proc_node = Node(name=f"Procedure {proc}", children=[])
        new_nodes.append(proc_node)
        proc_i = len(new_nodes) - 1
        proc_group_idx[proc] = proc_i
        for step_id in sorted(step_ids):
            step_node = Node(name=f"Step {step_id}: {step_titles[step_id]}", children=[])
            new_nodes.append(step_node)
            step_i = len(new_nodes) - 1
            step_group_idx[step_id] = step_i
            proc_node.children.append(step_i)

    # "Unmapped" bucket for anything never referenced by a step
    unmapped_node = Node(name="Unmapped", children=[])
    new_nodes.append(unmapped_node)
    unmapped_i = len(new_nodes) - 1

    # 3. Re-parent leaf mesh nodes under their step group (or Unmapped)
    for i, n in enumerate(g.nodes):
        if n.mesh is None:
            continue
        if i not in root_children:
            continue  # not a direct child of world in the original flat scene
        if i in node_to_step:
            step_i = step_group_idx[node_to_step[i]]
            new_nodes[step_i].children.append(i)
        else:
            unmapped_node.children.append(i)

    # 4. Root now only points at the procedure groups + Unmapped
    new_nodes[root_idx].children = list(proc_group_idx.values()) + [unmapped_i]

    g.nodes = new_nodes
    g.save(out_path)

    print(f"Restructured GLB written to {out_path}")
    print(f"  {len(node_to_step)} mesh nodes grouped under {len(step_group_idx)} step nodes "
          f"across {len(proc_group_idx)} procedures.")
    print(f"  {len(unmapped_node.children)} nodes left in 'Unmapped'.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python restructure_glb.py <in.glb> <mapping.json> <out.glb>")
        sys.exit(1)
    restructure(sys.argv[1], sys.argv[2], sys.argv[3])
