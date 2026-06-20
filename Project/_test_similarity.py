from src.pipeline.signal_intelligence_embeddings import EmbeddingGenerator
from src.pipeline.signal_intelligence_trend import TrendAnalyzer
from src.pipeline.signal_intelligence_db import get_connection

emb, reports = EmbeddingGenerator.load_embeddings()
print("loaded embeddings:", emb.shape, "reports:", len(reports))

ta = TrendAnalyzer()
ta.fit_clusters(emb, reports)
print("clusters fit; labels:", None if ta.labels is None else len(set(ta.labels.tolist())))

gen = EmbeddingGenerator()
q = gen.embed_single("MRI image reconstruction software produced artifacts in clinical scan")
print("query embedding dim:", q.shape)

conn = get_connection()
sim = ta.assign_complaint(embedding=q, conn=conn, top_k=10)
d = sim.model_dump()
print("cluster_id:", d.get("cluster_id"), "cluster_size:", d.get("cluster_size"),
      "growth_rate_30d:", d.get("growth_rate_30d"), "n_similar:", len(d.get("similar_events", [])))
conn.close()
