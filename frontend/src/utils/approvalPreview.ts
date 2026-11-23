export function formatApprovalReview(
  approvalType: string,
  payload: Record<string, unknown> | undefined,
): string {
  if (!payload || Object.keys(payload).length === 0) {
    return '_No preview payload._';
  }

  switch (approvalType) {
    case 'project_scope': {
      const intro =
        (payload.proposed_introduction as string) ||
        (payload.introduction as string) ||
        '';
      return intro.trim() || '_Empty scope proposal._';
    }
    case 'gist_root': {
      const title = String(payload.title || 'Untitled');
      const gist = String(payload.gist || '');
      return `**${title}**\n\n${gist}`.trim();
    }
    case 'placement': {
      const root = String(payload.root_id || '');
      const candidates = (payload.candidates as unknown[]) || [];
      const lines = candidates.slice(0, 12).map((c, i) => {
        if (Array.isArray(c)) {
          const [id, score] = c;
          return `${i + 1}. \`${id}\`${score != null ? ` (score ${score})` : ''}`;
        }
        if (c && typeof c === 'object') {
          const o = c as Record<string, unknown>;
          return `${i + 1}. \`${o.id || o.target_id || '?'}\` ${o.title || ''}`;
        }
        return `${i + 1}. ${String(c)}`;
      });
      return [`**Placement** for root \`${root}\``, '', ...lines].join('\n');
    }
    case 'intra_doc_staging': {
      const concepts = (payload.concepts as unknown[]) || (payload.staging as unknown[]) || [];
      const header = [
        typeof payload.source_title === 'string' ? `# ${payload.source_title}` : '',
        typeof payload.source_url === 'string' ? `Source: ${payload.source_url}` : '',
        typeof payload.doc_description === 'string' ? payload.doc_description : '',
      ].filter(Boolean);
      if (concepts.length) {
        const rendered = concepts
          .slice(0, 30)
          .map((c, i) => {
            if (typeof c === 'string') return `${i + 1}. ${c}`;
            const o = c as Record<string, unknown>;
            const title = String(o.title || o.name || `Concept ${i + 1}`);
            const description = typeof o.description === 'string' ? o.description : '';
            const passages = Array.isArray(o.passage_indices)
              ? `\n   Source passages: ${o.passage_indices.join(', ')}`
              : '';
            return `${i + 1}. **${title}**${description ? `\n   ${description}` : ''}${passages}`;
          })
          .join('\n');
        return [...header, rendered].filter(Boolean).join('\n\n');
      }
      const key = payload.staging_key ? `Staging: \`${payload.staging_key}\`` : 'Intra-doc staging';
      return [...header, key].filter(Boolean).join('\n\n');
    }
    case 'reorg': {
      const summary =
        (payload.summary as string) ||
        (payload.preview as string) ||
        (payload.proposal_id ? `Proposal \`${payload.proposal_id}\`` : '');
      return summary.trim() || 'Reorganization plan (see payload).';
    }
    default:
      return '```json\n' + JSON.stringify(payload, null, 2) + '\n```';
  }
}
