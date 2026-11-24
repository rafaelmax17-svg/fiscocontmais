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
  docs.sort((a, b) => String(a.nome || '').localeCompare(String(b.nome || '')));
  return { comp, docs, pedidos: pedidos.slice(0, 30), robo: await _estadoRobo(), resp };
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
    let trib = 0, bal = false;
    try { const t = await f.getDoc(f.doc(db, COL_E, e.cnpj)); trib = t.exists() ? (t.data().tributacao || 0) : 0; bal = t.exists() ? !!t.data().balanco : false; } catch (_) {}
    const valores = JSON.stringify([e.pis, e.cofins]);
    const mudou = !!(ant && ant.mit && ant.mit.situacao === 3 && ant.valoresAssinatura && ant.valoresAssinatura !== valores);
    await f.setDoc(ref, _limpo({
      comp: e.comp, cnpj: e.cnpj, nome: e.nome, arquivo: path.basename(e.arquivo || ''), regime: e.regime, retificadora: !!e.retificadora,
      pis: e.pis, cofins: e.cofins, total: e.total, saldoPis: e.saldo_pis, saldoCofins: e.saldo_cofins,
      tributacao: (ant && ant.tributacao) || trib || e.tributacao_sugerida || 1, balanco: ant && ant.balanco !== undefined ? !!ant.balanco : bal, extras: (ant && ant.extras) || [],
      valoresAssinatura: valores, mudouDepoisDoEnvio: mudou, importadoPor: _quem(), importadoEm: new Date().toISOString(),
    }), { merge: true });
    ok.push(e.nome);
  }
  return { importadas: ok.length, erros, comps: [...comps].sort(), codigos: r.codigos_irpj_csll || {} };
}

async function salvarEmpresa({ comp, cnpj, tributacao, extras, balanco } = {}) {
  if (!podeUsar()) throw new Error('Sem acesso ao módulo MIT.');
  cnpj = _so(cnpj);
  if (!_comp(comp) || cnpj.length !== 14) throw new Error('Empresa inválida.');
  const { db, f } = _fs();
  const ref = f.doc(db, COL, `${comp}_${cnpj}`);
  const s = await f.getDoc(ref);
  if (!s.exists()) throw new Error('Empresa não importada nesta competência.');
  if ((s.data().mit || {}).situacao === 3) throw new Error('O MIT desta empresa já foi enviado.');
  const campos = {};
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
    for (const c of lista) {
      const s = await f.getDoc(f.doc(db, COL, `${comp}_${c}`)); const d = s.exists() ? s.data() : null;
      if (!d) throw new Error('Empresa não importada.');
      const sit = situacaoDe(d);
      if (['enviado', 'sem_movimento', 'em_curso'].includes(sit)) throw new Error(`${d.nome}: o MIT já foi enviado.`);
      if (semMovimento ? sit !== 'saldo_credor' : sit !== 'a_enviar') throw new Error(`${d.nome}: ${semMovimento ? 'o sem movimento só vale para empresa sem débito' : 'sem débito a declarar (saldo credor)'}.`);
    }
    if (semMovimento) { if (lista.length !== 1) throw new Error('O sem movimento é enviado uma empresa por vez.'); extra.semMovimento = true; }
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
  escuta();
  // varredura de segurança a cada minuto: pega pedido parado na fila e destrava a fila presa
  _vigia = setInterval(() => _varrer().catch(() => {}), 60 * 1000);
}
function desligarRobo() { if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; } if (_vigia) { clearInterval(_vigia); _vigia = null; } _robo = null; }

// promessa com prazo: chamada à nuvem que não responde não pode segurar a fila para sempre
function _prazo(pr, ms, oque) {
  let t;
  return Promise.race([pr, new Promise((_, nao) => { t = setTimeout(() => nao(new Error(`sem resposta da nuvem (${oque})`)), ms); })]).finally(() => clearTimeout(t));
}

