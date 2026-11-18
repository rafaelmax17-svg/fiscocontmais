// Ícones do app Android a partir do ícone do sistema (build/icon.svg): ícone adaptável (fundo roxo + desenho),
// ícone antigo quadrado/redondo e a tela de abertura. Rodar uma vez depois de "npx cap add android":
//   node mobile/scripts/icones.js      (usa o sharp do projeto principal)
const fs = require('fs');
const path = require('path');
const sharp = require(path.join(__dirname, '..', '..', 'node_modules', 'sharp'));
const RES = path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'res');
const svg = fs.readFileSync(path.join(__dirname, '..', '..', 'build', 'icon.svg'), 'utf-8');
const defs = svg.match(/<defs>[\s\S]*?<\/defs>/)[0];
const desenho = svg.slice(svg.indexOf('<!-- donut ring'), svg.lastIndexOf('</svg>'));
// desenho (anel, visto e o "+") sem o quadrado; centralizado na zona segura do ícone adaptável (66 de 108)
const frente = `<svg width="432" height="432" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">${defs}<g transform="translate(256 256) scale(.62) translate(-262 -238)">${desenho}</g></svg>`;
const fundo = `<svg width="432" height="432" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">${defs}<rect width="512" height="512" fill="url(#bg)"/></svg>`;
const redondo = `<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">${defs}<circle cx="256" cy="256" r="246" fill="url(#bg)"/><g transform="translate(256 256) scale(.78) translate(-262 -238)">${desenho}</g></svg>`;
const D = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
const png = (src, w, h, out) => sharp(Buffer.from(src), { density: 400 }).resize(w, h || w).png().toFile(out);
(async () => {
  for (const [d, k] of Object.entries(D)) {
    const dir = path.join(RES, `mipmap-${d}`);
    await png(svg, Math.round(48 * k), 0, path.join(dir, 'ic_launcher.png'));
    await png(redondo, Math.round(48 * k), 0, path.join(dir, 'ic_launcher_round.png'));
    await png(frente, Math.round(108 * k), 0, path.join(dir, 'ic_launcher_foreground.png'));
    await png(fundo, Math.round(108 * k), 0, path.join(dir, 'ic_launcher_background.png'));
  }
  for (const n of ['ic_launcher.xml', 'ic_launcher_round.xml']) {
    fs.writeFileSync(path.join(RES, 'mipmap-anydpi-v26', n), `<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@mipmap/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
`);
  }
  // abertura: fundo azul-marinho do app com o ícone no meio
  for (const dir of fs.readdirSync(RES).filter((x) => x.startsWith('drawable'))) {
    const f = path.join(RES, dir, 'splash.png'); if (!fs.existsSync(f)) continue;
    const { width: w, height: h } = await sharp(f).metadata();
    const lado = Math.round(Math.min(w, h) * 0.28);
    const icone = await sharp(Buffer.from(svg), { density: 400 }).resize(lado, lado).png().toBuffer();
    await sharp({ create: { width: w, height: h, channels: 4, background: '#18214a' } }).composite([{ input: icone, gravity: 'center' }]).png().toFile(f + '.tmp');
    fs.renameSync(f + '.tmp', f);
  }
  console.log('ícones e abertura gerados');
})().catch((e) => { console.error(e); process.exit(1); });
