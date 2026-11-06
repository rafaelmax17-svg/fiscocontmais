'use strict';
// Robô do Fechamento do Simples Nacional · Integra Contador (Serpro).
//
// • A chave do Serpro (Consumer Key/Secret) é digitada UMA vez pelo Admin (Admin › Integra Contador) e fica gravada na
//   nuvem num documento que SÓ o Admin lê e grava (segredos_admin/integra — regra do Firestore). Vale para qualquer
//   computador em que o Admin entrar: não é pedida de novo. A equipe nunca vê nem recebe a chave; nada vai para o
//   código ou para o instalador. As pastas (onde salvar os documentos) ficam no mesmo documento.
// • O "robô" é um computador de Admin com o e-CNPJ da Liddera nas Baixas DF-e e o FiscoCont+ aberto: só ele fala com o
//   Serpro (TLS mútuo com o certificado). Se o robô ficar offline, outro computador de Admin com o e-CNPJ assume sozinho.
// • A equipe pede a conferência pelo botão "Conferir na Receita" no Fechamento; o pedido vai pela nuvem
//   (fechamento_sn/integra, sem nada de chave), o robô consulta e grava o resultado na competência.
// • Enquanto ninguém cadastrar a chave, nada muda para a equipe.
// • O robô nunca desmarca o que a analista marcou: quando a Receita discorda, a empresa aparece como "Verificar".
//
// Firestore fechamento_sn/integra (equipe lê): { ativo, roboMaquina, roboNome, heartbeat, pedido{n,comp,ids,por,em},
//   atendido, rodando{comp,feito,total}|null, ultimo{comp,em,por,resumo}, autoDia, consumo{AAAA-MM:{consulta,emissao}} }
// Firestore segredos_admin/integra (só Admin): { key, secret, finalKey, finalSecret, testadoEm, configuradoPor,
//   pastaEmpresas, subpasta, mapa{empresa|empresa|AAAA-MM: pasta}, pendPastas[] }

const fs = require('fs');
const os = require('os');
const path = require('path');
const { safeStorage } = require('electron');
const auth = require('./auth');

const COL = 'fechamento_sn';
const DOC = 'integra';
const COL_SEG = 'segredos_admin';
const CONTRATANTE = '36714399000110';           // LIDDERA CONTABILIDADE LTDA — contrato Integra Contador nº 598158
const LOTE = 8;                                  // empresas por chamada ao núcleo Python (atualiza o progresso entre lotes)
const INTERVALO_REPETIR = 6 * 3600 * 1000;       // a mesma empresa pendente não é consultada de novo antes de 6 h
const HORA_AUTO = 8;                             // conferência automática: 1× por dia, a partir das 08:00
const OFFLINE_MS = 12 * 60 * 1000;               // sem sinal do robô há 12 min = offline (outro Admin pode assumir)

let D = null;                                    // dependências do main.js
let _tok = null;                                 // acesso temporário do Serpro (só em memória)
let _unsub = null, _hb = null, _auto = null, _rodando = false, _ultimoPedido = 0;

