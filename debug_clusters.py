"""Debug script to investigate cluster assignment."""
import numpy as np
from collections import Counter
from src.embeddings.generator import EmbeddingGenerator
from src.trend.analyzer import TrendAnalyzer
from src.pipeline.database import get_connection

embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
ta = TrendAnalyzer()
ta.fit_clusters(embeddings, report_numbers)

conn = get_connection()
labels = ta.label_clusters(conn)

# Test different complaint types - show KNN details
gen = EmbeddingGenerator()
from sklearn.metrics.pairwise import cosine_similarity

texts = [
    "MRI scanner ghosting artifacts on T2 sequences",
    "CT scanner shut down during cardiac angiography",
    "Software crash with error code blue screen",
]
for t in texts:
    emb = gen.embed_single(t)
    sims = cosine_similarity(emb.reshape(1, -1), embeddings)[0]
    top_indices = np.argsort(sims)[::-1][:20]
    print(f'\n"{t}"')
    print("  Top-20 neighbors (label, sim):")
    neighbor_labels = []
    for idx in top_indices:
        lbl = ta.labels[idx]
        s = sims[idx]
        lbl_name = labels.get(lbl, "NOISE") if lbl != -1 else "NOISE"
        print(f"    label={lbl:>3} ({lbl_name[:30]:30s}) sim={s:.4f}")
        neighbor_labels.append(lbl)
    
    # Count non-noise labels
    non_noise = [l for l in neighbor_labels if l != -1]
    print(f"  Non-noise among top-20: {len(non_noise)}/{len(neighbor_labels)}")
    if non_noise:
        print(f"  Label counts: {Counter(non_noise).most_common(5)}")

conn.close()
