// zlib inflate with a hard output cap, on the platform's own DecompressionStream ("deflate" is
// the zlib wrapper, RFC 1950, which is what GRF tables and entries use). No third-party inflate
// library: nothing to license-check or pin (THIRD_PARTY.md). The cap is checked chunk by chunk, so
// a decompression bomb is cancelled after at most one chunk past the cap, never held in memory.

export type Inflated = { ok: true; bytes: Uint8Array } | { ok: false; why: "too_big" | "corrupt" };

export async function inflateCapped(data: Uint8Array, cap: number): Promise<Inflated> {
  const stream = new DecompressionStream("deflate");
  const writer = stream.writable.getWriter();
  const reader = stream.readable.getReader();
  // Not awaited before reading: with backpressure, awaiting the write first could deadlock.
  const writing = writer
    .write(data as Uint8Array<ArrayBuffer>)
    .then(() => writer.close())
    .catch(() => undefined);
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > cap) {
        await reader.cancel().catch(() => undefined);
        await writing;
        return { ok: false, why: "too_big" };
      }
      chunks.push(value);
    }
  } catch {
    await writing;
    return { ok: false, why: "corrupt" };
  }
  await writing;
  const out = new Uint8Array(total);
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.byteLength;
  }
  return { ok: true, bytes: out };
}
