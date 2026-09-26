'use strict';
// Gera build/icon.png (512) e build/icon.ico (multi-resolução) a partir de build/icon.svg
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const pngToIco = require('png-to-ico');

const DIR = __dirname;
const SVG = path.join(DIR, 'icon.svg');

async function main() {
  const svg = fs.readFileSync(SVG);
  const sizes = [256, 128, 64, 48, 32, 16];

  // PNG principal (usado pelo app / Linux / mac)
  await sharp(svg, { density: 384 }).resize(512, 512).png().toFile(path.join(DIR, 'icon.png'));

  // PNGs temporários para compor o .ico
  const tmp = [];
  for (const s of sizes) {
    const p = path.join(DIR, `._ic_${s}.png`);
    await sharp(svg, { density: 384 }).resize(s, s).png().toFile(p);
    tmp.push(p);
  }

  const ico = await pngToIco(tmp);
  fs.writeFileSync(path.join(DIR, 'icon.ico'), ico);
  tmp.forEach((p) => fs.existsSync(p) && fs.unlinkSync(p));

  console.log('Ícones gerados: build/icon.png e build/icon.ico');
}

main().catch((e) => { console.error(e); process.exit(1); });
