/** Extra padding around nodes when fitting (matches ~drawn node size). */
const NODE_PAD = 14;
const VIEW_PADDING = 56;
const MIN_SPAN = 48;
const MIN_ZOOM = 0.08;
const MAX_ZOOM = 6;

export type GraphPoint = { x?: number; y?: number };

export function graphBounds(nodes: GraphPoint[]) {
  const pts = nodes.filter((n) => Number.isFinite(n.x) && Number.isFinite(n.y));
  if (!pts.length) return null;

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const n of pts) {
    const x = n.x as number;
    const y = n.y as number;
    minX = Math.min(minX, x - NODE_PAD);
    maxX = Math.max(maxX, x + NODE_PAD);
    minY = Math.min(minY, y - NODE_PAD);
    maxY = Math.max(maxY, y + NODE_PAD);
  }

  let w = Math.max(maxX - minX, MIN_SPAN);
  let h = Math.max(maxY - minY, MIN_SPAN);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;

  if (w < MIN_SPAN) {
    w = MIN_SPAN;
  }
  if (h < MIN_SPAN) {
    h = MIN_SPAN;
  }

  return { minX, minY, maxX, maxY, w, h, cx, cy };
}

export function computeFitZoom(
  bounds: { w: number; h: number },
  canvasW: number,
  canvasH: number,
  padding = VIEW_PADDING
): number {
  if (canvasW <= 0 || canvasH <= 0) return 1;
  const k = Math.min(
    (canvasW - padding * 2) / bounds.w,
    (canvasH - padding * 2) / bounds.h
  );
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, k));
}

/**
 * Center on the graph. By default does not zoom IN (avoids feeling like the zoom-in button).
 * Pass allowZoomIn to use true fit-to-canvas behavior.
 */
type ForceGraphRef = {
  zoom: {
    (): number;
    (k: number, ms?: number): unknown;
  };
  centerAt?: (x: number, y: number, ms?: number) => void;
  width?: () => number;
  height?: () => number;
  zoomToFit?: (ms?: number, padding?: number) => void;
};

export function fitGraphView(
  fg: ForceGraphRef | null,
  nodes: GraphPoint[],
  options?: { durationMs?: number; allowZoomIn?: boolean }
): void {
  if (!fg) return;
  const duration = options?.durationMs ?? 350;
  const allowZoomIn = options?.allowZoomIn ?? false;

  const bounds = graphBounds(nodes);
  if (!bounds) {
    fg.centerAt?.(0, 0, duration);
    return;
  }

  const canvasW = fg.width?.() ?? 0;
  const canvasH = fg.height?.() ?? 0;

  if (!canvasW || !canvasH) {
    fg.zoomToFit?.(duration, VIEW_PADDING);
    return;
  }

  const fitZoom = computeFitZoom(bounds, canvasW, canvasH);
  const currentZoom = fg.zoom();
  let targetZoom = fitZoom;
  if (!allowZoomIn) {
    targetZoom = Math.min(currentZoom, fitZoom);
  }

  fg.centerAt?.(bounds.cx, bounds.cy, duration);
  if (Math.abs(targetZoom - currentZoom) > 0.02) {
    fg.zoom(targetZoom, duration);
  }
}
