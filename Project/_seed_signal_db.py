import shutil
import sqlite3
from pathlib import Path

AYAN_DATA = Path(
    r"D:\2025\personal\M.Tech\Course_May-June\Tutorial"
    r"\AgenticWorkflow-Mohammad_Ayan_Khan_Data_Extraction"
    r"\AgenticWorkflow-Mohammad_Ayan_Khan_Data_Extraction\data"
)

from src.config import RUNTIME_DIR

ml_db = RUNTIME_DIR / "signal_intelligence_ml.db"
emb_dir = RUNTIME_DIR / "signal_intelligence"
emb_dir.mkdir(parents=True, exist_ok=True)

# 1) Consistent snapshot of the populated DB (merges WAL/SHM) -> our ML db.
src = sqlite3.connect(str(AYAN_DATA / "signal_intelligence.db"))
dst = sqlite3.connect(str(ml_db))
with dst:
    src.backup(dst)
src.close()
dst.close()
print(f"DB seeded -> {ml_db}")

# 2) Copy precomputed embedding + UMAP caches.
shutil.copy2(AYAN_DATA / "embeddings.npz", emb_dir / "embeddings.npz")
shutil.copy2(AYAN_DATA / "umap_projection.npy", emb_dir / "umap_projection.npy")
print(f"Caches copied -> {emb_dir}")

# 3) Verify.
c = sqlite3.connect(str(ml_db))
for tbl in ("events", "event_problems", "clusters", "recalls"):
    try:
        n = c.execute("select count(*) from " + tbl).fetchone()[0]
        print(f"  {tbl}: {n} rows")
    except sqlite3.Error as e:
        print(f"  {tbl}: (missing) {e}")
c.close()

import numpy as np
data = np.load(str(emb_dir / "embeddings.npz"))
print(f"  embeddings shape: {data['embeddings'].shape}, reports: {len(data['report_numbers'])}")
