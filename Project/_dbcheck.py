import sqlite3

AYAN = r"D:\2025\personal\M.Tech\Course_May-June\Tutorial\AgenticWorkflow-Mohammad_Ayan_Khan_Data_Extraction\AgenticWorkflow-Mohammad_Ayan_Khan_Data_Extraction\data\signal_intelligence.db"
OURS = r"D:\2025\personal\M.Tech\Course_May-June\Tutorial\Project\outputs\runtime\signal_intelligence.db"

for label, p in [("AYAN", AYAN), ("OURS", OURS)]:
    print("===", label, "===")
    c = sqlite3.connect(p)
    cur = c.cursor()
    tables = [r[0] for r in cur.execute(
        "select name from sqlite_master where type='table' order by name")]
    for tbl in tables:
        try:
            n = cur.execute("select count(*) from " + tbl).fetchone()[0]
        except Exception as e:
            n = f"err {e}"
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tbl})")]
        print(f"  {tbl}: {n} rows | cols={cols}")
    c.close()
