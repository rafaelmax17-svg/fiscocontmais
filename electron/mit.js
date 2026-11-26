'use strict';
// MIT · PIS e COFINS (2.4.26 · 2.4.27) — envio pela Receita com a Liddera (e-CNPJ) como procuradora dos clientes.
//
// • Equipe (módulo "MIT"): importa a EFD-Contribuições (M205/M605 = código e valor a recolher; M200/M600; saldo credor
//   em 1100/1500), confere a tributação do lucro de cada empresa (fica guardada) e, se quiser, digita IRPJ/CSLL. Depois
//   pede o envio: os pedidos vão pela nuvem (mit_pedidos) e o computador do Admin que fala com a Receita (o mesmo robô
//   da DCTFWeb) atende.
// • Robô: monta o MIT (leiaute JSON 1.0 da Receita) e envia com a Liddera como procuradora (autor do pedido = e-CNPJ do
//   escritório, como a DCTFWeb e o PGDAS); o CPF do responsável pela apuração vai dentro do MIT. Acompanha o
//   encerramento e lê a DCTFWeb do mês. Também gera a guia só do MIT e transmite a DCTFWeb (assinatura do XML feita pelo programa com o
//   certificado do escritório — não usa o assinador do portal).
// • Com saldo credor o MIT não é necessário. "Sem movimento" só quando a equipe marca; o robô confere antes se a
//   DCTFWeb do mês tem débito de outra origem (eSocial / EFD-Reinf) e, se tiver, não envia (IN RFB 2.237/2024, art. 6º, § 2º).
//
// Firestore: mit/<AAAA-MM>_<CNPJ> (equipe e robô), mit_empresas/<CNPJ> (tributação guardada), mit_config/responsavel
// (só o resumo para a tela — o CPF completo fica no computador do robô), mit_pedidos/<id>.
const fs = require('fs');
const path = require('path');
const os = require('os');
const auth = require('./auth');
const pastaCliente = require('./pasta_cliente');

const COL = 'mit';
const COL_P = 'mit_pedidos';
const COL_E = 'mit_empresas';
const MODULO = 'fiscal-mit';
let D = null;
let _unsub = null, _robo = null, _rodando = false, _logTxt = [];
let _vigia = null, _rodandoDesde = 0, _geracao = 0;
const _atendidos = new Set();

function init(deps) { D = deps; }
function podeUsar(s = auth.sessao()) {
  if (!s) return false;
  if (s.perfil === 'admin') return true;
  return Array.isArray(s.modulos) ? s.modulos.includes(MODULO) : s.perfil === 'fiscal';
}
function _fs() { const db = auth.db(); if (!db) throw new Error('Entre com o seu usuário.'); return { db, f: auth.fsMod() }; }
const _quem = () => { const s = auth.sessao() || {}; return s.nome || s.email || ''; };
const _so = (s) => String(s || '').replace(/\D/g, '');
const _comp = (c) => /^\d{4}-(0[1-9]|1[0-2])$/.test(c || '');
const _r2 = (v) => Math.round((Number(v) || 0) * 100) / 100;
// 2.4.34: débitos de todas as origens somados por código (o mesmo código pode vir da folha e da REINF: somar, nunca sobrescrever)
function _tudo(x) {
  if (x && x.tudo && Object.keys(x.tudo).length) return x.tudo;
  const m = {};
  for (const o of [(x && x.outros) || {}, (x && x.reinf) || {}]) for (const [k, v] of Object.entries(o)) m[k] = Math.round(((m[k] || 0) + Number(v || 0)) * 100) / 100;
  return m;
}
function _limpo(o) { return JSON.parse(JSON.stringify(o, (k, v) => (v === undefined ? null : v))); }
function _log(m) {
  const l = `[${new Date().toLocaleString('pt-BR')}] ${m}`;
  _logTxt.push(l); if (_logTxt.length > 400) _logTxt = _logTxt.slice(-300);
  try { fs.appendFileSync(path.join(D.userData(), 'mit_log.txt'), l + '\n'); } catch (_) {}
}
const _totalExtras = (ex) => _r2((ex || []).reduce((s, x) => s + (Number(x.valor) || 0), 0));
function situacaoDe(d) {
  if (!d) return '';
  if (d.mit && d.mit.situacao === 3) return d.mit.semMovimento ? 'sem_movimento' : 'enviado';
  if (d.mit && d.mit.situacao === 4) return 'em_curso';
  if (d.mitDispensado) return 'dispensado';        // 2.4.57: sem débito e a DCTFWeb já tem débitos da folha/REINF
  return (d.total || 0) + _totalExtras(d.extras) > 0 ? 'a_enviar' : 'saldo_credor';
}

async function _estadoRobo() {
  try {
    const { db, f } = _fs();
    const s = await f.getDoc(f.doc(db, 'fechamento_sn', 'integra'));
    const d = s.exists() ? s.data() : {};
    const hb = d.heartbeat && d.heartbeat.toMillis ? d.heartbeat.toMillis() : 0;
    return { ativo: !!d.ativo, online: !!hb && Date.now() - hb < 12 * 60 * 1000, nome: d.roboNome || '', visto: hb || 0 };
  } catch (_) { return { ativo: false, online: false, nome: '' }; }
}

// ------------------------------------------------------------------ equipe
async function dados(comp) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo MIT.');
  if (!_comp(comp)) throw new Error('Competência inválida.');
  const { db, f } = _fs();
  const docs = [], pedidos = [];
  (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp)))).forEach((x) => { const d = x.data(); docs.push({ ...d, sit: situacaoDe(d) }); });
  try {
    (await f.getDocs(f.query(f.collection(db, COL_P), f.where('comp', '==', comp)))).forEach((x) => {
      const p = x.data();
      pedidos.push({ id: x.id, tipo: p.tipo, status: p.status, cnpjs: p.cnpjs || [], por: p.por || '', msg: p.msg || '', emMs: p.emMs || 0, fimMs: p.fimMs || 0 });
    });
  } catch (_) {}
  pedidos.sort((a, b) => b.emMs - a.emMs);
  let resp = null;
  try { const s = await f.getDoc(f.doc(db, 'mit_config', 'responsavel')); resp = s.exists() ? s.data() : null; } catch (_) {}
  let auto = { ligado: false };
  try { const s = await f.getDoc(f.doc(db, 'mit_config', 'automatico')); if (s.exists()) auto = { ligado: !!s.data().ligado, por: s.data().por || '', em: s.data().em || '' }; } catch (_) {}
  docs.sort((a, b) => String(a.nome || '').localeCompare(String(b.nome || '')));
  return { comp, docs, pedidos: pedidos.slice(0, 30), robo: await _estadoRobo(), resp, auto };
}

