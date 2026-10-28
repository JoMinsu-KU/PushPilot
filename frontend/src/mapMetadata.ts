import type { TemporaryMap } from '../../contracts/scene';

/** Display names come from the selected map; identifiers remain the API binding. */
export function nodeLabel(map: TemporaryMap | null, id: string | null | undefined): string {
  if (!id) return '—';
  return map?.nodes.find(node => node.id === id)?.label ?? id;
}

/** Round nominal drawing distances for presentation; retain full geometry in the API. */
export function drawingDistance(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '—' : Math.round(value).toLocaleString('en-US');
}

export function planStepLabel(map: TemporaryMap | null, step: { label: string; node_id?: string }): string {
  const suffix = step.node_id ? ` ${step.node_id}` : '';
  return suffix && step.label.endsWith(suffix)
    ? `${step.label.slice(0, -suffix.length)} ${nodeLabel(map, step.node_id)}`
    : step.label;
}

export function destinationOptions(map: TemporaryMap | null): { id: string; label: string }[] {
  return map?.destinations.map(id => ({ id, label: nodeLabel(map, id) })) ?? [];
}

export function destinationPage<T>(items: T[], page: number, size = 3): { items: T[]; page: number; pages: number } {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.max(0, Math.min(page, pages - 1));
  return { items: items.slice(current * size, (current + 1) * size), page: current, pages };
}

/** Include stable node identifiers so duplicate display labels remain unambiguous. */
export function destinationGoal(map: TemporaryMap, destination: string): string {
  return `Push the car from ${map.start} to ${destination}.`;
}
