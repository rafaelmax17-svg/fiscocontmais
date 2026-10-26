'use strict';
// Manual do Fiscal: leitura dentro do sistema, sem arquivo para salvar.
//
// O conteúdo NÃO vai no instalador nem no repositório (os dois são públicos): fica no Firestore, coleção
// manual_fiscal, e só abre para usuário logado e ativo (firestore.rules).
//   • info            → { versao, titulo, total, capitulos: [{ n, titulo, parte, parteNome, pagina }], publicadoEm, publicadoPor }
//   • p001, p002, …   → { img: JPEG em base64, versao }
// O Admin publica a partir de uma pasta com manual.json + as imagens das páginas (p-01.jpg, p-02.jpg, …).
// Cada abertura fica registrada em manual_acessos (quem, quando, por quanto tempo) — só o Admin lê.

const fs = require('fs');
const path = require('path');
const auth = require('./auth');

const COL = 'manual_fiscal';
const COL_AC = 'manual_acessos';

function _fs() {
  const db = auth.db();
  if (!db) throw new Error('Entre com o seu usuário para abrir o manual.');
  return { db, f: auth.fsMod() };
}
function _ehAdmin() { const s = auth.sessao(); return !!(s && s.perfil === 'admin'); }
const _id = (i) => 'p' + String(i).padStart(3, '0');

async function info() {
  const { db, f } = _fs();
  const s = await f.getDoc(f.doc(db, COL, 'info'));
  if (!s.exists()) return { vazio: true };
  const d = s.data();
  return { versao: d.versao || '', titulo: d.titulo || 'Manual do Fiscal', total: d.total || 0, capitulos: d.capitulos || [] };
}

async function pagina(i) {
  i = Number(i);
  if (!Number.isInteger(i) || i < 1 || i > 999) throw new Error('Página inválida.');
  const { db, f } = _fs();
  const s = await f.getDoc(f.doc(db, COL, _id(i)));
  if (!s.exists()) throw new Error('Página não encontrada.');
  return { img: s.data().img || '' };
}

// Publica (ou troca) o manual a partir de uma pasta: manual.json + imagens das páginas em ordem.
async function publicar(pasta) {
  if (!_ehAdmin()) throw new Error('Só o Admin publica o manual.');
  const meta = JSON.parse(fs.readFileSync(path.join(pasta, 'manual.json'), 'utf-8'));
  const imgs = fs.readdirSync(pasta).filter((n) => /\.jpe?g$/i.test(n)).sort((a, b) => a.localeCompare(b, 'pt-BR', { numeric: true }));
  if (!imgs.length) throw new Error('A pasta não tem as imagens das páginas (.jpg).');
  if (meta.total && meta.total !== imgs.length) throw new Error(`O manual.json fala em ${meta.total} páginas, mas a pasta tem ${imgs.length} imagens.`);
  const { db, f } = _fs();
  const versao = String(meta.versao || '') + '·' + Date.now().toString(36);
  for (let i = 0; i < imgs.length; i++) {
    const b64 = fs.readFileSync(path.join(pasta, imgs[i])).toString('base64');
    if (b64.length > 950000) throw new Error(`A imagem ${imgs[i]} ficou grande demais (máx. ~700 KB).`);
    await f.setDoc(f.doc(db, COL, _id(i + 1)), { img: b64, versao });
  }
  // páginas que sobraram de uma versão maior
  const antes = await f.getDoc(f.doc(db, COL, 'info'));
  const totAnt = antes.exists() ? (antes.data().total || 0) : 0;
  for (let i = imgs.length + 1; i <= totAnt; i++) await f.deleteDoc(f.doc(db, COL, _id(i)));
  const s = auth.sessao() || {};
  await f.setDoc(f.doc(db, COL, 'info'), {
    versao: String(meta.versao || ''), titulo: String(meta.titulo || 'Manual do Fiscal'), total: imgs.length,
    capitulos: Array.isArray(meta.capitulos) ? meta.capitulos : [], publicadoEm: f.serverTimestamp(), publicadoPor: s.nome || s.email || '',
  });
  return { ok: true, total: imgs.length };
}

async function acessoInicio() {
  const s = auth.sessao();
  if (!s || !s.uid) return { id: '' };
  const { db, f } = _fs();
  const ref = await f.addDoc(f.collection(db, COL_AC), {
    uid: s.uid, nome: s.nome || '', email: s.email || '', perfil: s.perfil || '', inicio: f.serverTimestamp(), segundos: 0,
  });
  return { id: ref.id };
}

async function acessoFim(id, segundos) {
  if (!id) return { ok: true };
  const { db, f } = _fs();
  await f.updateDoc(f.doc(db, COL_AC, String(id)), { fim: f.serverTimestamp(), segundos: Math.max(0, Math.round(Number(segundos) || 0)) });
  return { ok: true };
}

async function acessos() {
  if (!_ehAdmin()) throw new Error('Só o Admin vê os acessos.');
  const { db, f } = _fs();
  const q = f.query(f.collection(db, COL_AC), f.orderBy('inicio', 'desc'), f.limit(300));
  const sn = await f.getDocs(q);
  return {
    lista: sn.docs.map((d) => {
      const x = d.data();
      const ini = x.inicio && x.inicio.toDate ? x.inicio.toDate().toISOString() : '';
      return { nome: x.nome || '', email: x.email || '', perfil: x.perfil || '', inicio: ini, segundos: x.segundos || 0 };
    }),
  };
}

module.exports = { info, pagina, publicar, acessoInicio, acessoFim, acessos };
