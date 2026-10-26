// Rasteriza src/brand/favicon.svg em src/brand/generated/. Rode: pnpm --filter @katoshop/ui build:icons
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const brand = new URL("../src/brand/", import.meta.url);
const out = new URL("generated/", brand);
await mkdir(out, { recursive: true });
const svg = await readFile(new URL("favicon.svg", brand));

async function png(size) {
  return sharp(svg, { density: 384 }).resize(size, size).png({ compressionLevel: 9 }).toBuffer();
}

// ICO com uma imagem PNG de 32x32 (formato aceito por todos os navegadores atuais).
function ico(pngBuf, size) {
  const header = Buffer.alloc(22);
  header.writeUInt16LE(0, 0); // reservado
  header.writeUInt16LE(1, 2); // tipo: ícone
  header.writeUInt16LE(1, 4); // quantidade
  header.writeUInt8(size, 6);
  header.writeUInt8(size, 7);
  header.writeUInt16LE(1, 10); // planos
  header.writeUInt16LE(32, 12); // bits por pixel
  header.writeUInt32LE(pngBuf.length, 14);
  header.writeUInt32LE(22, 18);
  return Buffer.concat([header, pngBuf]);
}

await writeFile(new URL("favicon.ico", out), ico(await png(32), 32));
await writeFile(new URL("apple-touch-icon.png", out), await png(180));
await writeFile(new URL("icon-192.png", out), await png(192));
await writeFile(new URL("icon-512.png", out), await png(512));
console.log("icones gerados em", fileURLToPath(out));
