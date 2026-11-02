'use strict';
// Fechamento do Simples Nacional da equipe (Simples Nacional · aba "Fechamento da equipe").
//
// Firestore, coleção fechamento_sn:
//   • cadastro            → { empresas: { id: { nome, cnpj, analista, desde: 'AAAA-MM', ativa, saida, ordem } }, analistas: [nomes] }   (só o Admin grava)
//   • AAAA-MM (competência) → { empresas: { id: { nome, analista, esc, pgdas, das, fin, obs, alteradoPor, alteradoEm } } }
// Cada competência nasce do cadastro (mesmas empresas e analistas, etapas em branco). A data de finalização (fin)
// é automática: preenchida quando escrituração, PGDAS e DAS/DARE ficam Sim ou N/A; apagada se alguma etapa voltar.

const path = require('path');
const fs = require('fs');
const auth = require('./auth');

const COL = 'fechamento_sn';
const ETAPAS = ['esc', 'pgdas', 'das'];
const VALORES = ['Sim', 'Não', 'N/A', ''];
const RE_COMP = /^\d{4}-(0[1-9]|1[0-2])$/;

function _fs() {
  const db = auth.db();
  if (!db) throw new Error('Entre com o seu usuário para usar o fechamento.');
  return { db, f: auth.fsMod() };
}
function _ehAdmin() { const s = auth.sessao(); return !!(s && s.perfil === 'admin'); }
function _quem() { const s = auth.sessao(); return s ? (s.nome || s.email) : ''; }
function _hojeBr() {
  const d = new Date();
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
}
function _concluida(r) { return ETAPAS.every((k) => r[k] === 'Sim' || r[k] === 'N/A'); }
function _novoId() { return 'e' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }
function _prox(c) { let [a, m] = c.split('-').map(Number); m++; if (m > 12) { m = 1; a++; } return `${a}-${String(m).padStart(2, '0')}`; }
function _semMovimento(obs) { return /zerad|sem\s+movimento/i.test(String(obs || '')); }

