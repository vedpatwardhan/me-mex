/** Shared pixel radii for draw + physics (world space, not zoomed). */

export const NODE_RADIUS_DEFAULT = 3.5;
export const NODE_RADIUS_HOVER = 4.25;
export const NODE_RADIUS_SELECTED = 4.75;
export const NODE_POINTER_RADIUS = 7;
/** Min center-to-center gap between node circles (in addition to both radii). */
export const NODE_COLLIDE_GAP = 9;
export const ROOT_ORBIT_EXTRA = 1.5;

export function nodeCollideRadius(kind: 'root' | 'immutable' | 'mutable' = 'mutable'): number {
  const base =
    kind === 'root'
      ? NODE_RADIUS_DEFAULT + ROOT_ORBIT_EXTRA
      : NODE_RADIUS_DEFAULT;
  const gap =
    kind === 'immutable' ? NODE_COLLIDE_GAP + 6 : kind === 'root' ? NODE_COLLIDE_GAP + 2 : NODE_COLLIDE_GAP;
  return base + gap;
}

export function collideRadiusForGraph(nodeCount: number): number {
  const base = nodeCollideRadius('mutable');
  if (nodeCount >= 65) return base + 4;
  if (nodeCount >= 45) return base + 2;
  return base;
}