// lê as EFD-Contribuições escolhidas e grava uma linha por empresa (a competência vem do próprio arquivo)
async function importar(arquivos) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo MIT.');
  if (!Array.isArray(arquivos) || !arquivos.length) throw new Error('Escolha os arquivos da EFD-Contribuições.');
  const sai = path.join(os.tmpdir(), `fc_mit_${Date.now()}.json`);
  await D.runFiscal(['mit-ler', '--efd', ...arquivos, '--json', sai], sai);
  const r = JSON.parse(fs.readFileSync(sai, 'utf-8')); fs.unlink(sai, () => {});
  const { db, f } = _fs();
  const ok = [], erros = [], comps = new Set();
  for (const e of r.empresas || []) {
    if (e.erro || !e.cnpj || !e.comp) { erros.push(`${path.basename(e.arquivo || '')}: ${e.erro || 'arquivo inválido'}`); continue; }
    comps.add(e.comp);
    const ref = f.doc(db, COL, `${e.comp}_${e.cnpj}`);
    const s = await f.getDoc(ref); const ant = s.exists() ? s.data() : null;
    let trib = 0, bal = false, semFolha = false;
    try { const t = await f.getDoc(f.doc(db, COL_E, e.cnpj)); trib = t.exists() ? (t.data().tributacao || 0) : 0; bal = t.exists() ? !!t.data().balanco : false; semFolha = t.exists() ? !!t.data().semFolha : false; } catch (_) {}
    const valores = JSON.stringify([e.pis, e.cofins]);
    const mudou = !!(ant && ant.mit && ant.mit.situacao === 3 && ant.valoresAssinatura && ant.valoresAssinatura !== valores);
    await f.setDoc(ref, _limpo({
      comp: e.comp, cnpj: e.cnpj, nome: e.nome, arquivo: path.basename(e.arquivo || ''), regime: e.regime, retificadora: !!e.retificadora,
      pis: e.pis, cofins: e.cofins, total: e.total, saldoPis: e.saldo_pis, saldoCofins: e.saldo_cofins,
      tributacao: (ant && ant.tributacao) || trib || e.tributacao_sugerida || 1, balanco: ant && ant.balanco !== undefined ? !!ant.balanco : bal, semFolha: ant && ant.semFolha !== undefined ? !!ant.semFolha : semFolha, extras: (ant && ant.extras) || [],
      valoresAssinatura: valores, mudouDepoisDoEnvio: mudou, importadoPor: _quem(), importadoEm: new Date().toISOString(),
    }), { merge: true });
    ok.push(e.nome);
  }
  return { importadas: ok.length, erros, comps: [...comps].sort(), codigos: r.codigos_irpj_csll || {} };
}

async function salvarEmpresa({ comp, cnpj, tributacao, extras, balanco, semFolha } = {}) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo MIT.');
  cnpj = _so(cnpj);
  if (!_comp(comp) || cnpj.length !== 14) throw new Error('Empresa inválida.');
  const { db, f } = _fs();
  const ref = f.doc(db, COL, `${comp}_${cnpj}`);
  const s = await f.getDoc(ref);
  if (!s.exists()) throw new Error('Empresa não importada nesta competência.');
  const campos = {};
  // 2.4.53: "sem folha" (a DCTFWeb original pode ser transmitida sozinha) vale para a empresa toda, mesmo depois do MIT
  if (semFolha !== undefined) {
    const ss = auth.sessao();
    if (!ss || ss.perfil !== 'admin') throw new Error('Só o Admin marca ou desmarca "sem folha".');
    campos.semFolha = !!semFolha;
    await f.setDoc(f.doc(db, COL_E, cnpj), { semFolha: !!semFolha, por: _quem(), em: new Date().toISOString() }, { merge: true });
    if (tributacao === undefined && balanco === undefined && extras === undefined) { await f.setDoc(ref, _limpo(campos), { merge: true }); return { ok: true }; }
  }
  if ((s.data().mit || {}).situacao === 3) throw new Error('O MIT desta empresa já foi enviado.');
  if (tributacao !== undefined) {
    const t = Number(tributacao);
    if (![1, 2, 3, 4, 5, 6].includes(t)) throw new Error('Tributação inválida.');
    campos.tributacao = t;
    await f.setDoc(f.doc(db, COL_E, cnpj), { tributacao: t, por: _quem(), em: new Date().toISOString() }, { merge: true });
  }
  if (balanco !== undefined) {
    campos.balanco = !!balanco;
    await f.setDoc(f.doc(db, COL_E, cnpj), { balanco: !!balanco, por: _quem(), em: new Date().toISOString() }, { merge: true });
  }
  if (extras !== undefined) {
    campos.extras = (extras || []).map((x) => ({ grupo: x.grupo === 'Csll' ? 'Csll' : 'Irpj', cod: _so(x.cod).padStart(6, '0').slice(-6), valor: _r2(x.valor), rotulo: String(x.rotulo || '').slice(0, 80) }))
      .filter((x) => x.valor > 0 && x.cod !== '000000');
  }
  await f.setDoc(ref, _limpo(campos), { merge: true });
  return { ok: true };
}

// 2.4.53: envio automático (vale para a equipe toda): MIT com movimento → guia → DCTFWeb (retificadora ou empresa
// "sem folha") → recibo na pasta da competência
async function configAuto(ligado) {
  const ss = auth.sessao();
  if (!ss || ss.perfil !== 'admin') throw new Error('Só o Admin liga ou desliga o envio automático.');
  const { db, f } = _fs();
  await f.setDoc(f.doc(db, 'mit_config', 'automatico'), { ligado: !!ligado, por: _quem(), em: new Date().toISOString() }, { merge: true });
  return { ligado: !!ligado };
}

