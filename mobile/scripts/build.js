// Monta a pasta www (o que vai dentro do app): junta o JS com o Firebase num arquivo só e copia HTML, CSS e imagens.
const fs = require('fs');
const path = require('path');
const esbuild = require('esbuild');
const R = path.join(__dirname, '..');
const W = path.join(R, 'www');
fs.rmSync(W, { recursive: true, force: true });
fs.mkdirSync(W, { recursive: true });
const pkg = require(path.join(R, 'package.json'));
// configuração pública do Firebase (a mesma do sistema no computador; não é segredo)
const cfg = JSON.parse(fs.readFileSync(path.join(R, '..', 'electron', 'firebaseWebConfig.json'), 'utf-8'));
delete cfg._comentario;
esbuild.buildSync({
  entryPoints: [path.join(R, 'src', 'app.js')], bundle: true, minify: true, format: 'iife', target: ['chrome100'],
  outfile: path.join(W, 'app.js'), define: { __FIREBASE__: JSON.stringify(cfg), __VERSAO__: JSON.stringify(pkg.version) }, legalComments: 'none',
});
for (const f of ['index.html', 'app.css']) fs.copyFileSync(path.join(R, 'src', f), path.join(W, f));
fs.copyFileSync(path.join(R, '..', 'assets', 'liddera-logo.png'), path.join(W, 'logo.png'));
console.log('www pronto ·', pkg.version);
