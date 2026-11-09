/** Extra padding around nodes when fitting (matches ~drawn node size). */
const NODE_PAD = 14;
const VIEW_PADDING = 56;
const MIN_SPAN = 48;
const MIN_ZOOM = 0.08;
const MAX_ZOOM = 6;
/** Max zoom when auto-fitting sparse graphs so on-screen node size stays near dense-graph scale. */
const MAX_SPARSE_FIT_ZOOM = 1.15;

/** Default camera zoom for the initial “Everything” view (force-graph’s library default). */
export const DEFAULT_BASELINE_ZOOM = 1;

export type PinnedView = { zoom: number; cx: number; cy: number };

export function baselineViewFromNodes(
  nodes: GraphPoint[],
  zoom = DEFAULT_BASELINE_ZOOM
): PinnedView | null {
  const b = graphBounds(nodes);
  if (!b) return null;
  return { zoom, cx: b.cx, cy: b.cy };
}

export function applyPinnedView(
  fg: ForceGraphRef | null,
  view: PinnedView,
  durationMs = 0
): void {
  if (!fg) return;
  fg.centerAt?.(view.cx, view.cy, durationMs);
  fg.zoom(view.zoom, durationMs);
}

export type GraphPoint = { x?: number; y?: number };

export type GraphBoundsOptions = {
  /** Minimum width/height of the fit box (world units); inflates tiny / single-node layouts. */
  minSpan?: number;
};

export function graphBounds(nodes: GraphPoint[], options?: GraphBoundsOptions) {
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

  const minSpan = options?.minSpan ?? MIN_SPAN;
  let w = Math.max(maxX - minX, minSpan);
  let h = Math.max(maxY - minY, minSpan);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;

  if (w < minSpan) {
    w = minSpan;
  }
  if (h < minSpan) {
    h = minSpan;
  }

  return { minX, minY, maxX, maxY, w, h, cx, cy };
}

function minSpanForSparseFit(
  nodeCount: number,
  canvasW: number,
  canvasH: number,
  naturalExtent: number
): number | undefined {
  if (!canvasW || !canvasH) return undefined;
  const viewportMin = Math.min(canvasW, canvasH) - VIEW_PADDING * 2;
  if (nodeCount <= 1) {
    return viewportMin / MAX_SPARSE_FIT_ZOOM;
  }
  if (nodeCount <= 3 && naturalExtent < viewportMin * 0.35) {
    return viewportMin / 1.25;
  }
  return undefined;
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
export type ForceGraphRef = {
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

  const canvasW = fg.width?.() ?? 0;
  const canvasH = fg.height?.() ?? 0;

  if (!canvasW || !canvasH) {
    const fallback = graphBounds(nodes);
    if (!fallback) {
      fg.centerAt?.(0, 0, duration);
      return;
    }
    // Avoid force-graph zoomToFit on tiny graphs (same overshoot as its internal ZOOM2NODES rule).
    if (nodes.length <= 3) {
      fg.centerAt?.(fallback.cx, fallback.cy, duration);
      const z = Math.min(MAX_SPARSE_FIT_ZOOM, fg.zoom());
      fg.zoom(z, duration);
      return;
    }
    fg.zoomToFit?.(duration, VIEW_PADDING);
    return;
  }

  const natural = graphBounds(nodes);
  if (!natural) {
    fg.centerAt?.(0, 0, duration);
    return;
  }

  const sparseMinSpan = minSpanForSparseFit(
    nodes.length,
    canvasW,
    canvasH,
    Math.max(natural.w, natural.h)
  );
  const bounds =
    sparseMinSpan !== undefined
      ? graphBounds(nodes, { minSpan: sparseMinSpan })
      : natural;

  let fitZoom = computeFitZoom(bounds, canvasW, canvasH);
  if (nodes.length <= 3) {
    fitZoom = Math.min(fitZoom, MAX_SPARSE_FIT_ZOOM);
  }
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