function init(deps) { D = deps; }
function _ehAdmin() { const s = auth.sessao(); return !!(s && s.perfil === 'admin'); }
function _quem() { const s = auth.sessao(); return s ? (s.nome || s.email) : ''; }
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
function _ref() { const { db, f } = _fs(); return f.doc(db, COL, DOC); }
function _refSeg() { const { db, f } = _fs(); return f.doc(db, COL_SEG, DOC); }
const _mesAtual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };
function _compAnterior() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
function _vencimento(comp) { let [a, m] = comp.split('-').map(Number); m++; if (m > 12) { m = 1; a++; } return new Date(a, m - 1, 20, 23, 59, 59); }
const _hojeIso = () => new Date().toISOString().slice(0, 10);
function _hojeBr() { const d = new Date(); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`; }
const _ok = (v) => v === 'Sim' || v === 'N/A';

// ------------------------------------------------------------------ configuração (nuvem, só Admin)
async function _cfg() {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  const { f } = _fs();
  const s = await f.getDoc(_refSeg());
  return s.exists() ? s.data() : null;
}
async function _gravaCfg(campos) {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  const { f } = _fs();
  await f.setDoc(_refSeg(), campos, { merge: true });
}

// Preferência só deste computador: qual certificado da Liddera usar (os certificados são de cada computador).
const _localPath = () => path.join(D.userData(), 'integra.json');
function _local() { try { return JSON.parse(fs.readFileSync(_localPath(), 'utf-8')); } catch (_) { return {}; } }
function _gravaLocal(c) { fs.writeFileSync(_localPath(), JSON.stringify(c, null, 1)); }
function _cred() { return D.credEscritorio(_local().certId, CONTRATANTE.slice(0, 8)); }
function _temCert() { const c = _cred(); return !c.error && String((c.dono || {}).cnpj || '').slice(0, 8) === CONTRATANTE.slice(0, 8); }

// Versão 2.1.61/62 guardava a chave só no computador (cifrada pelo Windows): sobe para a nuvem uma vez e apaga daqui.
async function _migrarLocal() {
  const l = _local();
  if (!l.key) return;
  try {
    const atual = await _cfg();
    if (!atual || !atual.key) {
      const key = safeStorage.decryptString(Buffer.from(l.key, 'base64'));
      const secret = safeStorage.decryptString(Buffer.from(l.secret, 'base64'));
      await _gravaCfg({ key, secret, finalKey: key.slice(-4), finalSecret: secret.slice(-4), testadoEm: l.testadoEm || '',
        configuradoPor: _quem(), pastaEmpresas: l.pastaEmpresas || '', subpasta: l.subpasta || '', mapa: l.mapa || {}, pendPastas: l.pendPastas || [] });
    }
    _gravaLocal({ certId: l.certId || '' });
  } catch (_) {}
}

// ------------------------------------------------------------------ chamada ao núcleo Python
async function _python(pedido, chave) {
  const cfg = chave || await _cfg();
  if (!cfg || !cfg.key) throw new Error('Chave do Serpro não cadastrada.');
  const cred = _cred();
  if (cred.error) throw new Error(cred.error);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fc_ig_'));
  const ent = path.join(tmp, 'p.json'), sai = path.join(tmp, 'r.json');
  const corpo = { ...pedido, key: cfg.key, secret: cfg.secret, pfx: cred.pfxPath, senha: cred.senha, contratante: CONTRATANTE, token: _tok };
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
async function estadoLocal() {
  await _migrarLocal();
  const c = (await _cfg()) || {};
  return {
    configurado: !!c.key, certId: _local().certId || ((_cred().dono || {}).id) || '', temCert: _temCert(),
    testadoEm: c.testadoEm || '', configuradoPor: c.configuradoPor || '',
    finalKey: c.finalKey || '', finalSecret: c.finalSecret || '',
    pastaEmpresas: c.pastaEmpresas || '', subpasta: c.subpasta || '',
    fallback: D.pastaFallback() || '', mapa: c.mapa || {}, pendPastas: c.pendPastas || [],
    contratante: CONTRATANTE, sugestaoBase: _sugestaoBase(),
  };
}

// Pasta das empresas do Simples no Drive compartilhado da Liddera, quando existir neste computador (só sugestão).
function _sugestaoBase() {
  for (const p of ['G:\\Drives compartilhados\\Fiscal - Simples Nacional']) { try { if (fs.existsSync(p)) return p; } catch (_) {} }
  return '';
}

async function salvarChave({ key, secret, certId }) {
  if (!_ehAdmin()) throw new Error('Só o Admin cadastra a chave do Serpro.');
  key = String(key || '').trim(); secret = String(secret || '').trim();
  const atual = (await _cfg()) || {};
  if (!key && atual.key) key = atual.key;                         // trocando só o certificado: mantém a chave
  if (!secret && atual.secret) secret = atual.secret;
  if (key.length < 10 || secret.length < 10) throw new Error('Cole o Consumer Key e o Consumer Secret da Área do Cliente do Serpro.');
  if (certId) _gravaLocal({ ..._local(), certId });
  const cred = _cred();
  if (cred.error) throw new Error(cred.error);
  if (String((cred.dono || {}).cnpj || '').slice(0, 8) !== CONTRATANTE.slice(0, 8)) throw new Error('O certificado escolhido não é o e-CNPJ da Liddera (contratante do Integra Contador).');
  // testa antes de salvar: só grava a chave se o Serpro aceitar
  _tok = null;
  let r;
  try { r = await _python({ acao: 'testar' }, { key, secret }); } catch (e) { r = { ok: false, erro: String(e.message || e) }; }
  if (!r.ok) { _tok = null; throw new Error(r.erro || 'O Serpro não aceitou a chave.'); }
  await _gravaCfg({ key, secret, finalKey: key.slice(-4), finalSecret: secret.slice(-4), testadoEm: new Date().toISOString(), configuradoPor: _quem() });
  const { f } = _fs();
  await f.setDoc(_ref(), { ativo: true, roboMaquina: await D.maquina(), roboNome: `${os.hostname()} · ${_quem()}`, configuradoPor: _quem(),
    configuradoEm: f.serverTimestamp(), heartbeat: f.serverTimestamp() }, { merge: true });
  iniciarRobo();
  return { ok: true };
}

async function testar() {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  _tok = null;
  const r = await _python({ acao: 'testar' });
  if (!r.ok) throw new Error(r.erro);
  const testadoEm = new Date().toISOString();
  await _gravaCfg({ testadoEm });
  return { ok: true, testadoEm };
}

async function remover() {
  if (!_ehAdmin()) throw new Error('Acesso restrito ao Admin.');
  pararRobo();
  _tok = null;
  const { f } = _fs();
  await f.setDoc(_refSeg(), { key: f.deleteField(), secret: f.deleteField(), finalKey: '', finalSecret: '', testadoEm: '' }, { merge: true });
  try { await f.setDoc(_ref(), { ativo: false, roboMaquina: '', rodando: null }, { merge: true }); } catch (_) {}
  return { ok: true };
}

async function salvarPastas({ pastaEmpresas, subpasta }) {
  const base = String(pastaEmpresas || '').trim();
  if (base && !fs.existsSync(base)) throw new Error('Não achei essa pasta neste computador.');
  await _gravaCfg({ pastaEmpresas: base, subpasta: String(subpasta || '').trim().replace(/^[\\/]+|[\\/]+$/g, '') });
  return { ok: true };
}

// O Admin aponta a pasta certa de uma empresa (quando o nome bate com nenhuma ou com mais de uma pasta).
async function definirPasta(id, pasta) {
  const c = (await _cfg()) || {};
  const mapa = { ...(c.mapa || {}) };
  if (pasta) mapa[id] = pasta; else delete mapa[id];          // id = empresa, ou empresa|AAAA-MM (pasta da competência)
  const emp = String(id).split('|')[0];
  await _gravaCfg({ mapa, pendPastas: (c.pendPastas || []).filter((p) => p.id !== emp) });
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
async function iniciarRobo() {
  pararRobo();
  if (!_ehAdmin() || !auth.db()) return;
  await _migrarLocal();
  let cfg = null;
  try { cfg = await _cfg(); } catch (_) { return; }
  if (!cfg || !cfg.key || !_temCert()) return;                     // sem chave na nuvem ou sem o e-CNPJ aqui: não é robô
  const maq = await D.maquina();
  const { f } = _fs();
  const nome = `${os.hostname()} · ${_quem()}`;
  // assume o posto quando não há robô ou o robô atual está sem sinal (desligado / FiscoCont+ fechado)
  const assumir = async () => {
    try {
      const s = await f.getDoc(_ref()); const d = s.exists() ? s.data() : {};
      if (!d.ativo || d.roboMaquina === maq) return d.roboMaquina === maq;
      const hb = d.heartbeat && d.heartbeat.toMillis ? d.heartbeat.toMillis() : 0;
      if (d.roboMaquina && hb && Date.now() - hb < OFFLINE_MS) return false;
      await f.updateDoc(_ref(), { roboMaquina: maq, roboNome: nome, heartbeat: f.serverTimestamp() });
      return true;
    } catch (_) { return false; }
  };
  await assumir();
  _unsub = f.onSnapshot(_ref(), (s) => {
    const d = s.exists() ? s.data() : null;
    if (!d || !d.ativo || d.roboMaquina !== maq) return;           // outro computador é o robô
    const p = d.pedido;
    if (p && p.n && p.n > (d.atendido || 0) && p.n !== _ultimoPedido && !_rodando) {
      _ultimoPedido = p.n;
      _executar(p.comp, p.ids, p.por || 'equipe', p.n).catch(() => {});
    }
  }, () => {});
  const bate = async () => {
    try {
      if (await assumir()) await f.updateDoc(_ref(), { heartbeat: f.serverTimestamp() });
    } catch (_) {}
  };
  _hb = setInterval(bate, 4 * 60 * 1000);
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

// Quem entra na conferência (botão e automática): só empresas com "Escrituração concluída = Sim" e ainda não
// confirmadas pela Receita — não paga consulta nem salva documento de empresa que ainda não foi escriturada.
function _alvos(mes, cad, ids, automatica, cfg) {
  const agora = Date.now(), out = [];
  for (const [id, r] of Object.entries(mes)) {
    if (ids && !ids.includes(id)) continue;
    const c = cad[id] || {};
    const rc = r.receita || {};
    if (r.esc !== 'Sim') continue;                                 // só empresas com a Escrituração concluída = Sim
    if (rc.st === 'ok') {
      // confirmada; só volta (para salvar os documentos) se o Admin apontou a pasta ou mudou a pasta das empresas
      if (rc.pastaAviso && (Object.keys(cfg.mapa || {}).some((k) => k === id || k.startsWith(id + '|')) || (cfg.pastaEmpresas || '') !== (rc.pastaBase || ''))) out.push({ id, r, c });
      continue;
    }
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
    const cfg = (await _cfg()) || {};
    if (!cfg.key) throw new Error('Chave do Serpro não cadastrada.');
    const alvos = _alvos(mes, cad, ids, automatica, cfg);
    resumo.pulou = Object.keys(mes).length - alvos.length;
    await f.updateDoc(ref, { rodando: { comp, feito: 0, total: alvos.length, por }, ...(n ? { atendido: n } : {}) });
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
        }, cfg);
        if (!r.ok) throw new Error(r.erro || 'Falha na conferência.');
        res = r.resultados || [];
        consumo.consulta += (r.consumo || {}).consulta || 0; consumo.emissao += (r.consumo || {}).emissao || 0;
      }
      for (const a of sem) res.push({ id: a.id, st: 'semcnpj', msg: 'Empresa sem CNPJ no cadastro do Fechamento.' });
      await _gravaResultados(comp, res, resumo, cfg);
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

async function _gravaResultados(comp, res, resumo, cfg) {
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
        pastaAviso: x.pastaAviso || '', pastaBase: cfg.pastaEmpresas || '', dasAviso: x.dasAviso || '', dasValor: x.dasValor ?? null, dasVenc: x.dasVenc || '',
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
        if (x.pastaAviso) pend.push({ id: x.id, chave: x.pastaChave || x.id, nome: r.nome, aviso: x.pastaAviso, candidatos: x.candidatos || [] });
      } else if (x.st === 'nao') { if (r.pgdas === 'Sim') resumo.verificar++; else resumo.nao++; }
      else resumo[x.st] = (resumo[x.st] || 0) + 1;
    }
    if (Object.keys(upd).length) tx.update(ref, upd);
  });
  if (pend.length) {
    const c = (await _cfg()) || {};
    const m = new Map((c.pendPastas || []).map((p) => [p.id, p]));
    for (const p of pend) m.set(p.id, { ...p, comp });   // uma pendência por empresa (a mais recente)
    await _gravaCfg({ pendPastas: [...m.values()] });
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