async function pedir({ tipo, comp, cnpjs, semMovimento, confirmado, data } = {}) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo MIT.');
  if (!['consultar', 'enviar', 'guia', 'transmitir', 'recibo'].includes(tipo)) throw new Error('Pedido inválido.');
  if (!_comp(comp)) throw new Error('Competência inválida.');
  const robo = await _estadoRobo();
  if (!robo.ativo) throw new Error('O envio pela Receita ainda não foi configurado pelo Admin.');
  const { db, f } = _fs();
  const lista = (Array.isArray(cnpjs) ? cnpjs : []).map(_so).filter((c) => c.length === 14);
  if (!lista.length) throw new Error('Escolha a(s) empresa(s).');
  const extra = {};
  if (tipo === 'enviar') {
    // 2.4.57: no mesmo lote vão as empresas com débito (MIT com os débitos da EFD) e as sem débito (MIT sem movimento)
    const semMov = [];
    for (const c of lista) {
      const s = await f.getDoc(f.doc(db, COL, `${comp}_${c}`)); const d = s.exists() ? s.data() : null;
      if (!d) throw new Error('Empresa não importada.');
      const sit = situacaoDe(d);
      if (['enviado', 'sem_movimento', 'em_curso'].includes(sit)) throw new Error(`${d.nome}: o MIT já foi enviado.`);
      if (sit === 'saldo_credor' || sit === 'dispensado') semMov.push(c);
      else if (sit !== 'a_enviar') throw new Error(`${d.nome}: situação ${sit}.`);
    }
    if (semMov.length) extra.semMov = semMov;
    if (semMovimento && lista.length === 1 && semMov.length === 1) extra.semMovimento = true;
    try { const a = await f.getDoc(f.doc(db, 'mit_config', 'automatico')); if (a.exists() && a.data().ligado) extra.auto = true; } catch (_) {}
  }
  if (tipo === 'transmitir') {
    if (lista.length !== 1) throw new Error('Escolha uma empresa para transmitir.');
    if (!confirmado || !confirmado.folha || !confirmado.reinf || !confirmado.mit) throw new Error('Confirme a folha (eSocial), a EFD-Reinf e o MIT antes de transmitir.');
    extra.confirmado = { folha: true, reinf: true, mit: true };
  }
  if (tipo === 'guia' && data) { if (!/^\d{4}-\d{2}-\d{2}$/.test(data)) throw new Error('Data de pagamento inválida.'); extra.data = data; }
  // não deixa o mesmo pedido duas vezes na fila
  const ab = await f.getDocs(f.query(f.collection(db, COL_P), f.where('comp', '==', comp)));
  let dup = false;
  ab.forEach((x) => { const p = x.data(); if (p.tipo === tipo && ['novo', 'rodando'].includes(p.status) && (p.cnpjs || []).some((c) => lista.includes(c))) dup = true; });
  if (dup) throw new Error('Já existe um pedido igual na fila para esta empresa.');
  const s = auth.sessao() || {};
  const ref = await f.addDoc(f.collection(db, COL_P), {
    tipo, comp, cnpjs: lista, ...extra, status: 'novo', por: _quem(), uid: s.uid || '', maquina: os.hostname(), emMs: Date.now(), em: f.serverTimestamp(),
  });
  return { id: ref.id, roboOnline: robo.online };
}

// ------------------------------------------------------------------ robô (computador do Admin que fala com a Receita)
function ligarRobo(opc) {
  desligarRobo();
  _robo = opc;                             // { souRobo(), python(pedido) [já com o procurador], consumo(c) }
  let f, db;
  try { ({ db, f } = _fs()); } catch (_) { return; }
  const q = f.query(f.collection(db, COL_P), f.where('status', '==', 'novo'));
  // 2.4.36: se a escuta da nuvem cair (rede/servidor), o Firestore não religa sozinho — antes a fila parava em silêncio
  const escuta = () => {
    _unsub = f.onSnapshot(q, (snap) => {
      if (!_robo || !_robo.souRobo()) return;
      const novos = [];
      snap.forEach((x) => { if (!_atendidos.has(x.id)) novos.push({ id: x.id, ...x.data() }); });
      novos.sort((a, b) => (a.emMs || 0) - (b.emMs || 0));
      if (novos.length) _fila(novos);
    }, (e) => {
      _log(`escuta da fila caiu (${(e && (e.code || e.message)) || 'sem detalhe'}); religando em 15 s`);
      _unsub = null;
      setTimeout(() => { if (_robo && !_unsub) escuta(); }, 15000);
    });
  };
  _escuta = escuta;
  escuta();
  _log(`fila ligada neste computador (${os.hostname()})${_robo.souRobo() ? ' · é o robô' : ' · aguardando ser o robô'}`);
  // varredura de segurança a cada minuto: pega pedido parado na fila e destrava a fila presa
  _vigia = setInterval(() => _varrer().then(() => { _nFalha = 0; }).catch((e) => _falhaNuvem(e)), 60 * 1000);
}

// 2.4.50: a conexão com a nuvem pode cair sem dar erro (computador que dormiu, rede que trocou) — a escuta para de avisar e a
// leitura devolve a cópia local, sem pedido novo. A varredura lê direto do servidor; 2 falhas seguidas → reconecta sozinho.
let _escuta = null, _nFalha = 0, _religou = 0;
async function _falhaNuvem(e) {
  _nFalha++;
  if (_nFalha === 1 || _nFalha % 10 === 0) _log(`varredura da fila sem resposta da nuvem (${(e && (e.code || e.message)) || e}) · ${_nFalha}ª vez`);
  if (_nFalha < 2 || !_robo || Date.now() - _religou < 5 * 60 * 1000) return;
  _religou = Date.now();
  _log('reconectando à nuvem e religando a escuta da fila');
  try {
    const { db, f } = _fs();
    if (f.disableNetwork && f.enableNetwork) { await _prazo(f.disableNetwork(db), 15000, 'desligar').catch(() => {}); await _prazo(f.enableNetwork(db), 15000, 'religar').catch(() => {}); }
    if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; }
    if (_escuta && _robo) _escuta();
  } catch (x) { _log(`reconexão: ${x.message || x}`); }
}
function desligarRobo() { if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; } if (_vigia) { clearInterval(_vigia); _vigia = null; } _robo = null; _escuta = null; _nFalha = 0; }

// promessa com prazo: chamada à nuvem que não responde não pode segurar a fila para sempre
function _prazo(pr, ms, oque) {
  let t;
  return Promise.race([pr, new Promise((_, nao) => { t = setTimeout(() => nao(new Error(`sem resposta da nuvem (${oque})`)), ms); })]).finally(() => clearTimeout(t));
}

