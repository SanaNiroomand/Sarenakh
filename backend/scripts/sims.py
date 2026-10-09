"""Debug: prefilter similarity distribution for a run vs ground truth (to tune SIM_THRESHOLD).

    cd backend && python -m scripts.sims <run_id>
"""

import sys

from sqlalchemy import select

from app.db import Analysis, Product, Run, session
from app.samples import ground_truth

run_id = int(sys.argv[1])
with session() as db:
    run = db.get(Run, run_id)
    key = db.get(Product, run.product_id).sample_key
    rows = list(db.scalars(select(Analysis).where(Analysis.run_id == run_id)))
gt = ground_truth()["products"][key]
lead_ids = {e["msg_id"]: e["label"] for e in gt["leads"]}
decoy_ids = {e["msg_id"]: e["label"] for e in gt["decoys"]}
sims = sorted(((a.prefilter_sim or 0, a.msg_id) for a in rows), reverse=True)
print("kept", len(sims))
for rank, (s, mid) in enumerate(sims):
    tag = lead_ids.get(mid) or decoy_ids.get(mid)
    if tag:
        print(f"rank {rank:>3}  sim={s:.3f}  #{mid} {tag}")
for t in (0.30, 0.33, 0.35, 0.37, 0.40, 0.42, 0.45):
    kept = [m for s, m in sims if s >= t]
    print(f"thr {t:.2f}: keep {len(kept):>3}, leads kept {sum(1 for m in kept if m in lead_ids)}/{len(lead_ids)}")
