import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { GitBranch, ArrowDown, AlertTriangle } from 'lucide-react';
import { fetchGraph } from '../api/client';
import type { GraphResponse } from '../api/client';
import Spinner from '../components/Spinner';
import styles from './LangGraph.module.css';

const NODE_LABELS: Record<string, string> = {
  __start__: 'Start',
  __end__: 'End',
  input_guardrail: 'Input Guardrail',
  extract: 'Extraction',
  memory: 'Memory Recall',
  retrieve: 'Evidence Retrieval',
  trend: 'Trend Analysis',
  merge: 'Merge Branches',
  risk: 'Risk Assessment',
  assemble: 'Report Assembly',
  output_guardrail: 'Output Guardrail',
  end_rejected: 'Rejected',
  end_guarded: 'Guarded',
  end_ok: 'Approved',
};

function label(id: string): string {
  return NODE_LABELS[id] ?? id;
}

/** Assign each node a layer = shortest forward distance from __start__. */
function computeLayers(graph: GraphResponse): string[][] {
  const adj = new Map<string, string[]>();
  for (const n of graph.nodes) adj.set(n.id, []);
  for (const e of graph.edges) {
    if (!adj.has(e.source)) adj.set(e.source, []);
    adj.get(e.source)!.push(e.target);
  }

  const level = new Map<string, number>();
  const queue: string[] = ['__start__'];
  level.set('__start__', 0);
  while (queue.length) {
    const cur = queue.shift()!;
    const curLevel = level.get(cur)!;
    for (const next of adj.get(cur) ?? []) {
      if (!level.has(next) || level.get(next)! < curLevel + 1) {
        if (!level.has(next)) {
          level.set(next, curLevel + 1);
          queue.push(next);
        }
      }
    }
  }

  const maxLevel = Math.max(0, ...Array.from(level.values()));
  const layers: string[][] = Array.from({ length: maxLevel + 1 }, () => []);
  for (const n of graph.nodes) {
    const lvl = level.get(n.id);
    if (lvl !== undefined) layers[lvl].push(n.id);
  }
  return layers.filter((l) => l.length > 0);
}

function nodeClass(id: string): string {
  if (id === '__start__' || id === '__end__') return styles.terminal;
  if (id === 'end_ok') return styles.ok;
  if (id === 'end_rejected') return styles.bad;
  if (id === 'end_guarded') return styles.warn;
  if (id.includes('guardrail')) return styles.guard;
  return styles.node;
}

export default function LangGraph() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['graph'],
    queryFn: fetchGraph,
  });

  const layers = useMemo(() => (data ? computeLayers(data) : []), [data]);
  const conditionalEdges = useMemo(
    () => (data ? data.edges.filter((e) => e.conditional) : []),
    [data]
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>LangGraph Flow</h1>
        <p className={styles.subtitle}>
          The restored multi-agent signal workflow (langgraph_flow.py), rendered
          live from the compiled graph structure.
        </p>
      </div>

      {isLoading && (
        <div className={styles.center}>
          <Spinner size={32} />
          <p>Building graph...</p>
        </div>
      )}

      {isError && (
        <div className={styles.errorBox}>
          <AlertTriangle size={18} />
          <span>Could not load graph: {(error as Error).message}</span>
        </div>
      )}

      {data && (
        <div className={styles.content}>
          <div className={styles.diagram}>
            {layers.map((layer, i) => (
              <div key={i}>
                <div className={styles.layer}>
                  {layer.map((id) => (
                    <div key={id} className={`${styles.nodeBase} ${nodeClass(id)}`}>
                      {label(id)}
                    </div>
                  ))}
                </div>
                {i < layers.length - 1 && (
                  <div className={styles.arrow}>
                    <ArrowDown size={18} />
                  </div>
                )}
              </div>
            ))}
          </div>

          <aside className={styles.sidebar}>
            <div className={styles.legendCard}>
              <div className={styles.legendHeader}>
                <GitBranch size={16} />
                <h4>Conditional Routes</h4>
              </div>
              <ul className={styles.routeList}>
                {conditionalEdges.map((e, i) => (
                  <li key={i}>
                    <span className={styles.routeSrc}>{label(e.source)}</span>
                    <ArrowDown size={12} className={styles.routeArrow} />
                    <span className={styles.routeDst}>{label(e.target)}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className={styles.legendCard}>
              <div className={styles.legendHeader}>
                <h4>Summary</h4>
              </div>
              <div className={styles.statRow}>
                <span>Nodes</span>
                <strong>{data.nodes.length}</strong>
              </div>
              <div className={styles.statRow}>
                <span>Edges</span>
                <strong>{data.edges.length}</strong>
              </div>
              <div className={styles.statRow}>
                <span>Conditional</span>
                <strong>{conditionalEdges.length}</strong>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