let _avisoNaoRobo = 0;
async function _varrer() {
  if (!_robo) return;
  if (!_robo.souRobo()) {
    // 2.4.42: pedido parado na fila e este computador não é o robô → deixa registrado (antes ficava em silêncio)
    if (Date.now() - _avisoNaoRobo > 10 * 60 * 1000) {
      try {
        const { db, f } = _fs();
        const q = await _prazo(f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'novo'))), 30000, 'fila');
        const velhos = []; q.forEach((x) => { const d = x.data(); if (d.emMs && Date.now() - d.emMs > 3 * 60 * 1000) velhos.push(x.id); });
        if (velhos.length) {
          _avisoNaoRobo = Date.now();
          const ro = await _prazo(f.getDoc(f.doc(db, 'fechamento_sn', 'integra')), 30000, 'robô').catch(() => null);
          const d = ro && ro.exists() ? ro.data() : {};
          _log(`${velhos.length} pedido(s) parado(s) na fila, mas este computador não está como robô (robô atual: ${d.roboNome || '—'}${d.ativo ? '' : ', desativado'})`);
        }
      } catch (_) {}
    }
    return;
  }
  if (_rodando) {
    if (Date.now() - _rodandoDesde < 15 * 60 * 1000) return;
    _log('a fila estava presa havia 15 minutos; liberando');
    _geracao++; _rodando = false;
  }
  const { db, f } = _fs();
  const novos = [], presos = [];
  (await _prazo((f.getDocsFromServer || f.getDocs)(f.query(f.collection(db, COL_P), f.where('status', '==', 'novo'))), 30000, 'fila')).forEach((x) => { if (!_atendidos.has(x.id)) novos.push({ id: x.id, ...x.data() }); });
  (await _prazo(f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'rodando'))), 30000, 'fila')).forEach((x) => {
    const d = x.data();
    if (d.inicioMs && Date.now() - d.inicioMs > 20 * 60 * 1000) presos.push(x.ref);
  });
  for (const r of presos) await f.updateDoc(r, { status: 'erro', msg: 'Interrompido antes de terminar (o computador ou a conexão caiu). Peça de novo.', fimMs: Date.now() }).catch(() => {});
  if (novos.length) { novos.sort((a, b) => (a.emMs || 0) - (b.emMs || 0)); _fila(novos); }
  else _autoVarrer().catch((e) => _log(`automático: ${e.message || e}`));
}

// ------------------------------------------------------------------ envio automático (2.4.53)
// Cada empresa guarda em "auto" a etapa em que está: dctf (esperando a Receita montar a DCTFWeb) → transmitir → recibo →
// guia → feito (2.4.55: a guia só depois da DCTFWeb entregue). A varredura de 1 minuto anda uma etapa por vez, uma empresa por vez, sem prender a fila de pedidos.
let _autoRodando = false;
async function _autoVarrer() {
  if (!_robo || !_robo.souRobo() || _autoRodando || _rodando) return;
  _autoRodando = true;
  try {
    const { db, f } = _fs();
    const lista = [];
    (await _prazo(f.getDocs(f.query(f.collection(db, COL), f.where('auto.pendente', '==', true))), 30000, 'automático')).forEach((x) => lista.push({ ref: x.ref, d: x.data() }));
    lista.sort((a, b) => (a.d.auto.proxMs || 0) - (b.d.auto.proxMs || 0));
    for (const { ref, d } of lista) {
      if (_rodando || !_robo) break;                       // pedido da equipe chegou: ele vai primeiro
      if ((d.auto.proxMs || 0) > Date.now()) continue;
      await _autoPasso(ref, d).catch(async (e) => {
        _log(`automático ${d.nome}: ${e.message || e}`);
        const t = (d.auto.tent || 0) + 1;
        await f.setDoc(ref, _limpo({ auto: { ...d.auto, tent: t, proxMs: Date.now() + 2 * 60 * 1000, ...(t > 5 ? { pendente: false, etapa: 'erro', msg: String(e.message || e).slice(0, 200) } : {}) } }), { merge: true });
      });
    }
  } finally { _autoRodando = false; }
}

async function _autoPasso(ref, d) {
  const { db, f } = _fs();
  const a = d.auto, comp = d.comp, cnpj = d.cnpj, por = `${a.por || 'equipe'} (automático)`;
  const grava = async (o) => { await f.setDoc(ref, _limpo({ auto: { ...a, ...o, emEtapa: new Date().toISOString() } }), { merge: true }); try { D.notificar('mit:mudou', { comp }); } catch (_) {} };
  if (a.etapa === 'dctf') {
    const dctf = await _lerDctf(comp, cnpj);
    if (!dctf || !['em_andamento', 'transmitida'].includes(dctf.situacao)) {
      const t = (a.tent || 0) + 1;
      if (t >= 15) { _log(`automático ${d.nome}: a DCTFWeb não apareceu na Receita em 15 minutos`); return grava({ pendente: false, etapa: 'erro', msg: 'a DCTFWeb não apareceu na Receita em 15 minutos — gere a guia e transmita pelos botões' }); }
      return grava({ tent: t, proxMs: Date.now() + 60 * 1000, msg: 'aguardando a DCTFWeb na Receita' });
    }
    await f.setDoc(ref, _limpo({ dctf: { ...(d.dctf || {}), ...dctf } }), { merge: true });
    if (dctf.situacao === 'transmitida') return grava({ etapa: 'recibo', tent: 0, proxMs: Date.now(), msg: 'baixando o recibo' });
    return grava({ etapa: 'transmitir', tent: 0, proxMs: Date.now(), msg: 'transmitindo a DCTFWeb' });
  }
  if (a.etapa === 'guia') {
    if (d.mit && d.mit.semMovimento) return grava({ pendente: false, etapa: 'feito', msg: '' });      // sem débito: não tem guia
    const enviadoEm = Date.parse((d.mit && d.mit.enviadoEm) || '') || 0;
    const temGuia = (d.guias || []).some((g) => Date.parse(g.em || '') >= enviadoEm);
    if (!temGuia) {
      const r = await _guia({ comp, cnpjs: [cnpj], por });
      _log(`automático ${d.nome}: guia · ${r.msg || r.status}`);
      if (r.status !== 'feito' || /com problema/.test(r.msg || '')) throw new Error(`guia: ${r.msg || 'falha'}`);
    }
    return grava({ pendente: false, etapa: 'feito', msg: '' });
  }
  if (a.etapa === 'transmitir') {
    const { d: atual } = await _doc(comp, cnpj);
    const dc = (atual && atual.dctf) || {};
    if (dc.situacao === 'transmitida' && dc.recibo) return grava({ etapa: dc.arquivo ? 'guia' : 'recibo', tent: 0, proxMs: Date.now(), msg: dc.arquivo ? 'gerando a guia' : 'baixando o recibo' });
    let semFolha = !!(atual && atual.semFolha);
    try { const e = await f.getDoc(f.doc(db, COL_E, cnpj)); if (e.exists() && e.data().semFolha !== undefined) semFolha = !!e.data().semFolha; } catch (_) {}
    if (dc.retificadora !== true && !semFolha) {
      _log(`automático ${d.nome}: DCTFWeb original — fica para a equipe confirmar a folha e transmitir (a guia sai depois)`);
      return grava({ pendente: false, etapa: 'confirmar', msg: 'DCTFWeb original: confirme a folha e a REINF e transmita — a guia do MIT sai sozinha depois' });
    }
    const r = await _transmitir({ comp, cnpjs: [cnpj], confirmado: { folha: true, reinf: true, mit: true }, por });
    _log(`automático ${d.nome}: transmissão · ${r.msg || r.status}`);
    if (r.status !== 'feito') return grava({ pendente: false, etapa: 'erro', msg: String(r.msg || 'a Receita não aceitou a transmissão').slice(0, 300) });
    const { d: dep } = await _doc(comp, cnpj);
    if (dep && dep.dctf && dep.dctf.arquivo) return grava({ etapa: 'guia', tent: 0, proxMs: Date.now(), msg: 'gerando a guia' });
    return grava({ etapa: 'recibo', tent: 0, proxMs: Date.now() + 60 * 1000, msg: 'baixando o recibo' });
  }
  if (a.etapa === 'recibo') {
    const { ref: r2, d: atual } = await _doc(comp, cnpj);
    const x = await _buscarRecibo(comp, cnpj, r2, atual);
    if (x.ok) return grava({ etapa: 'guia', tent: 0, proxMs: Date.now(), msg: 'gerando a guia' });
    // em andamento de novo (transmissão não concluída): não gera guia — volta para a equipe
    if (/em andamento/.test(x.msg || '')) return grava({ pendente: false, etapa: 'erro', msg: 'a Receita mostra a DCTFWeb ainda em andamento — transmita de novo; a guia não foi gerada' });
    const t = (a.tent || 0) + 1;
    if (t >= 6) return grava({ etapa: 'guia', tent: 0, proxMs: Date.now(), msg: 'gerando a guia (o recibo vem no próximo "Consultar")' });
    return grava({ tent: t, proxMs: Date.now() + 2 * 60 * 1000, msg: 'aguardando a Receita liberar o recibo' });
  }
  return grava({ pendente: false });
}

