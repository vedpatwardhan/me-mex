import {
  appendPhantomRootEvidenceLinks,
  chargeStrengthForNode,
  classifyLayoutLink,
  getForceParams,
  layoutLinkDistance,
  layoutLinkStrength,
  resolveLinkEndpoints,
} from './forceLayoutConfig';
import {
  computeMutableDepths,
  computeRadialTargets,
  polarToXY,
} from './radialLayout';
import { isImmutableConcept, isRootNode } from '../types';
import { nodeCollideRadius } from './graphNodeMetrics';
function collideKind(d: any): 'root' | 'immutable' | 'mutable' {
  if (isRootNode(d)) return 'root';
  if (isImmutableConcept(d) && !isRootNode(d)) return 'immutable';
  return 'mutable';
}

export const prewarmForceSimulation = (
  nodes: any[],
  links: any[],
  ticks: number = 180,
  existingPositions?: Map<string, { x: number; y: number; fx?: number; fy?: number }>,
  options?: { onlyLayoutNewNodeIds?: Set<string> }
): { nodes: any[]; links: any[] } => {
  if (!nodes.length) return { nodes, links };

  const radialTargets = computeRadialTargets(nodes, links);
  const mutableDepths = computeMutableDepths(nodes, links);

  const nodesCopy = nodes.map((n) => {
    const existing = existingPositions?.get(n.id);
    const target = radialTargets.get(n.id);
    const isImm = isImmutableConcept(n) && !isRootNode(n);
    const { x: seedX, y: seedY } = target
      ? polarToXY(
          isImm
            ? target.radius
            : target.radius * (0.92 + (hashJitter(n.id) % 16) / 100),
          target.theta + (isImm ? 0 : hashJitter(n.id) * 0.04)
        )
      : { x: (hashJitter(n.id) - 0.5) * 40, y: (hashJitter(n.id + 'y') - 0.5) * 40 };

    if (existing) {
      return {
        ...n,
        x: existing.x,
        y: existing.y,
        _layoutDepth: mutableDepths.get(n.id) ?? 0,
        _radialTarget: target,
      };
    }
    return {
      ...n,
      x: seedX,
      y: seedY,
      _layoutDepth: mutableDepths.get(n.id) ?? 0,
      _radialTarget: target,
    };
  });

  const onlyNew = options?.onlyLayoutNewNodeIds;
  const layoutLinksRaw = appendPhantomRootEvidenceLinks(nodesCopy, links);
  const linksCopy = resolveLinkEndpoints(layoutLinksRaw, nodesCopy);

  const d3 = (globalThis as any).d3;
  if (!d3 || !d3.forceSimulation) {
    nodesCopy.forEach((n) => {
      if (n.x !== undefined && n.y !== undefined) {
        n.fx = n.x;
        n.fy = n.y;
      }
    });
    return { nodes: nodesCopy, links: linksCopy };
  }

  const params = getForceParams(nodesCopy.length);
  const tickCount = onlyNew && onlyNew.size > 0 ? Math.min(ticks, 60) : ticks;

  try {
    const simulation = d3
      .forceSimulation(nodesCopy)
      .force(
        'charge',
        d3
          .forceManyBody()
          .strength((d: any) => chargeStrengthForNode(d, params))
          .theta(0.82)
          .distanceMax(440)
      )
      .force(
        'link',
        d3
          .forceLink(linksCopy)
          .id((d: any) => d.id)
          .distance((l: any) => {
            const kind = classifyLayoutLink(l.source, l.target);
            return layoutLinkDistance(kind, params);
          })
          .strength((l: any) => {
            const kind = classifyLayoutLink(l.source, l.target);
            return layoutLinkStrength(kind);
          })
      )
      .force(
        'collide',
        d3
          .forceCollide()
          .radius((d: any) => nodeCollideRadius(collideKind(d)))
          .strength((d: any) => {
            const k = collideKind(d);
            if (k === 'immutable') return 0.9;
            if (k === 'mutable') return 0.95;
            return 0.9;
          })
          .iterations(4)
      )
      .force(
        'radial',
        d3
          .forceRadial(
            (d: any) => d._radialTarget?.radius ?? 120,
            0,
            0
          )
          .strength((d: any) => d._radialTarget?.radialStrength ?? 0.35)
      )
      .force('radialAnchor', radialAnchorForce())
      .force('immutableArcSpread', immutableArcSpreadForce())
      .force('center', d3.forceCenter(0, 0).strength(params.centerStrength))
      .velocityDecay(params.velocityDecay);

    simulation.stop();
    for (let i = 0; i < tickCount; ++i) {
      simulation.tick();
    }

    const radialForce = simulation.force('radial');
    const linkForce = simulation.force('link');
    const collideForce = simulation.force('collide');

    if (radialForce && typeof radialForce.strength === 'function') {
      radialForce.strength((d: any) => (d._radialTarget?.radialStrength ?? 0.35) * 0.25);
    }
    if (linkForce && typeof linkForce.strength === 'function') {
      linkForce.strength((l: any) => {
        const kind = classifyLayoutLink(l.source, l.target);
        const base = layoutLinkStrength(kind);
        if (kind === 'evidence_hub') return base * 0.18;
        return base * 0.35;
      });
    }
    if (collideForce && typeof collideForce.iterations === 'function') {
      collideForce.iterations(6);
    }

    const separationTicks = onlyNew && onlyNew.size > 0 ? 88 : 190;
    for (let i = 0; i < separationTicks; ++i) {
      simulation.tick();
    }

    nodesCopy.forEach((n) => {
      const pinned = existingPositions?.get(n.id);
      const isNew = onlyNew?.has(n.id);
      const incrementalPin = pinned && !isNew && onlyNew && onlyNew.size > 0;
      if (incrementalPin) {
        n.x = pinned.x;
        n.y = pinned.y;
        n.fx = pinned.fx ?? pinned.x;
        n.fy = pinned.fy ?? pinned.y;
      } else {
        n.fx = n.x;
        n.fy = n.y;
      }
    });
  } catch (e) {
    console.warn('Pre-warming simulation skipped:', e);
  }

  return { nodes: nodesCopy, links: linksCopy.filter((l) => !l._phantom) };
};

