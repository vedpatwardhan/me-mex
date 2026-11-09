import {
  GraphNode,
  isImmutableConcept,
  isRootNode,
} from '../types';
import { isGenesisNode } from './radialLayout';
import { collideRadiusForGraph } from './graphNodeMetrics';

/** Render-only layout tiers; backend edges stay unweighted. */
export type LayoutLinkKind =
  | 'root_evidence'
  | 'evidence_hub'
  | 'mutable_tree'
  | 'other';

export interface ForceParams {
  chargeRootImmutable: number;
  chargeMutable: number;
  linkDistanceDefault: number;
  collideRadius: number;
  centerStrength: number;
  velocityDecay: number;
  nRef: number;
}

const N_REF = 40;

export function getForceParams(nodeCount: number): ForceParams {
  const n = Math.max(1, nodeCount);
  // Gentler than sqrt: large graphs still need readable separation
  const scale = Math.pow(N_REF / n, 0.28);
  const chargeScale = Math.max(0.82, Math.min(1.08, scale));
  const denseBoost = n >= 55 ? 1.12 : 1;

  return {
    // Roots/immutables on the outer band need stronger local repulsion; genesis stays soft (see chargeStrengthForNode).
    chargeRootImmutable: -620 * chargeScale * denseBoost,
    chargeMutable: -320 * chargeScale * denseBoost,
    linkDistanceDefault: n > 60 ? 115 : 125,
    collideRadius: collideRadiusForGraph(n),
    centerStrength: n > 50 ? 0.006 : 0.012,
    velocityDecay: 0.52,
    nRef: N_REF,
  };
}

function nodeById(nodes: any[], id: string): any | undefined {
  return nodes.find((n) => n.id === id);
}

export function classifyLayoutLink(
  source: any,
  target: any
): LayoutLinkKind {
  const sRoot = isRootNode(source);
  const tRoot = isRootNode(target);
  const sImm = isImmutableConcept(source);
  const tImm = isImmutableConcept(target);
  const sMut = !sRoot && !sImm;
  const tMut = !tRoot && !tImm;

  if ((sRoot && tImm) || (tRoot && sImm)) {
    return 'root_evidence';
  }
  if ((sImm && tMut) || (tImm && sMut)) {
    return 'evidence_hub';
  }
  if (sMut && tMut) {
    return 'mutable_tree';
  }
  return 'other';
}

export function layoutLinkDistance(kind: LayoutLinkKind, params: ForceParams): number {
  switch (kind) {
    case 'root_evidence':
      return 72;
    case 'evidence_hub':
      return 175;
    case 'mutable_tree':
      return 110;
    default:
      return params.linkDistanceDefault;
  }
}

export function layoutLinkStrength(kind: LayoutLinkKind): number {
  switch (kind) {
    case 'root_evidence':
      return 0.55;
    case 'evidence_hub':
      return 0.22;
    case 'mutable_tree':
      return 0.38;
    default:
      return 0.4;
  }
}

export function chargeStrengthForNode(d: any, params: ForceParams): number {
  if (isGenesisNode(d)) {
    return params.chargeMutable * 0.25;
  }
  const root = isRootNode(d);
  const imm = isImmutableConcept(d);
  if (root) {
    return params.chargeRootImmutable;
  }
  if (imm) {
    return params.chargeRootImmutable * 1.02;
  }
  const depth = typeof d._layoutDepth === 'number' ? d._layoutDepth : 0;
  // Deeper mutables: slightly stronger repulsion so rings don't collapse inward.
  return params.chargeMutable * (0.78 + Math.min(depth, 6) * 0.05);
}

/** Phantom ROOT↔immutable links for layout only (not persisted). */
export function appendPhantomRootEvidenceLinks(
  nodes: any[],
  links: any[]
): any[] {
  const out = [...links];
  const hasLink = new Set<string>();
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source;
    const t = typeof l.target === 'object' ? l.target.id : l.target;
    hasLink.add(`${s}|${t}`);
    hasLink.add(`${t}|${s}`);
  }

  for (const n of nodes) {
    if (!isImmutableConcept(n)) continue;
    const rootId = n.metadata?.root_node_id as string | undefined;
    if (!rootId) continue;
    const rootNode = nodeById(nodes, rootId);
    if (!rootNode || !isRootNode(rootNode)) continue;
    const key = `${rootId}|${n.id}`;
    if (hasLink.has(key)) continue;
    out.push({
      id: `phantom_${rootId}_${n.id}`,
      source: rootId,
      target: n.id,
      _phantom: true,
    });
  }
  return out;
}

export function resolveLinkEndpoints(links: any[], nodes: any[]): any[] {
  const map = new Map(nodes.map((n) => [n.id, n]));
  return links.map((l) => {
    const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
    const targetId = typeof l.target === 'object' ? l.target.id : l.target;
    return {
      ...l,
      source: map.get(sourceId) ?? sourceId,
      target: map.get(targetId) ?? targetId,
    };
  });
}

export function computeGraphStructureKey(
  nodes: { id: string }[],
  edges: { id?: string; source: string; target: string }[]
): string {
  const nIds = nodes.map((n) => n.id).sort().join(',');
  const eIds = edges
    .map((e) => e.id ?? `${e.source}-${e.target}`)
    .sort()
    .join(',');
  return `layout-v4|${nodes.length}|${edges.length}|${nIds}|${eIds}`;
}

export type GraphNodeLike = GraphNode;