async function _fila(novos) {
  if (_rodando) return;                   // o laço abaixo pega os que chegarem enquanto roda
  _rodando = true; _rodandoDesde = Date.now();
  const g = ++_geracao;
  try {
    let lista = novos;
    while (lista.length && g === _geracao) {
      for (const p of lista) {
        if (_atendidos.has(p.id) || g !== _geracao) continue;
        _atendidos.add(p.id);
        _rodandoDesde = Date.now();
        await _atender(p).catch((e) => _log(`pedido ${p.id}: ${e.message || e}`));
      }
      // chegou mais alguma coisa enquanto atendia?
      const { db, f } = _fs();
      const mais = [];
      (await _prazo(f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'novo'))), 30000, 'fila')).forEach((x) => { if (!_atendidos.has(x.id)) mais.push({ id: x.id, ...x.data() }); });
      lista = mais.sort((a, b) => (a.emMs || 0) - (b.emMs || 0));
    }
  } catch (e) {
    _log(`fila: ${e.message || e} (a varredura tenta de novo em 1 minuto)`);
  } finally { if (g === _geracao) _rodando = false; }
}

async function _atender(p) {
  const { db, f } = _fs();
  const ref = f.doc(db, COL_P, p.id);
  const ok = await _prazo(f.runTransaction(db, async (tx) => {
    const s = await tx.get(ref);
    if (!s.exists() || s.data().status !== 'novo') return false;
    tx.update(ref, { status: 'rodando', roboNome: `${os.hostname()} · ${_quem()}`, inicioMs: Date.now() });
    return true;
  }), 60000, 'pegar o pedido').catch(() => null);     // 2.4.42: transação que não responde não prende a fila
  if (ok === null) { _atendidos.delete(p.id); _log(`pedido ${p.id}: sem resposta da nuvem ao pegar; tenta de novo na próxima varredura`); return; }
  if (!ok) return;
  _log(`===== pedido ${p.tipo} ${p.comp} (${(p.cnpjs || []).length} empresa(s)) · por ${p.por}`);
  let fim;
  try {
    fim = p.tipo === 'enviar' ? await _enviar(p) : p.tipo === 'guia' ? await _guia(p) : p.tipo === 'transmitir' ? await _transmitir(p)
      : p.tipo === 'recibo' ? await _recibo(p) : await _consultar(p);
  } catch (e) {
    fim = { status: 'erro', msg: String(e.message || e).slice(0, 300) };
  }
  _log(`pedido ${p.id}: ${fim.status} · ${fim.msg || ''}`);
  await _prazo(f.updateDoc(ref, _limpo({ ...fim, fimMs: Date.now() })), 30000, 'gravar o pedido').catch((e) => _log(`pedido ${p.id}: ${e.message || e}`));
  try { D.notificar('mit:mudou', { comp: p.comp }); } catch (_) {}
}

async function _doc(comp, cnpj) {
  const { db, f } = _fs();
  const ref = f.doc(db, COL, `${comp}_${cnpj}`);
  const s = await f.getDoc(ref);
  return { ref, d: s.exists() ? s.data() : null };
}
const _consumo = async (r) => { if (_robo.consumo) await _robo.consumo(r.consumo || {}).catch(() => {}); };

// DCTFWeb do mês depois do MIT (situação, débitos por origem) — guardada no documento do MIT
let _indVisto = false;
async function _lerDctf(comp, cnpj) {
  const r = await _robo.python({ acao: 'dctf_conferir', comp, empresas: [{ cnpj }] });
  if (!r.ok) return null;
  await _consumo(r);
  const x = (r.resultados || [])[0] || {};
  if (x.indRetif && !_indVisto) { _indVisto = true; _log(`DCTFWeb ${comp} ${cnpj}: indRetificacao = "${x.indRetif}" → ${x.retificadora === true ? 'retificadora' : x.retificadora === false ? 'original' : 'não reconhecido'}`); }
  return _limpo({ situacao: x.situacao || '', msg: x.msg || '', retificadora: x.retificadora ?? null, origens: x.origens || {}, outros: x.outros || {}, reinf: x.reinf || {},
    esperadoTudo: _tudo(x), xmlHash: x.xmlHash || '', msgReceita: x.msgReceita || '', lidaEm: new Date().toISOString() });
}

