import {
  GraphNode,
  isImmutableConcept,
  isRootNode,
} from '../types';

export function isGenesisNode(node: GraphNode): boolean {
  if (node.metadata?.is_genesis === true) return true;
  const title = (node.title || '').trim().toLowerCase();
  return title === 'everything' || title === 'genesis';
}

export function isMutableConcept(node: GraphNode): boolean {
  return !isRootNode(node) && !isImmutableConcept(node);
}

export interface RadialTarget {
  radius: number;
  theta: number;
  radialStrength: number;
  anchorStrength: number;
}

function hashAngle(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) | 0;
  }
  return ((h % 1000) / 1000) * 2 * Math.PI - Math.PI;
}

function linkId(l: { source: unknown; target: unknown }): { sourceId: string; targetId: string } {
  const sourceId = typeof l.source === 'object' && l.source !== null ? (l.source as { id: string }).id : String(l.source);
  const targetId = typeof l.target === 'object' && l.target !== null ? (l.target as { id: string }).id : String(l.target);
  return { sourceId, targetId };
}

/** Mutable parent edges: child SUBSET_OF parent (source → target). */
export function buildMutableChildrenMap(
  nodes: GraphNode[],
  links: { source: unknown; target: unknown; description?: string }[]
): Map<string, string[]> {
  const childrenOf = new Map<string, string[]>();
  const addChild = (parentId: string, childId: string) => {
    if (!childrenOf.has(parentId)) childrenOf.set(parentId, []);
    const list = childrenOf.get(parentId)!;
    if (!list.includes(childId)) list.push(childId);
  };

  for (const l of links) {
    const desc = (l.description || '').toUpperCase();
    if (desc.includes('SUBSET')) {
      const { sourceId, targetId } = linkId(l);
      addChild(targetId, sourceId);
    }
  }

  for (const n of nodes) {
    if (!isMutableConcept(n)) continue;
    const parentId = n.metadata?.mutable_parent_id as string | undefined;
    if (parentId) addChild(parentId, n.id);
  }

  return childrenOf;
}

export function computeMutableDepths(
  nodes: GraphNode[],
  links: { source: unknown; target: unknown; description?: string }[]
): Map<string, number> {
  const depths = new Map<string, number>();
  const genesis = nodes.find(isGenesisNode);

  for (const n of nodes) {
    if (isGenesisNode(n) || isMutableConcept(n)) {
      const d = n.metadata?.tree_depth_from_genesis;
      if (typeof d === 'number' && Number.isFinite(d)) {
        depths.set(n.id, d);
      }
    }
  }

  if (genesis) depths.set(genesis.id, 0);

  const childrenOf = buildMutableChildrenMap(nodes, links);
  const queue: string[] = genesis ? [genesis.id] : [];

  if (!genesis) {
    for (const n of nodes) {
      if (isMutableConcept(n) && !n.metadata?.mutable_parent_id) {
        depths.set(n.id, depths.get(n.id) ?? 1);
        queue.push(n.id);
      }
    }
  }

  while (queue.length) {
    const id = queue.shift()!;
    const d = depths.get(id) ?? 0;
    for (const childId of childrenOf.get(id) || []) {
      if (!depths.has(childId)) depths.set(childId, d + 1);
      queue.push(childId);
    }
  }

  for (const n of nodes) {
    if (isMutableConcept(n) && !depths.has(n.id)) depths.set(n.id, 1);
  }

  return depths;
}

function assignSubtreeAngles(
  genesisId: string | undefined,
  childrenOf: Map<string, string[]>,
  depths: Map<string, number>
): Map<string, number> {
  const angles = new Map<string, number>();

  const visit = (id: string, a0: number, a1: number) => {
    angles.set(id, (a0 + a1) / 2);
    const kids = (childrenOf.get(id) || [])
      .filter((k) => depths.has(k))
      .sort((a, b) => a.localeCompare(b));
    if (!kids.length) return;
    const slice = (a1 - a0) / kids.length;
    kids.forEach((kid, i) => visit(kid, a0 + i * slice, a0 + (i + 1) * slice));
  };

  if (genesisId) {
    visit(genesisId, -Math.PI, Math.PI);
  }
  return angles;
}

