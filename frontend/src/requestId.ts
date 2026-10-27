interface RequestRandomSource {
  randomUUID?: () => string;
  getRandomValues?: (buffer: Uint8Array<ArrayBuffer>) => Uint8Array<ArrayBuffer>;
}

/** Request identity only; this value is never a credential or an authorization token. */
export function createRequestId(source: RequestRandomSource | undefined = globalThis.crypto): string {
  if (source?.randomUUID) return source.randomUUID();
  const bytes = new Uint8Array(16);
  if (source?.getRandomValues) source.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index++) bytes[index] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0'));
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
}
