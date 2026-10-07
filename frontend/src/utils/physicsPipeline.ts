export const prewarmForceSimulation = (
  nodes: any[],
  links: any[],
  ticks: number = 180
): { nodes: any[]; links: any[] } => {
  if (!nodes.length) return { nodes, links };

  const nodesCopy = nodes.map((n) => ({ ...n }));
  const linksCopy = links.map((l) => ({ ...l }));

  const d3 = (globalThis as any).d3;
  if (!d3 || !d3.forceSimulation) {
    return { nodes: nodesCopy, links: linksCopy };
  }

  try {
    const simulation = d3
      .forceSimulation(nodesCopy)
      .force(
        'charge',
        d3
          .forceManyBody()
          .strength((d: any) =>
            d.node_type === 'ROOT' || d.is_immutable ? -320 : -140
          )
          .theta(0.85)
      )
      .force(
        'link',
        d3
          .forceLink(linksCopy)
          .id((d: any) => d.id)
          .distance((l: any) => (l.type === 'SUBSET_OF' ? 45 : 85))
          .strength(0.7)
      )
      .force(
        'collide',
        d3
          .forceCollide()
          .radius((d: any) => (d.node_type === 'ROOT' ? 16 : 10) + 4)
          .iterations(2)
      )
      .force('center', d3.forceCenter(0, 0).strength(0.05))
      .velocityDecay(0.55);

    simulation.stop();
    for (let i = 0; i < ticks; ++i) {
      simulation.tick();
    }
  } catch (e) {
    console.warn('Pre-warming simulation skipped:', e);
  }

  return { nodes: nodesCopy, links: linksCopy };
};