async function _varrer() {
  if (!_robo || !_robo.souRobo()) return;
  if (_rodando) {
    if (Date.now() - _rodandoDesde < 15 * 60 * 1000) return;
    _log('a fila estava presa havia 15 minutos; liberando');
    _geracao++; _rodando = false;
  }
  const { db, f } = _fs();
  const novos = [], presos = [];
  (await _prazo(f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'novo'))), 30000, 'fila')).forEach((x) => { if (!_atendidos.has(x.id)) novos.push({ id: x.id, ...x.data() }); });
  (await _prazo(f.getDocs(f.query(f.collection(db, COL_P), f.where('status', '==', 'rodando'))), 30000, 'fila')).forEach((x) => {
    const d = x.data();
    if (d.inicioMs && Date.now() - d.inicioMs > 20 * 60 * 1000) presos.push(x.ref);
  });
  for (const r of presos) await f.updateDoc(r, { status: 'erro', msg: 'Interrompido antes de terminar (o computador ou a conexão caiu). Peça de novo.', fimMs: Date.now() }).catch(() => {});
  if (novos.length) { novos.sort((a, b) => (a.emMs || 0) - (b.emMs || 0)); _fila(novos); }
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
  const ok = await f.runTransaction(db, async (tx) => {
    const s = await tx.get(ref);
    if (!s.exists() || s.data().status !== 'novo') return false;
    tx.update(ref, { status: 'rodando', roboNome: `${os.hostname()} · ${_quem()}`, inicioMs: Date.now() });
    return true;
  }).catch(() => null);
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
    esperadoTudo: _tudo(x), xmlHash: x.xmlHash || '', lidaEm: new Date().toISOString() });
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
    const sem = !!p.semMovimento;
    const empresa = { cnpj, nome: d.nome, dados: { comp: d.comp, regime: d.regime, pis: d.pis || [], cofins: d.cofins || [] }, tributacao: d.tributacao, balanco: !!d.balanco, extras: d.extras || [] };
    const r = await _robo.python({ acao: 'mit_enviar', comp: p.comp, empresa, semMovimento: sem });
    if (!r.ok) throw new Error(r.erro || 'Falha no envio do MIT.');
    await _consumo(r);
    const x = r.resultado || {};
    if (!x.ok && !x.jaEnviado) {
      await f.setDoc(ref, _limpo({ ultimoErro: x.msg || 'falha', ultimoErroEm: new Date().toISOString() }), { merge: true });
      erros.push(`${d.nome}: ${x.msg || 'falha'}`); continue;
    }
    const mit = { id: x.idApuracao || null, situacao: x.situacao || 3, texto: x.texto || '', data: x.dataEncerramento || '', avisos: x.avisos || [],
      protocolo: x.protocolo || '', semMovimento: sem, enviadoPor: p.por || '', enviadoEm: new Date().toISOString(), jaEnviado: !!x.jaEnviado,
      valor: _r2((d.total || 0) + _totalExtras(d.extras)) };
    const dctf = await _lerDctf(p.comp, cnpj).catch(() => null);
    await f.setDoc(ref, _limpo({ mit, ...(dctf ? { dctf } : {}), ultimoErro: '', mudouDepoisDoEnvio: false }), { merge: true });
    ok.push(d.nome);
    _log(`MIT ${sem ? 'sem movimento ' : ''}${d.nome}: ${x.msg || ''}`);
  }
  if (!ok.length && erros.length) return { status: 'erro', msg: erros.join(' · ').slice(0, 400) };
  return { status: 'feito', msg: `${ok.length} MIT enviado(s)${erros.length ? ` · ${erros.length} com problema: ${erros.join(' · ')}` : ''}`.slice(0, 400) };
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
    const [a, m] = p.comp.split('-');
    const mp = +m === 12 ? [String(+a + 1), '01'] : [a, String(+m + 1).padStart(2, '0')];
    const pasta = pastaCliente.pastaDoMes({ nome: d.nome, cnpj }, mp[0], mp[1], true) || '';
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
  if (!['enviado', 'saldo_credor', 'sem_movimento'].includes(sit)) return { status: 'erro', msg: 'Envie o MIT antes de transmitir a DCTFWeb.' };
  let dctf = await _lerDctf(p.comp, cnpj);
  if (!dctf || dctf.situacao !== 'em_andamento') {
    if (dctf && dctf.situacao === 'transmitida') { await f.setDoc(ref, _limpo({ dctf }), { merge: true }); return { status: 'feito', msg: 'A DCTFWeb já estava transmitida.' }; }
    return { status: 'erro', msg: `A DCTFWeb não está em andamento (${(dctf && (dctf.msg || dctf.situacao)) || 'sem resposta'}).` };
  }
  const [a, m] = p.comp.split('-');
  const pasta = pastaCliente.pastaDoMes({ nome: d.nome, cnpj }, a, m, true) || '';
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
  if (!x.ok) {
    await f.setDoc(ref, _limpo({ ultimoErro: x.msg || 'falha', ultimoErroEm: new Date().toISOString() }), { merge: true });
    return { status: 'erro', msg: x.msg || 'A Receita não aceitou a transmissão.' };
  }
  await f.setDoc(ref, _limpo({ dctf: { ...dctf, situacao: 'transmitida', recibo: x.recibo || '', arquivo: x.arquivo || '', transmitidaEm: new Date().toISOString(), transmitidaPor: p.por || '' }, ultimoErro: '' }), { merge: true });
  return { status: 'feito', msg: `${d.nome}: ${x.jaTransmitida ? 'a DCTFWeb já estava transmitida' : `DCTFWeb${dctf.retificadora ? ' retificadora' : ''} transmitida${x.recibo ? ` · recibo ${x.recibo}` : ' · o recibo vem no próximo "Consultar"'}`}` };
}

// recibo da DCTFWeb já transmitida (a Receita não tinha liberado na hora, ou foi transmitida por fora do sistema)
// 2.4.38: situação atual da DCTFWeb e, se já transmitida (pelo sistema ou por fora, original ou retificadora),
// o recibo da que está valendo — a Receita devolve o recibo da última transmitida do período
async function _buscarRecibo(comp, cnpj, ref, d) {
  const { f } = _fs();
  const lida = await _lerDctf(comp, cnpj).catch(() => null);
  if (lida && lida.situacao === 'em_andamento') {
    await f.setDoc(ref, _limpo({ dctf: { ...(d.dctf || {}), ...lida } }), { merge: true });
    return { ok: false, msg: 'a DCTFWeb do mês está em andamento — falta transmitir' };
  }
  const [a, m] = comp.split('-');
  const pasta = pastaCliente.pastaDoMes({ nome: d.nome, cnpj }, a, m, true) || '';
  const r = await _robo.python({ acao: 'dctf_recibo', comp, empresa: { cnpj, nome: d.nome, pasta, retificadora: !!((lida && lida.retificadora) || (d.dctf && d.dctf.retificadora)) } });
  if (!r.ok) throw new Error(r.erro || 'Falha ao buscar o recibo.');
  await _consumo(r);
  const x = r.resultado || {};
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
  if (!ok.length && erros.length) return { status: erros.every((x) => /em andamento/.test(x)) ? 'aviso' : 'erro', msg: erros.join(' · ').slice(0, 400) };
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

module.exports = { init, podeUsar, dados, importar, salvarEmpresa, pedir, limparHistorico, limparErrosAntigos, ligarRobo, desligarRobo, situacaoDe };