async function _consultar(p) {
  const { f } = _fs();
  const r = await _robo.python({ acao: 'mit_consultar', comp: p.comp, empresas: (p.cnpjs || []).map((cnpj) => ({ cnpj })) });
  if (!r.ok) throw new Error(r.erro || 'Falha na consulta do MIT.');
  await _consumo(r);
  let n = 0, nr = 0;
  for (const x of r.resultados || []) {
    const { ref, d } = await _doc(p.comp, _so(x.cnpj)); if (!d) continue;
    if (!x.ok) { await f.setDoc(ref, _limpo({ ultimoErro: x.msg || 'falha', ultimoErroEm: new Date().toISOString() }), { merge: true }); continue; }
    const u = x.ultima;
    const mit = u ? { ...(d.mit || {}), id: u.id, situacao: u.situacao, texto: u.texto, data: u.data, valor: u.valor, consultadoEm: new Date().toISOString() } : (d.mit || null);
    await f.setDoc(ref, _limpo({ mit, ultimoErro: '' }), { merge: true });
    n++;
    if (mit && mit.situacao === 3 && !(d.dctf && d.dctf.arquivo)) {
      try { if ((await _buscarRecibo(p.comp, _so(x.cnpj), ref, { ...d, mit })).ok) nr++; } catch (e) { _log(`${d.nome}: recibo da DCTFWeb: ${e.message || e}`); }
    }
  }
  return { status: 'feito', msg: `${n} empresa(s) consultada(s) na Receita${nr ? ` · ${nr} recibo(s) da DCTFWeb baixado(s)` : ''}` };
}

async function _enviar(p) {
  const { f } = _fs();
  const ok = [], erros = [];
  for (const cnpj of p.cnpjs || []) {
    const { ref, d } = await _doc(p.comp, cnpj);
    if (!d) { erros.push(`${cnpj}: não importada`); continue; }
    const sem = !!p.semMovimento || (p.semMov || []).includes(cnpj);
    const empresa = { cnpj, nome: d.nome, dados: { comp: d.comp, regime: d.regime, pis: d.pis || [], cofins: d.cofins || [] }, tributacao: d.tributacao, balanco: !!d.balanco, extras: d.extras || [] };
    // 2.4.57: sem débito vai sempre (mesmo com débitos da folha/REINF na DCTFWeb); a DCTFWeb é transmitida depois
    const r = await _robo.python({ acao: 'mit_enviar', comp: p.comp, empresa, semMovimento: sem, forcarSem: sem });
    if (!r.ok) throw new Error(r.erro || 'Falha no envio do MIT.');
    await _consumo(r);
    const x = r.resultado || {};
    if (x.dispensado) {
      // sem débito de PIS/COFINS e a DCTFWeb do mês já tem débitos da folha/REINF: o MIT sem movimento não é obrigatório
      // (Manual do MIT, item 8.2) e não muda nada — fica registrado como "não precisa", sem erro
      await f.setDoc(ref, _limpo({ mitDispensado: { em: new Date().toISOString(), por: p.por || '', motivo: x.msg || '' }, ultimoErro: '' }), { merge: true });
      ok.push(`${d.nome} (MIT não precisa)`);
      _log(`MIT ${d.nome}: não precisa — ${x.msg || ''}`);
      continue;
    }
    if (!x.ok && !x.jaEnviado) {
      await f.setDoc(ref, _limpo({ ultimoErro: x.msg || 'falha', ultimoErroEm: new Date().toISOString() }), { merge: true });
      erros.push(`${d.nome}: ${x.msg || 'falha'}`); continue;
    }
    const mit = { id: x.idApuracao || null, situacao: x.situacao || 3, texto: x.texto || '', data: x.dataEncerramento || '', avisos: x.avisos || [],
      protocolo: x.protocolo || '', semMovimento: sem, enviadoPor: p.por || '', enviadoEm: new Date().toISOString(), jaEnviado: !!x.jaEnviado,
      valor: _r2((d.total || 0) + _totalExtras(d.extras)) };
    const dctf = await _lerDctf(p.comp, cnpj).catch(() => null);
    const auto = p.auto && (sem || situacaoDe(d) === 'a_enviar') ? { pendente: true, etapa: 'dctf', tent: 0, proxMs: Date.now() + 15000, desde: new Date().toISOString(), por: p.por || '', msg: 'aguardando a DCTFWeb na Receita' } : null;
    await f.setDoc(ref, _limpo({ mit, ...(dctf ? { dctf } : {}), ...(auto ? { auto } : {}), ultimoErro: '', mudouDepoisDoEnvio: false, mitDispensado: null }), { merge: true });
    ok.push(d.nome);
    _log(`MIT ${sem ? 'sem movimento ' : ''}${d.nome}: ${x.msg || ''}`);
  }
  if (p.auto && ok.length) setTimeout(() => _autoVarrer().catch((e) => _log(`automático: ${e.message || e}`)), 20000);
  if (!ok.length && erros.length) return { status: 'erro', msg: erros.join(' · ').slice(0, 400) };
  return { status: 'feito', msg: `${ok.length} MIT enviado(s)${p.auto ? ' · guia e DCTFWeb seguem no automático' : ''}${erros.length ? ` · ${erros.length} com problema: ${erros.join(' · ')}` : ''}`.slice(0, 400) };
}