export function computeRadialTargets(
  nodes: GraphNode[],
  links: { source: unknown; target: unknown; description?: string }[]
): Map<string, RadialTarget> {
  const n = Math.max(1, nodes.length);
  const ringR = 88 + Math.sqrt(n) * 20;
  const R_ROOT = ringR * 1.02;
  const R_IMM = ringR * 0.78;
  const R_GENESIS = 12;
  /** Mutable band stays well inside immutables / roots. */
  const R_MUT_OUTER = ringR * 0.48;

  const depths = computeMutableDepths(nodes, links);
  const maxDepth = Math.max(1, ...[...depths.values()]);
  const genesis = nodes.find(isGenesisNode);
  const childrenOf = buildMutableChildrenMap(nodes, links);
  const subtreeAngles = assignSubtreeAngles(genesis?.id, childrenOf, depths);

  const roots = nodes.filter(isRootNode).sort((a, b) => a.id.localeCompare(b.id));
  const rootAngle = new Map<string, number>();
  roots.forEach((r, i) => {
    rootAngle.set(r.id, (2 * Math.PI * i) / Math.max(1, roots.length) - Math.PI / 2);
  });

  const targets = new Map<string, RadialTarget>();

  const immAngle = new Map<string, number>();
  const immByRoot = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    if (!isImmutableConcept(node) || isRootNode(node)) continue;
    const rootId = (node.metadata?.root_node_id as string | undefined) ?? '__none__';
    if (!immByRoot.has(rootId)) immByRoot.set(rootId, []);
    immByRoot.get(rootId)!.push(node);
  }
  immByRoot.forEach((group, rootId) => {
    group.sort((a, b) => a.id.localeCompare(b.id));
    const baseTheta =
      rootId === '__none__'
        ? hashAngle(group[0]?.id ?? 'imm')
        : rootAngle.get(rootId) ?? hashAngle(rootId);
    const arc = Math.min(1.55, 0.2 * group.length + 0.28);
    const mid = (group.length - 1) / 2;
    group.forEach((node, i) => {
      const t = group.length === 1 ? 0.5 : i / (group.length - 1);
      immAngle.set(node.id, baseTheta - arc / 2 + t * arc);
      (node as GraphNode & { _immRadialOffset?: number })._immRadialOffset =
        (i - mid) * 16;
    });
  });

  for (const node of nodes) {
    if (isGenesisNode(node)) {
      targets.set(node.id, {
        radius: R_GENESIS,
        theta: 0,
        radialStrength: 0.88,
        anchorStrength: 0.12,
      });
      continue;
    }

    if (isRootNode(node)) {
      const theta = rootAngle.get(node.id) ?? hashAngle(node.id);
      targets.set(node.id, {
        radius: R_ROOT,
        theta,
        radialStrength: 0.72,
        anchorStrength: 0.1,
      });
      continue;
    }

    if (isImmutableConcept(node)) {
      const theta =
        immAngle.get(node.id) ??
        hashAngle(node.id) + (hashAngle(node.id + ':imm') - Math.PI) * 0.08;
      const radialOffset = (node as GraphNode & { _immRadialOffset?: number })._immRadialOffset ?? 0;
      targets.set(node.id, {
        radius: R_IMM + radialOffset,
        theta,
        radialStrength: 0.44,
        anchorStrength: 0.05,
      });
      continue;
    }

    const depth = Math.max(1, depths.get(node.id) ?? 1);
    const theta = subtreeAngles.get(node.id) ?? hashAngle(node.id);
    const innerSpan = Math.max(24, R_MUT_OUTER - R_GENESIS - 10);
    const step = innerSpan / Math.max(1, maxDepth);
    const radius = R_GENESIS + 6 + depth * step * 0.92;

    targets.set(node.id, {
      radius: Math.min(radius, R_MUT_OUTER),
      theta,
      radialStrength: 0.38 + Math.min(depth, 4) * 0.04,
      anchorStrength: 0.06,
    });
  }

  return targets;
}

export function polarToXY(radius: number, theta: number): { x: number; y: number } {
  return { x: radius * Math.cos(theta), y: radius * Math.sin(theta) };
}

/** Detect layouts where almost all nodes sit on one annulus (the old ring seed). */
export function isDiscLikeLayout(
  positions: Iterable<{ x: number; y: number }>
): boolean {
  const radii: number[] = [];
  for (const p of positions) {
    radii.push(Math.hypot(p.x, p.y));
  }
  if (radii.length < 8) return false;
  const mean = radii.reduce((a, b) => a + b, 0) / radii.length;
  if (mean < 70) return false;
  const variance = radii.reduce((a, r) => a + (r - mean) ** 2, 0) / radii.length;
  const cv = Math.sqrt(variance) / Math.max(mean, 1);
  return cv < 0.17;
}