// Analistas cadastradas sem empresa ainda (entram na lista na primeira abertura do Admin).
const ANALISTAS_NOVAS = ['Taynara'];
function _nomeAn(n) { return String(n || '').trim().replace(/\s+/g, ' ').replace(/(^|\s)(\S)/g, (m, s, l) => s + l.toUpperCase()); }
function _chaveAn(n) { return _nomeAn(n).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
function _uneNomes(...listas) {
  const vistos = new Map();
  for (const l of listas) for (const n of l || []) { const k = _chaveAn(n); if (k && !vistos.has(k)) vistos.set(k, _nomeAn(n)); }
  return [...vistos.values()].sort((a, b) => a.localeCompare(b, 'pt-BR'));
}

function _seed() {
  try { return JSON.parse(fs.readFileSync(path.join(__dirname, 'fechamento-seed.json'), 'utf-8')); } catch (_) { return null; }
}

// Primeira vez (só o Admin): grava o cadastro com as empresas da planilha da equipe e a competência dela já preenchida.
async function _garanteCadastro() {
  const { db, f } = _fs();
  const ref = f.doc(db, COL, 'cadastro');
  const snap = await f.getDoc(ref);
  if (snap.exists()) {
    const d = snap.data();
    // Lista de analistas (versão 2.1.51): na primeira abertura do Admin nasce com as que já têm empresas + as novas da equipe.
    if (!Array.isArray(d.analistas) && _ehAdmin()) {
      const nomes = _uneNomes(Object.values(d.empresas || {}).map((c) => c.analista), ANALISTAS_NOVAS);
      try { await f.updateDoc(ref, { analistas: nomes }); } catch (_) {}
    }
    return d.empresas || {};
  }
  if (!_ehAdmin()) return {};
  const seed = _seed();
  if (!seed) return {};
  const cad = {}, mes = {};
  for (const e of seed.empresas) {
    cad[e.id] = { nome: e.nome, cnpj: '', analista: e.analista, desde: seed.competencia, ativa: true, ordem: e.ordem };
    const r = { nome: e.nome, analista: e.analista, esc: e.esc, pgdas: e.pgdas, das: e.das, obs: e.obs, fin: '' };
    if (_concluida(r)) r.fin = _hojeBr();
    mes[e.id] = r;
  }
  await f.runTransaction(db, async (tx) => {
    const s2 = await tx.get(ref);
    if (s2.exists()) return;
    tx.set(ref, { empresas: cad, analistas: _uneNomes(seed.empresas.map((x) => x.analista), ANALISTAS_NOVAS), criadoPor: _quem(), criadoEm: f.serverTimestamp() });
    tx.set(f.doc(db, COL, seed.competencia), { empresas: mes, criadoPor: _quem(), criadoEm: f.serverTimestamp() }, { merge: true });
  });
  return cad;
}

function _vale(c, comp) {
  return c && (c.desde || '0000-00') <= comp && (c.ativa !== false || (c.saida && comp < c.saida));
}

// Abre a competência: cria se não existir e inclui empresas do cadastro que ainda não estão nela.
async function abrir(comp) {
  if (!RE_COMP.test(comp || '')) throw new Error('Competência inválida.');
  const { db, f } = _fs();
  const cad = await _garanteCadastro();
  const ref = f.doc(db, COL, comp);
  await f.runTransaction(db, async (tx) => {
    const s = await tx.get(ref);
    const atual = s.exists() ? (s.data().empresas || {}) : {};
    const faltam = {}, sobram = [];
    for (const [id, c] of Object.entries(cad)) {
      if (!atual[id] && _vale(c, comp)) faltam[id] = { nome: c.nome, analista: c.analista || '', esc: '', pgdas: '', das: '', obs: '', fin: '' };
      if (atual[id] && c.ativa === false && c.saida && comp >= c.saida) sobram.push(id);     // inativada num mês anterior
    }
    if (!s.exists()) tx.set(ref, { empresas: faltam, criadoPor: _quem(), criadoEm: f.serverTimestamp() });
    else if (Object.keys(faltam).length || sobram.length) {
      const upd = {};
      for (const [id, r] of Object.entries(faltam)) upd[`empresas.${id}`] = r;
      for (const id of sobram) upd[`empresas.${id}`] = f.deleteField();
      tx.update(ref, upd);
    }
  });
  return { ok: true };
}

let _unsubs = [];
function parar() { _unsubs.forEach((u) => { try { u(); } catch (_) {} }); _unsubs = []; }

// Escuta a competência e o cadastro em tempo real: qualquer marcação da equipe chega na hora.
function ouvir(comp, cb) {
  parar();
  const { db, f } = _fs();
  let mes = null, cad = null, lista = [];
  const manda = () => {
    if (!mes || !cad) return;
    const analistas = _uneNomes(lista, Object.values(cad).filter((c) => c.ativa !== false).map((c) => c.analista), Object.values(mes).map((r) => r.analista));
    const linhas = Object.entries(mes).map(([id, r]) => {
      const c = cad[id] || {};
      return {
        id, nome: c.nome || r.nome || '', cnpj: c.cnpj || '', analista: r.analista || c.analista || '', ordem: c.ordem ?? 9999,
        esc: r.esc || '', pgdas: r.pgdas || '', das: r.das || '', obs: r.obs || '', fin: r.fin || '',
        alteradoPor: r.alteradoPor || '', semMovimento: _semMovimento(r.obs),
        inativa: c.ativa === false, saida: c.saida || '',
      };
    }).sort((a, b) => a.ordem - b.ordem || a.nome.localeCompare(b.nome));
    cb({ comp, linhas, analistas, admin: _ehAdmin() });
  };
  _unsubs.push(f.onSnapshot(f.doc(db, COL, comp), (s) => { mes = s.exists() ? (s.data().empresas || {}) : {}; manda(); }, () => {}));
  _unsubs.push(f.onSnapshot(f.doc(db, COL, 'cadastro'), (s) => { const d = s.exists() ? s.data() : {}; cad = d.empresas || {}; lista = Array.isArray(d.analistas) ? d.analistas : []; manda(); }, () => {}));
}

// Marca uma etapa ou a observação. A data de finalização é refeita na mesma gravação.
async function salvar(comp, id, campo, valor) {
  if (!RE_COMP.test(comp || '')) throw new Error('Competência inválida.');
  if (![...ETAPAS, 'obs'].includes(campo)) throw new Error('Campo inválido.');
  valor = String(valor ?? '');
  if (campo === 'obs') valor = valor.slice(0, 300);
  else if (!VALORES.includes(valor)) throw new Error('Valor inválido.');
  const { db, f } = _fs();
  const ref = f.doc(db, COL, comp);
  await f.runTransaction(db, async (tx) => {
    const s = await tx.get(ref);
    const r = s.exists() ? (s.data().empresas || {})[id] : null;
    if (!r) throw new Error('Empresa não está nessa competência.');
    const novo = { ...r, [campo]: valor };
    const fin = _concluida(novo) ? (r.fin || _hojeBr()) : '';
    tx.update(ref, {
      [`empresas.${id}.${campo}`]: valor, [`empresas.${id}.fin`]: fin,
      [`empresas.${id}.alteradoPor`]: _quem(), [`empresas.${id}.alteradoEm`]: f.serverTimestamp(),
    });
  });
  return { ok: true };
}

function _exigeAdmin() { if (!_ehAdmin()) throw new Error('Só o Admin pode cadastrar, alterar ou inativar empresas.'); }

async function cadastrar(comp, { nome, cnpj, analista, desde }) {
  _exigeAdmin();
  nome = String(nome || '').trim().replace(/\s+/g, ' ').toUpperCase();
  cnpj = String(cnpj || '').replace(/\D/g, '');
  analista = _nomeAn(analista);
  desde = RE_COMP.test(desde || '') ? desde : comp;
  if (!nome) throw new Error('Informe a razão social.');
  if (cnpj && cnpj.length !== 14) throw new Error('CNPJ inválido.');
  if (!analista) throw new Error('Informe a analista responsável.');
  const { db, f } = _fs();
  const refC = f.doc(db, COL, 'cadastro');
  const s = await f.getDoc(refC);
  const cad = s.exists() ? (s.data().empresas || {}) : {};
  const dup = Object.values(cad).find((c) => c.ativa !== false && ((cnpj && c.cnpj === cnpj) || c.nome === nome));
  if (dup) throw new Error(`Essa empresa já está cadastrada (${dup.nome}).`);
  const id = _novoId();
  const ordem = Math.max(-1, ...Object.values(cad).map((c) => c.ordem ?? 0)) + 1;
  const c = { nome, cnpj, analista, desde, ativa: true, ordem, cadastradoPor: _quem() };
  if (s.exists()) await f.updateDoc(refC, { [`empresas.${id}`]: c, analistas: _uneNomes(s.data().analistas, [analista]) });
  else await f.setDoc(refC, { empresas: { [id]: c }, analistas: [analista] });
  if (desde <= comp) {
    await f.setDoc(f.doc(db, COL, comp), { empresas: { [id]: { nome, analista, esc: '', pgdas: '', das: '', obs: '', fin: '' } } }, { merge: true });
  }
  return { ok: true, id };
}

async function alterar(comp, id, { nome, analista }) {
  _exigeAdmin();
  const { db, f } = _fs();
  const updC = {}, updM = {};
  if (nome !== undefined) {
    const n = String(nome).trim().replace(/\s+/g, ' ').toUpperCase();
    if (!n) throw new Error('Informe a razão social.');
    updC[`empresas.${id}.nome`] = n; updM[`empresas.${id}.nome`] = n;
  }
  if (analista !== undefined) {
    const a = _nomeAn(analista);
    if (!a) throw new Error('Informe a analista.');
    const sc = await f.getDoc(f.doc(db, COL, 'cadastro'));
    const conhecidas = sc.exists() ? (sc.data().analistas || []) : [];
    if (!conhecidas.some((x) => _chaveAn(x) === _chaveAn(a))) updC.analistas = _uneNomes(conhecidas, [a]);
    updC[`empresas.${id}.analista`] = a; updM[`empresas.${id}.analista`] = a;
  }
  if (!Object.keys(updC).length) return { ok: true };
  await f.updateDoc(f.doc(db, COL, 'cadastro'), updC);
  if (RE_COMP.test(comp || '')) await f.updateDoc(f.doc(db, COL, comp), updM);
  return { ok: true };
}

// Inativa a empresa NO mês aberto: ela continua nesse mês (para terminar o fechamento) e some a partir do próximo.
async function inativar(comp, id) {
  _exigeAdmin();
  if (!RE_COMP.test(comp || '')) throw new Error('Competência inválida.');
  const { db, f } = _fs();
  const saida = _prox(comp);
  await f.updateDoc(f.doc(db, COL, 'cadastro'), { [`empresas.${id}.ativa`]: false, [`empresas.${id}.saida`]: saida, [`empresas.${id}.inativadaPor`]: _quem() });
  // meses seguintes que já tenham sido abertos
  const hoje = new Date();
  const limite = `${hoje.getFullYear() + 1}-${String(hoje.getMonth() + 1).padStart(2, '0')}`;
  for (let c = saida; c <= limite; c = _prox(c)) {
    const ref = f.doc(db, COL, c);
    const sn = await f.getDoc(ref);
    if (sn.exists() && (sn.data().empresas || {})[id]) await f.updateDoc(ref, { [`empresas.${id}`]: f.deleteField() });
  }
  return { ok: true, saida };
}

// Desfaz a inativação: volta a entrar nos próximos meses.
async function reativar(comp, id) {
  _exigeAdmin();
  const { db, f } = _fs();
  await f.updateDoc(f.doc(db, COL, 'cadastro'), { [`empresas.${id}.ativa`]: true, [`empresas.${id}.saida`]: f.deleteField() });
  return { ok: true };
}

// ------------------------------------------------------------------ analistas (só o Admin)
async function analistaNova(nome) {
  _exigeAdmin();
  const n = _nomeAn(nome).slice(0, 40);
  if (n.length < 2) throw new Error('Informe o nome da analista.');
  const { db, f } = _fs();
  const ref = f.doc(db, COL, 'cadastro');
  const s = await f.getDoc(ref);
  const d = s.exists() ? s.data() : {};
  const atual = _uneNomes(d.analistas, Object.values(d.empresas || {}).filter((c) => c.ativa !== false).map((c) => c.analista));
  const ja = atual.find((x) => _chaveAn(x) === _chaveAn(n));
  if (ja) throw new Error(`${ja} já está cadastrada.`);
  const nova = _uneNomes(atual, [n]);
  if (s.exists()) await f.updateDoc(ref, { analistas: nova }); else await f.setDoc(ref, { empresas: {}, analistas: nova });
  return { ok: true, nome: n };
}

// Tira da lista. Só se não houver empresa ativa com ela no cadastro (troque a analista das empresas antes).
async function analistaRemover(nome) {
  _exigeAdmin();
  const { db, f } = _fs();
  const ref = f.doc(db, COL, 'cadastro');
  const s = await f.getDoc(ref);
  if (!s.exists()) return { ok: true };
  const d = s.data(); const k = _chaveAn(nome);
  const usando = Object.values(d.empresas || {}).filter((c) => c.ativa !== false && _chaveAn(c.analista) === k);
  if (usando.length) throw new Error(`${_nomeAn(nome)} ainda é responsável por ${usando.length} empresa(s). Troque a analista delas antes de remover.`);
  await f.updateDoc(ref, { analistas: (d.analistas || []).filter((x) => _chaveAn(x) !== k) });
  return { ok: true };
}

module.exports = { analistaNova, analistaRemover, abrir, ouvir, parar, salvar, cadastrar, alterar, inativar, reativar };