// guia só dos débitos do MIT (origem 8); a Receita calcula vencimento e acréscimos; o PDF vai para a pasta do cliente
async function _guia(p) {
  const { f } = _fs();
  const ok = [], erros = [];
  for (const cnpj of p.cnpjs || []) {
    const { ref, d } = await _doc(p.comp, cnpj);
    if (!d) { erros.push(`${cnpj}: não importada`); continue; }
    const dctf = await _lerDctf(p.comp, cnpj);
    if (!dctf || !['em_andamento', 'transmitida'].includes(dctf.situacao)) { erros.push(`${d.nome}: a DCTFWeb do mês ainda não está disponível (${(dctf && (dctf.msg || dctf.situacao)) || 'sem resposta'})`); continue; }
    // 2.4.53: a guia vai para a pasta da competência (10/2026), não a do mês do vencimento
    // 2.4.57: dentro de Sped - Contribuições\AAAA\mês (junto da EFD-Contribuições), não em Relatórios
    const [a, m] = p.comp.split('-');
    const pasta = pastaCliente.pastaContribDoMes({ nome: d.nome, cnpj }, a, m, true) || '';
    const r = await _robo.python({ acao: 'dctf_guia', comp: p.comp, empresa: { cnpj, nome: d.nome, situacao: dctf.situacao, origens: ['MIT'], data: p.data ? p.data.replace(/-/g, '') : '', pasta, rotulo: 'MIT PIS-COFINS' } });
    if (!r.ok) throw new Error(r.erro || 'Falha ao gerar a guia.');
    await _consumo(r);
    const x = r.resultado || {};
    if (!x.ok) { erros.push(`${d.nome}: ${x.msg || 'falha'}`); continue; }
    const guias = (d.guias || []).slice(-9);
    guias.push({ arquivo: x.arquivo || '', aviso: x.aviso || '', emAndamento: !!x.emAndamento, data: p.data || '', em: new Date().toISOString(), por: p.por || '' });
    await f.setDoc(ref, _limpo({ guias, dctf }), { merge: true });
    ok.push(d.nome);
  }
  if (!ok.length && erros.length) return { status: 'erro', msg: erros.join(' · ').slice(0, 400) };
  return { status: 'feito', msg: `${ok.length} guia(s) gerada(s)${erros.length ? ` · ${erros.length} com problema: ${erros.join(' · ')}` : ''}`.slice(0, 400) };
}

// transmissão da DCTFWeb: lê de novo na hora e transmite o que a Receita tem agora (folha, REINF e MIT já confirmados)
async function _transmitir(p) {
  const { f } = _fs();
  const cnpj = (p.cnpjs || [])[0];
  const { ref, d } = await _doc(p.comp, cnpj);
  if (!d) return { status: 'erro', msg: 'Empresa não importada.' };
  if (!p.confirmado || !p.confirmado.folha || !p.confirmado.reinf || !p.confirmado.mit) return { status: 'erro', msg: 'Faltou a confirmação da folha, da REINF e do MIT.' };
  const sit = situacaoDe(d);
  if (!['enviado', 'saldo_credor', 'sem_movimento', 'dispensado'].includes(sit)) return { status: 'erro', msg: 'Envie o MIT antes de transmitir a DCTFWeb.' };
  // 2.4.41: transmitida pelo sistema nas últimas 24 h → não transmite de novo (cada nova transmissão vira outra retificadora)
  // (2.4.43: só com recibo — as "transmitidas" sem recibo de antes desta versão podem não ter sido aceitas pela Receita)
  const jaEm = d.dctf && d.dctf.transmitidaEm && d.dctf.recibo && Date.now() - Date.parse(d.dctf.transmitidaEm) < 24 * 3600 * 1000 ? d.dctf.transmitidaEm : '';
  if (jaEm) return { status: 'erro', msg: `${d.nome}: a DCTFWeb já foi transmitida pelo sistema em ${new Date(jaEm).toLocaleString('pt-BR')} — não transmito de novo. O recibo vem pelo "Consultar"; se precisar de outra retificadora, faça pelo e-CAC.` };
  let dctf = await _lerDctf(p.comp, cnpj);
  if (dctf) _log(`${d.nome}: situação antes de transmitir = ${dctf.situacao}${dctf.retificadora ? ' (retificadora)' : ''} · Receita: "${dctf.msgReceita || ''}"`);
  if (!dctf || dctf.situacao !== 'em_andamento') {
    if (dctf && dctf.situacao === 'transmitida') { await f.setDoc(ref, _limpo({ dctf }), { merge: true }); return { status: 'feito', msg: 'A DCTFWeb já estava transmitida.' }; }
    return { status: 'erro', msg: `A DCTFWeb não está em andamento (${(dctf && (dctf.msg || dctf.situacao)) || 'sem resposta'}).` };
  }
  const [a, m] = p.comp.split('-');
  const pasta = pastaCliente.pastaContribDoMes({ nome: d.nome, cnpj }, a, m, true) || '';
  const envia = async (lida) => {
    const r = await _robo.python({ acao: 'dctf_transmitir', comp: p.comp, empresa: { cnpj, nome: d.nome, esperado: lida.reinf || {}, esperadoTudo: lida.esperadoTudo || {}, esperadoHash: lida.xmlHash || '', pasta, semMovimento: sit === 'sem_movimento' } });
    if (!r.ok) throw new Error(r.erro || 'Falha na transmissão.');
    await _consumo(r);
    return r.resultado || {};
  };
  let x = await envia(dctf);
  // 2.4.34: a Receita ainda estava juntando os débitos (comum logo depois do MIT, sobretudo quando a folha já tinha
  // transmitido e a DCTFWeb virou retificadora). Registra o que mudou, espera, lê de novo e tenta uma vez só.
  if (!x.ok && Array.isArray(x.diferencas)) {
    _log(`${d.nome}: débitos mudaram entre as leituras → ${x.diferencas.map((y) => `${y.cod}: ${y.visto} → ${y.agora}`).join(' · ') || 'nenhum débito reconhecido no XML'}`);
    if (Array.isArray(x.arvore)) _log(`leiaute do XML (só nomes das tags): ${x.arvore.join(' | ').slice(0, 3000)}`);
    await new Promise((ok) => setTimeout(ok, 20000));
    const nova = await _lerDctf(p.comp, cnpj);
    if (nova && nova.situacao === 'em_andamento') { dctf = nova; x = await envia(nova); }
    if (!x.ok && Array.isArray(x.diferencas)) _log(`${d.nome}: ainda mudando → ${x.diferencas.map((y) => `${y.cod}: ${y.visto} → ${y.agora}`).join(' · ')}`);
  }
  if (x.msgReceita) _log(`${d.nome}: resposta da transmissão · Receita: "${x.msgReceita}"`);
  if (!x.ok) {
    await f.setDoc(ref, _limpo({ ultimoErro: x.msg || 'falha', ultimoErroEm: new Date().toISOString() }), { merge: true });
    return { status: 'erro', msg: x.msg || 'A Receita não aceitou a transmissão.' };
  }
  await f.setDoc(ref, _limpo({ dctf: { ...dctf, situacao: 'transmitida', recibo: x.recibo || '', arquivo: x.arquivo || '', transmitidaEm: new Date().toISOString(), transmitidaPor: p.por || '' }, ultimoErro: '' }), { merge: true });
  // 2.4.55: o automático tinha parado esperando a confirmação (original) → depois da transmissão, segue com recibo e guia
  if (d.auto && !d.auto.pendente && ['confirmar', 'erro'].includes(d.auto.etapa) && situacaoDe(d) === 'enviado') {
    await f.setDoc(ref, _limpo({ auto: { ...d.auto, pendente: true, etapa: x.arquivo ? 'guia' : 'recibo', tent: 0, proxMs: Date.now() + 20000, msg: x.arquivo ? 'gerando a guia' : 'baixando o recibo' } }), { merge: true });
    setTimeout(() => _autoVarrer().catch((e) => _log(`automático: ${e.message || e}`)), 25000);
  }
  return { status: 'feito', msg: `${d.nome}: ${x.jaTransmitida ? 'a DCTFWeb já estava transmitida' : `DCTFWeb${dctf.retificadora ? ' retificadora' : ''} transmitida${x.recibo ? ` · recibo ${x.recibo}` : ' · o recibo vem no próximo "Consultar"'}`}` };
}

