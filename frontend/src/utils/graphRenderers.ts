import { GraphNode, isRootNode, getRootSubType, isImmutableConcept } from '../types';

export const createGlowTextureCache = (): Map<string, HTMLCanvasElement> => {
  const cache = new Map<string, HTMLCanvasElement>();
  // Sky Blue (Paper), Emerald (Blog), Purple (Post), Cyan (Immutable Concept), Amber (Mutable Concept), Slate (Generic Root)
  const colors = ['#38bdf8', '#34d399', '#c084fc', '#0ea5e9', '#fbbf24', '#94a3b8'];

  colors.forEach((color) => {
    const size = 64;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d')!;

    const grad = ctx.createRadialGradient(size / 2, size / 2, 2, size / 2, size / 2, size / 2);
    grad.addColorStop(0, color);
    grad.addColorStop(0.35, color.concat('55'));
    grad.addColorStop(1, 'rgba(0,0,0,0)');

    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
    cache.set(color, canvas);
  });

  return cache;
};

export const drawMeMexNode = (
  node: any,
  ctx: CanvasRenderingContext2D,
  globalScale: number,
  glowCache: Map<string, HTMLCanvasElement>,
  isSelected: boolean,
  isHovered: boolean,
  isTraversed: boolean
) => {
  const x = node.x || 0;
  const y = node.y || 0;
  const isRoot = isRootNode(node);
  const rootType = isRoot ? getRootSubType(node) : null;
  const isImmutable = isImmutableConcept(node);
  const radius = isRoot ? 12 : isSelected ? 10 : isHovered ? 8.5 : 6.5;

  let baseColor = '#fbbf24'; // Mutable Concept (Amber)
  if (isRoot) {
    if (rootType === 'paper') baseColor = '#38bdf8'; // Sky Blue
    else if (rootType === 'blog') baseColor = '#34d399'; // Emerald
    else if (rootType === 'post') baseColor = '#c084fc'; // Purple
    else baseColor = '#94a3b8'; // Slate generic
  } else if (isImmutable) {
    baseColor = '#0ea5e9'; // Cyan for Immutable Concept (Directly from Root)
  }

  // 1. Draw cached offscreen radial glow for active state
  if (isSelected || isHovered || isTraversed) {
    const sprite = glowCache.get(baseColor) || glowCache.get('#fbbf24');
    if (sprite) {
      const glowSize = radius * (isTraversed ? 4.2 : 3.5);
      ctx.drawImage(sprite, x - glowSize / 2, y - glowSize / 2, glowSize, glowSize);
    }
  }

  // 2. Draw Node Shape
  ctx.beginPath();
  if (isRoot) {
    // Pill geometry for Document Roots
    const width = radius * 2.6;
    const height = radius * 1.5;
    if (ctx.roundRect) {
      ctx.roundRect(x - width / 2, y - height / 2, width, height, 4);
    } else {
      ctx.rect(x - width / 2, y - height / 2, width, height);
    }
    ctx.fillStyle = '#0f172a';
    ctx.fill();
    ctx.lineWidth = isSelected ? 2.5 / globalScale : 1.5 / globalScale;
    ctx.strokeStyle = baseColor;
    ctx.stroke();
  } else {
    // Spherical Disc for Concepts
    ctx.arc(x, y, radius, 0, 2 * Math.PI, false);
    ctx.fillStyle = baseColor;
    ctx.fill();
    ctx.lineWidth = isSelected ? 2.5 / globalScale : 1.2 / globalScale;
    ctx.strokeStyle = isSelected ? '#ffffff' : 'rgba(255, 255, 255, 0.3)';
    ctx.stroke();
  }


  // 3. Level-of-Detail (LOD) Typography
  if (globalScale > 1.1 || isSelected || isHovered || isRoot) {
    const fontSize = Math.max(11 / globalScale, 3.2);
    ctx.font = `${isRoot || isSelected ? '600' : '400'} ${fontSize}px "Plus Jakarta Sans", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = isSelected ? '#ffffff' : isRoot ? '#f8fafc' : '#cbd5e1';

    const label = node.title || '';
    const truncated = label.length > 24 ? `${label.slice(0, 21)}...` : label;
    ctx.fillText(truncated, x, y + radius + 4 / globalScale);
  }
};
