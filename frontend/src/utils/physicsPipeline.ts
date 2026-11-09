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
    const { x: seedX, y: seedY } = target
      ? polarToXY(
          target.radius * (0.92 + (hashJitter(n.id) % 16) / 100),
          target.theta + hashJitter(n.id) * 0.04
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
          .distanceMax(420)
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
            if (k === 'immutable') return 0.98;
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
        return layoutLinkStrength(kind) * 0.35;
      });
    }
    if (collideForce && typeof collideForce.iterations === 'function') {
      collideForce.iterations(6);
    }

    const separationTicks = onlyNew && onlyNew.size > 0 ? 88 : 175;
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

/** Weak pull toward target angle (ballpark radial sectors, not a rigid ring). */
function radialAnchorForce(): (alpha: number) => void {
  let nodes: any[] = [];
  const force = (alpha: number) => {
    for (const n of nodes) {
      const t = n._radialTarget;
      if (!t) continue;
      const { x: tx, y: ty } = polarToXY(t.radius, t.theta);
      const k = (t.anchorStrength ?? 0.08) * alpha;
      n.vx += (tx - n.x) * k;
      n.vy += (ty - n.y) * k;
    }
  };
  (force as { initialize?: (n: any[]) => void }).initialize = (n: any[]) => {
    nodes = n;
  };
  return force;
}
