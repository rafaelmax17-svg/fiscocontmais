'use strict';
// Robô do Fechamento do Simples Nacional · Integra Contador (Serpro).
//
// • A chave do Serpro (Consumer Key/Secret) é digitada UMA vez pelo Admin, na tela Admin › Integra Contador, e fica
//   guardada só neste computador, cifrada pelo Windows (safeStorage) — nunca no código, no instalador ou na nuvem.
// • Este computador vira o "robô": é o único que fala com o Serpro (precisa também do e-CNPJ da Liddera, já cadastrado
//   nas Baixas DF-e). A equipe pede a conferência pelo botão "Conferir na Receita" no Fechamento; o pedido vai pela
//   nuvem (fechamento_sn/integra), o robô consulta e grava o resultado na competência — todos veem na hora.
// • Enquanto ninguém cadastrar a chave, nada muda para a equipe (o documento integra não existe → botão escondido).
// • O robô nunca desmarca o que a analista marcou: quando a Receita discorda, a empresa aparece como "Verificar".
//
// Firestore fechamento_sn/integra: { ativo, roboMaquina, roboNome, heartbeat, pedido{n,comp,ids,por,em},
//   atendido, rodando{comp,feito,total}|null, ultimo{comp,em,por,resumo}, autoDia, consumo{AAAA-MM:{consulta,emissao}} }
// Resultado por empresa na competência: empresas.<id>.receita = { st, msg, decl, dataTrans, em, arquivos, pastaAviso, ... }

const fs = require('fs');
const os = require('os');
const path = require('path');
const { safeStorage } = require('electron');
const auth = require('./auth');

const COL = 'fechamento_sn';
const DOC = 'integra';
const CONTRATANTE = '36714399000110';           // LIDDERA CONTABILIDADE LTDA — contrato Integra Contador nº 598158
const LOTE = 8;                                  // empresas por chamada ao núcleo Python (atualiza o progresso entre lotes)
const INTERVALO_REPETIR = 6 * 3600 * 1000;       // a mesma empresa pendente não é consultada de novo antes de 6 h
const HORA_AUTO = 8;                             // conferência automática: 1× por dia, a partir das 08:00

let D = null;                                    // dependências do main.js
let _tok = null;                                 // acesso temporário do Serpro (só em memória)
let _unsub = null, _hb = null, _auto = null, _rodando = false, _ultimoPedido = 0;

