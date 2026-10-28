/** Preserve bounded API diagnostics instead of treating every 409 as a revision conflict. */
export function readableError(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'message' in value && typeof value.message === 'string') return value.message;
  return 'The request could not be completed. Refresh the state and try again.';
}

export function commandErrorMessage(payload: unknown, status: number): string {
  const detail = payload && typeof payload === 'object' && 'detail' in payload ? payload.detail : payload;
  if (detail && typeof detail === 'object' && 'code' in detail && 'message' in detail
      && typeof detail.code === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(detail.code)
      && typeof detail.message === 'string' && detail.message.trim()) {
    return `${detail.code}: ${detail.message}`;
  }
  if (status === 409) return 'The mission state changed. Review the current state before trying again.';
  return readableError(detail);
}
