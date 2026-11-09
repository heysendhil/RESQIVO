// Citation URLs come from retrieval metadata, which is untrusted. Only plain
// http(s) URLs become links; anything else (for example the synthetic
// "urn:resqivo:..." identifiers, or "javascript:" URLs) is shown as text.

export function externalUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}