function init(deps) { D = deps; }
const _cfgPath = () => path.join(D.userData(), 'integra.json');
function _lerCfg() { try { return JSON.parse(fs.readFileSync(_cfgPath(), 'utf-8')); } catch (_) { return null; } }
function _gravaCfg(c) { fs.writeFileSync(_cfgPath(), JSON.stringify(c, null, 1)); }
function _cifra(t) { return safeStorage.encryptString(String(t)).toString('base64'); }
function _decifra(b) { return safeStorage.decryptString(Buffer.from(b, 'base64')); }
function _ehAdmin() { const s = auth.sessao(); return !!(s && s.perfil === 'admin'); }
function _quem() { const s = auth.sessao(); return s ? (s.nome || s.email) : ''; }
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
function _ref() { const { db, f } = _fs(); return f.doc(db, COL, DOC); }
const _mesAtual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };
function _compAnterior() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
function _vencimento(comp) { let [a, m] = comp.split('-').map(Number); m++; if (m > 12) { m = 1; a++; } return new Date(a, m - 1, 20, 23, 59, 59); }
const _hojeIso = () => new Date().toISOString().slice(0, 10);
function _hojeBr() { const d = new Date(); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`; }
const _ok = (v) => v === 'Sim' || v === 'N/A';

// ------------------------------------------------------------------ chamada ao núcleo Python
async function _python(pedido) {
  const cfg = _lerCfg();
  if (!cfg || !cfg.key) throw new Error('Chave do Serpro não cadastrada neste computador.');
  const cred = D.credEscritorio(cfg.certId);
  if (cred.error) throw new Error(cred.error);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fc_ig_'));
  const ent = path.join(tmp, 'p.json'), sai = path.join(tmp, 'r.json');
  const corpo = { ...pedido, key: _decifra(cfg.key), secret: _decifra(cfg.secret), pfx: cred.pfxPath, senha: cred.senha, contratante: CONTRATANTE, token: _tok };
  fs.writeFileSync(ent, JSON.stringify(corpo), { mode: 0o600 });
  try {
    await D.runFiscal(['integra', '--entrada', ent, '--json', sai], sai);
    const r = JSON.parse(fs.readFileSync(sai, 'utf-8'));
    if (r.token) _tok = r.token;
    return r;
  } finally {
    fs.rm(tmp, { recursive: true, force: true }, () => {});
  }
}

// ------------------------------------------------------------------ Admin: configuração
function estadoLocal() {
  const c = _lerCfg();
  return {
    configurado: !!(c && c.key), certId: c ? c.certId : '', testadoEm: c ? c.testadoEm : '',
    finalKey: c ? c.finalKey : '', finalSecret: c ? c.finalSecret : '',
    pastaEmpresas: c ? (c.pastaEmpresas || '') : '', subpasta: c ? (c.subpasta || '') : '',
    fallback: D.pastaFallback() || '', mapa: c ? (c.mapa || {}) : {}, pendPastas: c ? (c.pendPastas || []) : [],
    contratante: CONTRATANTE,
  };
}

async function salvarChave({ key, secret, certId }) {
  if (!_ehAdmin()) throw new Error('Só o Admin cadastra a chave do Serpro.');
  key = String(key || '').trim(); secret = String(secret || '').trim();
  const atual = _lerCfg() || {};
  if (!key && atual.key) key = _decifra(atual.key);              // trocando só o certificado: mantém a chave
  if (!secret && atual.secret) secret = _decifra(atual.secret);
  if (key.length < 10 || secret.length < 10) throw new Error('Cole o Consumer Key e o Consumer Secret da Área do Cliente do Serpro.');
  if (!safeStorage.isEncryptionAvailable()) throw new Error('A criptografia segura do Windows não está disponível nesta máquina — não vou guardar a chave sem ela.');
  if (!certId) throw new Error('Escolha o certificado (e-CNPJ) da Liddera.');
  const cred = D.credEscritorio(certId);
  if (cred.error) throw new Error(cred.error);
  if (String(cred.dono.cnpj || '').slice(0, 8) !== CONTRATANTE.slice(0, 8)) throw new Error('O certificado escolhido não é o e-CNPJ da Liddera (contratante do Integra Contador).');
  // testa antes de salvar: só grava a chave se o Serpro aceitar
  const prova = { ...atual, key: _cifra(key), secret: _cifra(secret), certId };
  const bak = _lerCfg();
  _gravaCfg(prova); _tok = null;
  let r;
  try { r = await _python({ acao: 'testar' }); } catch (e) { r = { ok: false, erro: String(e.message || e) }; }
  if (!r.ok) { if (bak) _gravaCfg(bak); else fs.rmSync(_cfgPath(), { force: true }); _tok = null; throw new Error(r.erro || 'O Serpro não aceitou a chave.'); }
  prova.testadoEm = new Date().toISOString();
  prova.finalKey = key.slice(-4); prova.finalSecret = secret.slice(-4);
  _gravaCfg(prova);
  const { f } = _fs();
  const maq = await D.maquina();
  await f.setDoc(_ref(), { ativo: true, roboMaquina: maq, roboNome: `${os.hostname()} · ${_quem()}`, configuradoPor: _quem(),
    configuradoEm: f.serverTimestamp(), heartbeat: f.serverTimestamp() }, { merge: true });
  iniciarRobo();
  return { ok: true };
}

async function testar() {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  _tok = null;
  const r = await _python({ acao: 'testar' });
  if (!r.ok) throw new Error(r.erro);
  const c = _lerCfg(); c.testadoEm = new Date().toISOString(); _gravaCfg(c);
  return { ok: true, testadoEm: c.testadoEm };
}

async function remover() {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  pararRobo();
  fs.rmSync(_cfgPath(), { force: true }); _tok = null;
  const { f } = _fs();
  try { await f.setDoc(_ref(), { ativo: false, roboMaquina: '', rodando: null }, { merge: true }); } catch (_) {}
  return { ok: true };
}

function salvarPastas({ pastaEmpresas, subpasta }) {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  const c = _lerCfg(); if (!c) throw new Error('Cadastre a chave do Serpro primeiro.');
  c.pastaEmpresas = String(pastaEmpresas || '').trim();
  c.subpasta = String(subpasta || '').trim().replace(/^[\\/]+|[\\/]+$/g, '');
  if (c.pastaEmpresas && !fs.existsSync(c.pastaEmpresas)) throw new Error('Não achei essa pasta neste computador.');
  _gravaCfg(c);
  return { ok: true };
}

// O Admin aponta a pasta certa de uma empresa (quando o nome bate com nenhuma ou com mais de uma pasta).
function definirPasta(id, pasta) {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  const c = _lerCfg(); if (!c) throw new Error('Cadastre a chave do Serpro primeiro.');
  c.mapa = c.mapa || {};
  if (pasta) c.mapa[id] = pasta; else delete c.mapa[id];
  c.pendPastas = (c.pendPastas || []).filter((p) => p.id !== id);
  _gravaCfg(c);
  return { ok: true };
}

// ------------------------------------------------------------------ equipe: pedir conferência
async function pedir(comp, ids) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(comp || '')) throw new Error('Competência inválida.');
  const { f } = _fs();
  const s = await f.getDoc(_ref());
  if (!s.exists() || !s.data().ativo) throw new Error('O Integra Contador ainda não foi configurado pelo Admin.');
  const n = Date.now();
  await f.updateDoc(_ref(), { pedido: { n, comp, ids: Array.isArray(ids) ? ids.slice(0, 400) : null, por: _quem(), em: f.serverTimestamp() } });
  return { ok: true };
}

// ------------------------------------------------------------------ robô
function _souRobo(d) { return d && d.ativo && d.roboMaquina && _lerCfg() && _lerCfg().key; }

async function iniciarRobo() {
  pararRobo();
  if (!_ehAdmin() || !auth.db()) return;
  const cfg = _lerCfg(); if (!cfg || !cfg.key) return;
  const maq = await D.maquina();
  const { f } = _fs();
  _unsub = f.onSnapshot(_ref(), (s) => {
    const d = s.exists() ? s.data() : null;
    if (!d || !d.ativo || d.roboMaquina !== maq) return;           // outro computador virou o robô
    const p = d.pedido;
    if (p && p.n && p.n > (d.atendido || 0) && p.n !== _ultimoPedido && !_rodando) {
      _ultimoPedido = p.n;
      _executar(p.comp, p.ids, p.por || 'equipe', p.n).catch(() => {});
    }
  }, () => {});
  const bate = async () => {
    try {
      const s = await f.getDoc(_ref());
      if (s.exists() && s.data().roboMaquina === maq) await f.updateDoc(_ref(), { heartbeat: f.serverTimestamp() });
    } catch (_) {}
  };
  bate(); _hb = setInterval(bate, 4 * 60 * 1000);
  const auto = async () => {
    try {
      if (new Date().getHours() < HORA_AUTO || _rodando) return;
      const s = await f.getDoc(_ref()); const d = s.exists() ? s.data() : {};
      if (d.roboMaquina !== maq || d.autoDia === _hojeIso()) return;
      await f.updateDoc(_ref(), { autoDia: _hojeIso() });
      await _executar(_compAnterior(), null, 'automática', 0, true);
    } catch (_) {}
  };
  setTimeout(auto, 60 * 1000); _auto = setInterval(auto, 30 * 60 * 1000);
}
function pararRobo() {
  if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; }
  if (_hb) { clearInterval(_hb); _hb = null; }
  if (_auto) { clearInterval(_auto); _auto = null; }
}

// Quem entra na conferência: empresas ainda não confirmadas pela Receita. A automática só olha as que já têm a
// escrituração concluída (ou PGDAS marcado), para não pagar consulta de empresa que nem foi escriturada.
function _alvos(mes, cad, ids, automatica) {
  const agora = Date.now(), out = [];
  for (const [id, r] of Object.entries(mes)) {
    if (ids && !ids.includes(id)) continue;
    const c = cad[id] || {};
    const rc = r.receita || {};
    if (rc.st === 'ok') {
      // confirmada; só volta (para salvar os documentos) se o Admin apontou a pasta ou mudou a pasta das empresas
      const cfg = _lerCfg() || {};
      if (rc.pastaAviso && ((cfg.mapa || {})[id] || (cfg.pastaEmpresas || '') !== (rc.pastaBase || ''))) out.push({ id, r, c });
      continue;
    }
    if (automatica && !_ok(r.esc) && r.pgdas !== 'Sim') continue;
    if (rc.st && rc.st !== 'ok' && rc.emMs && agora - rc.emMs < INTERVALO_REPETIR && rc.st !== 'semcnpj') continue;
    out.push({ id, r, c });
  }
  return out;
}

async function _executar(comp, ids, por, n, automatica) {
  if (_rodando) return;
  _rodando = true;
  const { db, f } = _fs();
  const ref = _ref();
  const resumo = { ok: 0, nao: 0, verificar: 0, semproc: 0, semcnpj: 0, erro: 0, pulou: 0, arquivos: 0 };
  try {
    const sm = await f.getDoc(f.doc(db, COL, comp));
    const sc = await f.getDoc(f.doc(db, COL, 'cadastro'));
    const mes = sm.exists() ? (sm.data().empresas || {}) : {};
    const cad = sc.exists() ? (sc.data().empresas || {}) : {};
    const alvos = _alvos(mes, cad, ids, automatica);
    resumo.pulou = Object.keys(mes).length - alvos.length;
    await f.updateDoc(ref, { rodando: { comp, feito: 0, total: alvos.length, por }, ...(n ? { atendido: n } : {}) });
    const cfg = _lerCfg();
    const emitirDas = Date.now() <= _vencimento(comp).getTime();
    let feito = 0;
    const consumo = { consulta: 0, emissao: 0 };
    for (let i = 0; i < alvos.length; i += LOTE) {
      const lote = alvos.slice(i, i + LOTE);
      const sem = lote.filter((a) => String(a.c.cnpj || '').replace(/\D/g, '').length !== 14);
      const com = lote.filter((a) => !sem.includes(a));
      let res = [];
      if (com.length) {
        const r = await _python({
          acao: 'conferir', comp, baixar: true, emitirDas,
          empresas: com.map((a) => ({ id: a.id, cnpj: a.c.cnpj, nome: a.c.nome || a.r.nome, das: a.r.das })),
          pastas: { base: cfg.pastaEmpresas || '', subpasta: cfg.subpasta || '', mapa: cfg.mapa || {}, fallback: D.pastaFallback() || '' },
        });
        if (!r.ok) throw new Error(r.erro || 'Falha na conferência.');
        res = r.resultados || [];
        consumo.consulta += (r.consumo || {}).consulta || 0; consumo.emissao += (r.consumo || {}).emissao || 0;
      }
      for (const a of sem) res.push({ id: a.id, st: 'semcnpj', msg: 'Empresa sem CNPJ no cadastro do Fechamento.' });
      await _gravaResultados(comp, res, resumo);
      feito += lote.length;
      await f.updateDoc(ref, { rodando: { comp, feito, total: alvos.length, por } });
    }
    const mesC = _mesAtual();
    await f.updateDoc(ref, {
      rodando: null,
      ultimo: { comp, em: f.serverTimestamp(), emBr: new Date().toLocaleString('pt-BR'), por, total: alvos.length, resumo },
      [`consumo.${mesC}.consulta`]: f.increment(consumo.consulta), [`consumo.${mesC}.emissao`]: f.increment(consumo.emissao),
    });
  } catch (e) {
    try { await f.updateDoc(ref, { rodando: null, ultimo: { comp, em: f.serverTimestamp(), emBr: new Date().toLocaleString('pt-BR'), por, erro: String(e.message || e).slice(0, 300), resumo } }); } catch (_) {}
  } finally {
    _rodando = false;
  }
}

async function _gravaResultados(comp, res, resumo) {
  const { db, f } = _fs();
  const ref = f.doc(db, COL, comp);
  const pend = [];
  await f.runTransaction(db, async (tx) => {
    const s = await tx.get(ref);
    const emp = s.exists() ? (s.data().empresas || {}) : {};
    const upd = {};
    for (const x of res) {
      const r = emp[x.id]; if (!r) continue;
      const rc = {
        st: x.st, msg: x.msg || '', em: new Date().toLocaleString('pt-BR').slice(0, 17), emMs: Date.now(),
        decl: x.decl || '', dataTrans: x.dataTrans || '', pasta: x.pasta || '',
        arquivos: Object.fromEntries(Object.entries(x.arquivos || {}).map(([k, v]) => [k, path.basename(v)])),
        pastaAviso: x.pastaAviso || '', pastaBase: (_lerCfg() || {}).pastaEmpresas || '', dasAviso: x.dasAviso || '', dasValor: x.dasValor ?? null, dasVenc: x.dasVenc || '',
      };
      // confirmação já gravada antes e agora só faltavam os arquivos: mantém a data da confirmação
      if (x.st === 'ok' && r.receita && r.receita.st === 'ok') { rc.decl = rc.decl || r.receita.decl || ''; }
      upd[`empresas.${x.id}.receita`] = rc;
      if (x.st === 'ok') {
        resumo.ok++;
        if (r.pgdas === '' || r.pgdas === 'Não' || r.pgdas == null) {            // a Receita confirma: marca Sim
          upd[`empresas.${x.id}.pgdas`] = 'Sim';
          upd[`empresas.${x.id}.pgdasRobo`] = true;
          upd[`empresas.${x.id}.alteradoPor`] = 'Robô (Receita Federal)';
          upd[`empresas.${x.id}.alteradoEm`] = f.serverTimestamp();
          const novo = { ...r, pgdas: 'Sim' };
          upd[`empresas.${x.id}.fin`] = (_ok(novo.esc) && _ok(novo.pgdas) && _ok(novo.das)) ? (r.fin || _hojeBr()) : '';
        }
        if (r.pgdas === 'N/A') resumo.verificar++;
        resumo.arquivos += Object.keys(rc.arquivos).length;
        if (x.pastaAviso) pend.push({ id: x.id, nome: r.nome, aviso: x.pastaAviso, candidatos: x.candidatos || [] });
      } else if (x.st === 'nao') { if (r.pgdas === 'Sim') resumo.verificar++; else resumo.nao++; }
      else resumo[x.st] = (resumo[x.st] || 0) + 1;
    }
    if (Object.keys(upd).length) tx.update(ref, upd);
  });
  if (pend.length) {
    const c = _lerCfg();
    const m = new Map((c.pendPastas || []).map((p) => [p.id, p]));
    for (const p of pend) m.set(p.id, { ...p, comp });
    c.pendPastas = [...m.values()]; _gravaCfg(c);
  }
}

// Painel do Admin: o que está na nuvem sobre o robô.
async function estadoNuvem() {
  const { f } = _fs();
  const s = await f.getDoc(_ref());
  const d = s.exists() ? s.data() : {};
  const maq = await D.maquina();
  const hb = d.heartbeat && d.heartbeat.toMillis ? d.heartbeat.toMillis() : 0;
  return {
    ativo: !!d.ativo, esteComputador: d.roboMaquina === maq, roboNome: d.roboNome || '',
    online: !!hb && Date.now() - hb < 12 * 60 * 1000, ultimo: d.ultimo ? { ...d.ultimo, em: undefined } : null,
    consumo: (d.consumo || {})[_mesAtual()] || { consulta: 0, emissao: 0 }, rodando: d.rodando || null,
  };
}

module.exports = { init, estadoLocal, estadoNuvem, salvarChave, testar, remover, salvarPastas, definirPasta, pedir, iniciarRobo, pararRobo, CONTRATANTE };
