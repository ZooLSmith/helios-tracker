// Texture decoding (the map images come as the game's raw mips). Pure (no DOM): tested offline
// under Node against a reference decoder.

function rgb565(c, out, o) {
  out[o] = ((c >> 11) & 31) * 255 / 31 | 0;
  out[o + 1] = ((c >> 5) & 63) * 255 / 63 | 0;
  out[o + 2] = (c & 31) * 255 / 31 | 0;
}

/** Colour part of a DXT block at `o` -> 16 RGBA pixels (alpha 255) into `px`. */
function dxtColours(d, o, px, dxt1) {
  const c0 = d[o] | d[o + 1] << 8, c1 = d[o + 2] | d[o + 3] << 8;
  const pal = new Uint8Array(16);
  rgb565(c0, pal, 0); rgb565(c1, pal, 4);
  pal[3] = pal[7] = pal[11] = pal[15] = 255;
  if (c0 > c1 || !dxt1) {
    for (let k = 0; k < 3; k++) {
      pal[8 + k] = (2 * pal[k] + pal[4 + k]) / 3 | 0;
      pal[12 + k] = (pal[k] + 2 * pal[4 + k]) / 3 | 0;
    }
  } else {
    for (let k = 0; k < 3; k++) pal[8 + k] = (pal[k] + pal[4 + k]) / 2 | 0;
    pal[12] = pal[13] = pal[14] = pal[15] = 0; // DXT1 punch-through
  }
  const bits = (d[o + 4] | d[o + 5] << 8 | d[o + 6] << 16 | d[o + 7] << 24) >>> 0;
  for (let k = 0; k < 16; k++) {
    const i = ((bits >>> (2 * k)) & 3) * 4;
    px[k * 4] = pal[i]; px[k * 4 + 1] = pal[i + 1]; px[k * 4 + 2] = pal[i + 2]; px[k * 4 + 3] = pal[i + 3];
  }
}

/** Texture bytes (UE3 EPixelFormat) -> RGBA Uint8ClampedArray of w*h*4. */
export function decodeTexture(format, w, h, data) {
  const out = new Uint8ClampedArray(w * h * 4);
  if (format === "PF_A8R8G8B8") { // stored BGRA
    for (let i = 0; i < w * h; i++) {
      out[i * 4] = data[i * 4 + 2]; out[i * 4 + 1] = data[i * 4 + 1];
      out[i * 4 + 2] = data[i * 4]; out[i * 4 + 3] = data[i * 4 + 3];
    }
    return out;
  }
  if (format === "PF_G8") {
    for (let i = 0; i < w * h; i++) { out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = data[i]; out[i * 4 + 3] = 255; }
    return out;
  }
  const kind = { PF_DXT1: 1, PF_DXT3: 3, PF_DXT5: 5 }[format];
  if (!kind) throw new Error("unsupported texture format " + format);
  const blockSize = kind === 1 ? 8 : 16, bw = (w + 3) >> 2, bh = (h + 3) >> 2;
  const px = new Uint8Array(64), alpha = new Uint8Array(16), apal = new Uint8Array(8);
  for (let by = 0; by < bh; by++) {
    for (let bx = 0; bx < bw; bx++) {
      const o = (by * bw + bx) * blockSize;
      if (o + blockSize > data.length) continue;
      if (kind === 1) {
        dxtColours(data, o, px, true);
      } else {
        dxtColours(data, o + 8, px, false);
        if (kind === 3) {
          for (let k = 0; k < 16; k++) alpha[k] = ((data[o + (k >> 1)] >> ((k & 1) * 4)) & 15) * 17;
        } else {
          const a0 = data[o], a1 = data[o + 1];
          apal[0] = a0; apal[1] = a1;
          if (a0 > a1) for (let k = 1; k < 7; k++) apal[k + 1] = ((7 - k) * a0 + k * a1) / 7 | 0;
          else { for (let k = 1; k < 5; k++) apal[k + 1] = ((5 - k) * a0 + k * a1) / 5 | 0; apal[6] = 0; apal[7] = 255; }
          // 48 bits of 3-bit indices: two 24-bit halves (JS bit ops are 32-bit)
          const lo = data[o + 2] | data[o + 3] << 8 | data[o + 4] << 16;
          const hi = data[o + 5] | data[o + 6] << 8 | data[o + 7] << 16;
          for (let k = 0; k < 8; k++) { alpha[k] = apal[(lo >> (3 * k)) & 7]; alpha[k + 8] = apal[(hi >> (3 * k)) & 7]; }
        }
        for (let k = 0; k < 16; k++) px[k * 4 + 3] = alpha[k];
      }
      for (let k = 0; k < 16; k++) {
        const x = bx * 4 + (k & 3), y = by * 4 + (k >> 2);
        if (x >= w || y >= h) continue;
        const t = (y * w + x) * 4;
        out[t] = px[k * 4]; out[t + 1] = px[k * 4 + 1]; out[t + 2] = px[k * 4 + 2]; out[t + 3] = px[k * 4 + 3];
      }
    }
  }
  return out;
}
