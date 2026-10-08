/** Accept only snapshots that do not discard events already delivered over SSE. */
export function mergeSnapshot<T extends { generation?: number; revision: number; events: { id: number }[] }>(current: T | null, incoming: T): T {
  if (!current) return incoming;
  if ((incoming.generation ?? 0) < (current.generation ?? 0)) return current;
  if ((incoming.generation ?? 0) > (current.generation ?? 0)) return incoming;
  const currentCursor = current.events.at(-1)?.id ?? 0;
  const incomingCursor = incoming.events.at(-1)?.id ?? 0;
  if (incomingCursor < currentCursor || (incomingCursor === currentCursor && incoming.revision < current.revision)) return current;
  return incoming;
}