function hashJitter(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 33 + id.charCodeAt(i)) | 0;
  }
  return (h & 0xffff) / 0xffff;
}

/**
 * Within each paper’s sector, push immutable concepts apart along the arc
 * (tangentially), not inward toward yellow hubs.
 */
function immutableArcSpreadForce(): (alpha: number) => void {
  let nodes: any[] = [];
  const force = (alpha: number) => {
    const groups = new Map<string, any[]>();
    for (const n of nodes) {
      if (!isImmutableConcept(n) || isRootNode(n)) continue;
      const rootId = (n.metadata?.root_node_id as string | undefined) ?? '__none__';
      if (!groups.has(rootId)) groups.set(rootId, []);
      groups.get(rootId)!.push(n);
    }

    for (const group of groups.values()) {
      if (group.length < 2) continue;
      const minAngleSep = Math.max(0.1, Math.min(0.28, 0.52 / Math.sqrt(group.length)));

      for (let i = 0; i < group.length; i++) {
        for (let j = i + 1; j < group.length; j++) {
          const a = group[i];
          const b = group[j];
          const ra = Math.hypot(a.x, a.y);
          const rb = Math.hypot(b.x, b.y);
          if (ra < 8 || rb < 8) continue;
          const ta = Math.atan2(a.y, a.x);
          const tb = Math.atan2(b.y, b.x);
          let dAngle = tb - ta;
          while (dAngle > Math.PI) dAngle -= 2 * Math.PI;
          while (dAngle < -Math.PI) dAngle += 2 * Math.PI;

          const radialSep = Math.abs(ra - rb);
          const tangentialClose = Math.abs(dAngle) < minAngleSep;
          const radialStack =
            Math.abs(dAngle) < 0.09 && radialSep > 10 && radialSep < 120;

          if (!tangentialClose && !radialStack) continue;

          const rMean = (ra + rb) / 2;
          let push = tangentialClose
            ? (minAngleSep - Math.abs(dAngle)) * rMean * 0.22
            : radialStack
              ? radialSep * 0.14
              : 0;
          push *= alpha;
          if (push <= 0) continue;

          const sign = dAngle >= 0 ? 1 : -1;
          const ax = -Math.sin(ta);
          const ay = Math.cos(ta);
          a.vx -= ax * push * sign;
          a.vy -= ay * push * sign;
          b.vx += ax * push * sign;
          b.vy += ay * push * sign;

          if (radialStack) {
            const rTarget = rMean;
            const kr = 0.06 * alpha;
            const pullA = (rTarget - ra) * kr;
            const pullB = (rTarget - rb) * kr;
            a.vx += (a.x / ra) * pullA;
            a.vy += (a.y / ra) * pullA;
            b.vx += (b.x / rb) * pullB;
            b.vy += (b.y / rb) * pullB;
          }
        }
      }
    }
  };
  (force as { initialize?: (n: any[]) => void }).initialize = (n: any[]) => {
    nodes = n;
  };
  return force;
}

/** Weak pull toward target angle (ballpark radial sectors, not a rigid ring). */
function radialAnchorForce(): (alpha: number) => void {
  let nodes: any[] = [];
  const force = (alpha: number) => {
    for (const n of nodes) {
      const t = n._radialTarget;
      if (!t) continue;
      const { x: tx, y: ty } = polarToXY(t.radius, t.theta);
      let k = (t.anchorStrength ?? 0.08) * alpha;
      if (isImmutableConcept(n) && !isRootNode(n)) {
        k *= 1.25;
      }
      n.vx += (tx - n.x) * k;
      n.vy += (ty - n.y) * k;
    }
  };
  (force as { initialize?: (n: any[]) => void }).initialize = (n: any[]) => {
    nodes = n;
  };
  return force;
}