// recibo da DCTFWeb já transmitida (a Receita não tinha liberado na hora, ou foi transmitida por fora do sistema)
// 2.4.38: situação atual da DCTFWeb e, se já transmitida (pelo sistema ou por fora, original ou retificadora),
// o recibo da que está valendo — a Receita devolve o recibo da última transmitida do período
async function _buscarRecibo(comp, cnpj, ref, d) {
  const { f } = _fs();
  const lida = await _lerDctf(comp, cnpj).catch(() => null);
  if (lida) _log(`${d.nome}: situação = ${lida.situacao}${lida.retificadora ? ' (retificadora)' : ''} · Receita: "${lida.msgReceita || ''}"`);
  // 2.4.43: em andamento na Receita = não transmitida, mesmo que o sistema tenha registrado "transmitida" antes
  // (o recibo do período seria o da original, não o desta retificadora)
  const peloSistema = d.dctf && d.dctf.situacao === 'transmitida' && d.dctf.transmitidaEm;
  if (lida && lida.situacao === 'em_andamento') {
    const dctf = { ...(d.dctf || {}), ...lida, situacao: 'em_andamento', recibo: '', arquivo: '', transmitidaEm: '' };
    await f.setDoc(ref, _limpo({ dctf }), { merge: true });
    if (peloSistema) _log(`${d.nome}: estava marcada como transmitida, mas a Receita mostra em andamento — corrigido para "falta transmitir"`);
    return { ok: false, msg: peloSistema ? 'a Receita mostra a DCTFWeb ainda em andamento — a transmissão anterior não foi concluída; transmita de novo' : 'a DCTFWeb do mês está em andamento — falta transmitir' };
  }
  const [a, m] = comp.split('-');
  const pasta = pastaCliente.pastaContribDoMes({ nome: d.nome, cnpj }, a, m, true) || '';
  const r = await _robo.python({ acao: 'dctf_recibo', comp, empresa: { cnpj, nome: d.nome, pasta, retificadora: !!((lida && lida.retificadora) || (d.dctf && d.dctf.retificadora)) } });
  if (!r.ok) throw new Error(r.erro || 'Falha ao buscar o recibo.');
  await _consumo(r);
  const x = r.resultado || {};
  if (x.msgReceita) _log(`${d.nome}: recibo · Receita: "${x.msgReceita}"`);
  if (!x.ok) return { ok: false, msg: /dispon|transmit|n[aã]o encontr/i.test(x.msg || '') ? 'a DCTFWeb do mês ainda não está transmitida (ou o recibo não foi liberado)' : (x.msg || 'falha') };
  await f.setDoc(ref, _limpo({ dctf: { ...(d.dctf || {}), ...(lida || {}), situacao: 'transmitida', recibo: x.recibo || '', arquivo: x.arquivo || '', reciboAviso: x.aviso || '', reciboEm: new Date().toISOString() } }), { merge: true });
  return { ok: true };
}

async function _recibo(p) {
  const ok = [], erros = [];
  for (const cnpj of p.cnpjs || []) {
    const { ref, d } = await _doc(p.comp, cnpj);
    if (!d) { erros.push(`${cnpj}: não importada`); continue; }
    const x = await _buscarRecibo(p.comp, cnpj, ref, d);
    if (x.ok) ok.push(d.nome); else erros.push(`${d.nome}: ${x.msg}`);
  }
  // DCTFWeb ainda em andamento não é erro: só não há recibo para baixar ainda
  if (!ok.length && erros.length) return { status: erros.every((x) => /em andamento|ainda não liberou|ainda não devolveu/.test(x)) ? 'aviso' : 'erro', msg: erros.join(' · ').slice(0, 400) };
  return { status: 'feito', msg: `${ok.length} recibo(s) baixado(s)${erros.length ? ` · ${erros.length} sem recibo: ${erros.join(' · ')}` : ''}`.slice(0, 400) };
}

// Admin: apaga o histórico de pedidos da competência (e os avisos de erro das empresas)
async function limparHistorico(comp) {
  const s = auth.sessao();
  if (!s || s.perfil !== 'admin') throw new Error('Só o Admin limpa o histórico.');
  if (!_comp(comp)) throw new Error('Competência inválida.');
  const { db, f } = _fs();
  let n = 0;
  for (const x of (await f.getDocs(f.query(f.collection(db, COL_P), f.where('comp', '==', comp)))).docs) {
    if (['novo', 'rodando'].includes(x.data().status)) continue;              // o que está na fila continua
    await f.deleteDoc(x.ref); n++;
  }
  for (const x of (await f.getDocs(f.query(f.collection(db, COL), f.where('comp', '==', comp)))).docs) {
    if (x.data().ultimoErro) await f.setDoc(x.ref, { ultimoErro: '', ultimoErroEm: '' }, { merge: true });
  }
  return { apagados: n };
}
// 2.4.27 (uma vez, no computador do robô): apaga os pedidos que deram erro na 2.4.26 (procuração no CPF) e os avisos
async function limparErrosAntigos() {
  const marca = path.join(D.userData(), 'mit_limpeza_2427.txt');
  if (fs.existsSync(marca)) return;
  const { db, f } = _fs();
  for (const x of (await f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'erro')))).docs) await f.deleteDoc(x.ref).catch(() => {});
  for (const x of (await f.getDocs(f.collection(db, COL))).docs) {
    if (x.data().ultimoErro) await f.setDoc(x.ref, { ultimoErro: '', ultimoErroEm: '' }, { merge: true }).catch(() => {});
  }
  fs.writeFileSync(marca, new Date().toISOString());
}

module.exports = { init, podeUsar, dados, importar, salvarEmpresa, pedir, configAuto, limparHistorico, limparErrosAntigos, ligarRobo, desligarRobo, situacaoDe };
