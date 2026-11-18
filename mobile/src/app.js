// FiscoCont+ para Android — equipe e gestores (pedido do Rafael, 17/11/2026).
// Só leitura do que o sistema já guarda na nuvem (Firestore do projeto fiscocontmais), com o MESMO login e as MESMAS
// regras do computador: usuário ativo, perfil e módulos liberados. O processamento pesado (SPED, conferências, DARE,
// baixa de notas) continua no computador.
//   • Início: DAREs a vencer, Fisconforme, fechamento do Simples e certificados, com a lista de alertas.
//   • Empresas: débitos em aberto na SEFIN, Fisconforme, Simples, certificado e os números do SPED de cada mês.
//   • Consultas: CNPJ (dados públicos da Receita, BrasilAPI) e débitos na SEFIN.
//   • Ajuda tributária: a mesma função chatIA do sistema — o texto vai SEM CNPJ, CPF, IE e nome de cliente.
// Regras de segurança mantidas: só funciona com internet (sem cache local dos dados); trava depois de 60 minutos sem
// uso e pede a senha; nenhuma senha ou chave fica no app.
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged, reauthenticateWithCredential, EmailAuthProvider, browserLocalPersistence, setPersistence } from 'firebase/auth';
import { getFirestore, doc, getDoc, getDocs, collection, query, where } from 'firebase/firestore';
import { getFunctions, httpsCallable } from 'firebase/functions';
import { App as CapApp } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { StatusBar } from '@capacitor/status-bar';

/* global __FIREBASE__, __VERSAO__ */
const VERSAO = __VERSAO__;
const fb = initializeApp(__FIREBASE__);
const auth = getAuth(fb);
const db = getFirestore(fb);
const fns = getFunctions(fb, 'southamerica-east1');
const TRAVA_MIN = 60;
const REL_API = 'https://api.github.com/repos/rafaelmax17-svg/fiscocontmais-releases/releases/tags/android';
const REL_APK = 'https://github.com/rafaelmax17-svg/fiscocontmais-releases/releases/download/android/FiscoContMais.apk';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const brl = (v) => 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const so = (s) => String(s || '').replace(/\D/g, '');
const docf = (d) => { d = so(d); return d.length === 14 ? d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : d.length === 11 ? d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4') : d; };
const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const hoje0 = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const dBr = (s) => { const m = String(s || '').match(/^(\d{2})\/(\d{2})\/(\d{4})/); return m ? new Date(+m[3], +m[2] - 1, +m[1]) : null; };
const dIso = (s) => { const m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; };
const fmtD = (d) => d ? `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}` : '';
const dias = (d) => Math.round((d - hoje0()) / 86400000);
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const compAnt = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };
const quando = (s) => { const d = new Date(s); if (isNaN(d)) return String(s || ''); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} às ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
const compBr = (c) => (c ? `${c.slice(5, 7)}/${c.slice(0, 4)}` : '');

const S = { user: null, perfil: null, dados: null, carregadoEm: 0, aba: 'inicio', pilha: [], chat: [], ultimoUso: Date.now(), novaVersao: null };

// ------------------------------------------------------------------ telas
function mostra(id) { for (const t of ['#telaLogin', '#telaTrava', '#telaApp']) $(t).hidden = t !== id; }
function topo(tit, sub, volta) { $('#hTit').textContent = tit; $('#hSub').textContent = sub || ''; $('#hVolta').hidden = !volta; }
function aviso(html, acao) {
  const a = $('#aviso');
  if (!html) { a.hidden = true; return; }
  a.innerHTML = `<span>${html}</span>${acao ? `<button>${esc(acao.t)}</button>` : ''}`;
  a.hidden = false;
  if (acao) a.querySelector('button').onclick = acao.f;
}
const C = () => $('#conteudo');
function carregando(t) { C().innerHTML = `<div class="carregando">${esc(t || 'Carregando…')}</div>`; }

// ------------------------------------------------------------------ entrar / sair / travar
$('#lVer').textContent = `versão ${VERSAO}`;
$('#fVer').textContent = `FiscoCont+ Android · versão ${VERSAO}`;
try { const e = localStorage.getItem('fc_email'); if (e) $('#lEmail').value = e; } catch (_) {}
setPersistence(auth, browserLocalPersistence).catch(() => {});

function erroLogin(e) {
  const c = (e && e.code) || '';
  if (/invalid-credential|wrong-password|user-not-found|invalid-email/.test(c)) return 'E-mail ou senha incorretos.';
  if (/too-many-requests/.test(c)) return 'Muitas tentativas. Espere alguns minutos e tente de novo.';
  if (/network/.test(c)) return 'Sem internet. O FiscoCont+ só funciona conectado.';
  return (e && e.message) || 'Não foi possível entrar.';
}
$('#fLogin').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const b = $('#lBtn'); b.disabled = true; b.textContent = 'Entrando…'; $('#lErro').hidden = true;
  try {
    const email = $('#lEmail').value.trim().toLowerCase();
    await signInWithEmailAndPassword(auth, email, $('#lSenha').value);
    try { localStorage.setItem('fc_email', email); } catch (_) {}
    $('#lSenha').value = '';
  } catch (e) { $('#lErro').textContent = erroLogin(e); $('#lErro').hidden = false; }
  finally { b.disabled = false; b.textContent = 'Entrar'; }
});
$('#fTrava').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  $('#tErro').hidden = true;
  try {
    await reauthenticateWithCredential(auth.currentUser, EmailAuthProvider.credential(auth.currentUser.email, $('#tSenha').value));
    $('#tSenha').value = ''; S.ultimoUso = Date.now(); mostra('#telaApp');
  } catch (e) { $('#tErro').textContent = erroLogin(e); $('#tErro').hidden = false; }
});
async function sair() { $('#folha').hidden = true; S.dados = null; S.chat = []; await signOut(auth).catch(() => {}); }
$('#tSair').onclick = sair; $('#fSair').onclick = sair;
$('#hMenu').onclick = () => { $('#folha').hidden = false; };
$('#fFecha').onclick = () => { $('#folha').hidden = true; };
$('#folha').addEventListener('click', (e) => { if (e.target.id === 'folha') $('#folha').hidden = true; });
$('#fAtualiza').onclick = () => Browser.open({ url: REL_APK });

function travar() { if (!auth.currentUser) return; $('#tSub').textContent = `${(S.perfil && S.perfil.nome) || ''}, o app ficou ${TRAVA_MIN} minutos sem uso. Digite a sua senha para continuar.`; mostra('#telaTrava'); }
['touchstart', 'keydown', 'scroll'].forEach((t) => document.addEventListener(t, () => { if (!$('#telaApp').hidden) S.ultimoUso = Date.now(); }, { passive: true }));
setInterval(() => { if (!$('#telaApp').hidden && Date.now() - S.ultimoUso > TRAVA_MIN * 60000) travar(); }, 30000);
CapApp.addListener('appStateChange', ({ isActive }) => {
  if (!isActive) return;
  if (!$('#telaApp').hidden && Date.now() - S.ultimoUso > TRAVA_MIN * 60000) travar();
  else if (!$('#telaApp').hidden && Date.now() - S.carregadoEm > 5 * 60000) { S.dados = null; abrir(S.aba, true); }
}).catch?.(() => {});
CapApp.addListener('backButton', () => {
  if (!$('#folha').hidden) { $('#folha').hidden = true; return; }
  if (S.pilha.length) { S.pilha.pop()(); return; }
  if (S.aba !== 'inicio') { abrir('inicio'); return; }
  CapApp.minimizeApp();
}).catch?.(() => {});
$('#hVolta').onclick = () => { if (S.pilha.length) S.pilha.pop()(); };

// sem internet: o app não mostra dados guardados
function rede() { $('#offline').hidden = navigator.onLine; }
window.addEventListener('online', () => { rede(); if (!$('#telaApp').hidden) abrir(S.aba, true); });
window.addEventListener('offline', rede);
rede();

onAuthStateChanged(auth, async (u) => {
  S.user = u; S.dados = null; S.pilha = [];
  if (!u) { mostra('#telaLogin'); return; }
  try {
    const p = await getDoc(doc(db, 'usuarios', u.uid));
    const d = p.exists() ? p.data() : null;
    if (!d || d.ativo !== true) { await signOut(auth); $('#lErro').textContent = 'Usuário sem acesso ao sistema. Fale com o Admin.'; $('#lErro').hidden = false; return; }
    if (d.trocarSenha) { await signOut(auth); $('#lErro').textContent = 'Crie a sua senha no FiscoCont+ do computador antes de usar o app.'; $('#lErro').hidden = false; return; }
    S.perfil = { nome: d.nome || u.email, email: u.email, perfil: d.perfil, modulos: Array.isArray(d.modulos) ? d.modulos : null };
  } catch (e) { await signOut(auth); $('#lErro').textContent = erroLogin(e); $('#lErro').hidden = false; return; }
  $('#fNome').textContent = S.perfil.nome; $('#fEmail').textContent = S.perfil.email;
  S.ultimoUso = Date.now();
  mostra('#telaApp');
  abrir('inicio');
  checaVersao();
});

// ------------------------------------------------------------------ dados (só do Firestore, sem cache em disco)
async function lerTudo(forca) {
  if (S.dados && !forca && Date.now() - S.carregadoEm < 5 * 60000) return S.dados;
  const ano = new Date().getFullYear();
  const ler = async (fn) => { try { return await fn(); } catch (e) { return { semAcesso: /permission/i.test(String(e && (e.code || e.message))) , erro: e }; } };
  const [dare, fisc, fech, cert] = await Promise.all([
    ler(async () => { const out = { docs: [], meta: null }; (await getDocs(collection(db, 'dare'))).forEach((d) => { if (d.id === `_meta_${ano}`) out.meta = d.data(); else if (d.id.startsWith(`${ano}_`)) out.docs.push(d.data()); }); return out; }),
    ler(async () => { const out = { docs: [], meta: null }; (await getDocs(collection(db, 'fisconforme'))).forEach((d) => { if (d.id === '_meta') out.meta = d.data(); else if (!d.id.startsWith('_')) out.docs.push(d.data()); }); return out; }),
    ler(async () => { const c = compAnt(); const [cad, mes] = await Promise.all([getDoc(doc(db, 'fechamento_sn', 'cadastro')), getDoc(doc(db, 'fechamento_sn', c))]); return { comp: c, cadastro: cad.exists() ? cad.data() : null, mes: mes.exists() ? mes.data() : null }; }),
    ler(async () => { const out = []; (await getDocs(collection(db, 'certificados'))).forEach((d) => out.push({ cnpj: d.id, ...d.data() })); return out; }),
  ]);
  S.dados = { dare, fisc, fech, cert, ano, empresas: montaEmpresas(dare, fisc, fech, cert) };
  S.carregadoEm = Date.now();
  return S.dados;
}
function montaEmpresas(dare, fisc, fech, cert) {
  const m = new Map();
  const chave = (cnpj, ie, nome) => (so(cnpj).length === 14 ? so(cnpj) : so(ie) ? 'ie' + so(ie) : 'n' + norm(nome));
  const pega = (cnpj, ie, nome) => {
    let k = chave(cnpj, ie, nome);
    // junta pela IE quando um lado tem CNPJ e o outro não
    if (!m.has(k) && so(ie)) for (const [k2, e] of m) if (e.ie && so(e.ie) === so(ie)) { k = k2; break; }
    if (!m.has(k)) m.set(k, { id: k, cnpj: so(cnpj), ie: so(ie), nome: nome || '', debitos: [], fisc: [], fech: null, cert: null });
    const e = m.get(k); if (!e.cnpj && so(cnpj)) e.cnpj = so(cnpj); if (!e.ie && so(ie)) e.ie = so(ie); if ((!e.nome || e.nome.length < 4) && nome) e.nome = nome;
    return e;
  };
  if (dare && dare.docs) for (const d of dare.docs) { const e = pega(d.cnpj, d.ie, d.razao || d.nome); e.debitos = (d.debitos || []).map((l) => ({ ...l, ie: d.ie })); e.lidoEm = d.lidoEm; }
  if (fisc && fisc.docs) for (const d of fisc.docs) if (d.status && d.status !== 'fora') pega(d.cnpj, d.ie, d.nome).fisc.push(d);
  if (fech && fech.cadastro && fech.cadastro.empresas) {
    const mes = (fech.mes && fech.mes.empresas) || {};
    for (const [id, c] of Object.entries(fech.cadastro.empresas)) { if (c.ativa === false) continue; pega(c.cnpj, '', c.nome).fech = { ...c, ...(mes[id] || {}), id }; }
  }
  if (Array.isArray(cert)) for (const c of cert) { const e = m.get(so(c.cnpj)) || (c.nome ? pega(c.cnpj, '', c.nome) : null); if (e) e.cert = c; }
  return [...m.values()].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
}
const concluida = (f) => f && ['esc', 'pgdas'].every((k) => f[k] === 'Sim' || f[k] === 'N/A');

// ------------------------------------------------------------------ abas
document.querySelectorAll('.tb button').forEach((b) => b.addEventListener('click', () => abrir(b.dataset.aba)));
function abrir(aba, forca) {
  S.aba = aba; S.pilha = [];
  document.querySelectorAll('.tb button').forEach((b) => b.classList.toggle('on', b.dataset.aba === aba));
  window.scrollTo(0, 0);
  ({ inicio: telaInicio, empresas: telaEmpresas, consultas: telaConsultas, ajuda: telaAjuda })[aba](forca);
}

// Início: números e alertas
async function telaInicio(forca) {
  const d0 = new Date();
  topo(`${MESES[d0.getMonth()][0].toUpperCase()}${MESES[d0.getMonth()].slice(1)} de ${d0.getFullYear()}`, `${saudacao()}, ${(S.perfil.nome || '').split(' ')[0]}`);
  carregando();
  let d;
  try { d = await lerTudo(forca); } catch (e) { C().innerHTML = `<div class="vazio">Não foi possível ler os dados: ${esc(e.message || e)}</div>`; return; }
  if (S.aba !== 'inicio') return;
  const h = hoje0(), em7 = new Date(h); em7.setDate(em7.getDate() + 7);
  const deb = d.empresas.flatMap((e) => e.debitos.map((l) => ({ ...l, emp: e, v: dBr(l.venc) })));
  const vence7 = deb.filter((l) => l.v && l.v >= h && l.v <= em7), vencidos = deb.filter((l) => l.v && l.v < h);
  const fiscPend = d.empresas.flatMap((e) => e.fisc.filter((x) => x.status === 'pendente').map((x) => ({ ...x, emp: e })));
  const novasF = fiscPend.filter((x) => { const p = dIso(x.primeiraVez); return p && dias(p) >= -7; });
  const fechEmp = d.empresas.filter((e) => e.fech);
  const fechOk = fechEmp.filter((e) => concluida(e.fech)).length;
  const certs = d.empresas.filter((e) => e.cert && e.cert.validade).map((e) => ({ e, v: dIso(e.cert.validade) })).filter((x) => x.v && dias(x.v) <= 30).sort((a, b) => a.v - b.v);
  const k = (cor, tit, val, sub, aba) => `<button class="k" style="--c:${cor}" data-ir="${aba || ''}"><small>${tit}</small><b>${val}</b><span>${sub}</span></button>`;
  let html = '<div class="k2">';
  html += d.dare.semAcesso ? k('#8a90a6', 'DAREs', '—', 'sem acesso ao módulo') : k('#c93a3a', 'DAREs vencendo (7 dias)', vence7.length, `${brl(vence7.reduce((s, l) => s + (l.valorAtuN || l.valorN || 0), 0))}${vencidos.length ? ` · ${vencidos.length} vencido(s)` : ''}`, 'dare');
  html += d.fisc.semAcesso ? k('#8a90a6', 'Fisconforme', '—', 'sem acesso ao módulo') : k('#eb6834', 'Fisconforme', fiscPend.length, `pendente(s)${novasF.length ? ` · ${novasF.length} nova(s)` : ''}`, 'fisc');
  html += fechEmp.length ? k('#2a78d6', `Fechamento Simples ${compBr(d.fech.comp)}`, `${fechOk}/${fechEmp.length}`, 'empresas concluídas', 'sn') : k('#2a78d6', 'Fechamento Simples', '—', 'sem dados');
  html += k('#eda100', 'Certificados', certs.length, Array.isArray(d.cert) && d.cert.length ? 'vencem em 30 dias' : 'aguardando o computador enviar', 'cert');
  html += '</div>';
  // alertas
  const al = [];
  vencidos.sort((a, b) => a.v - b.v).slice(0, 5).forEach((l) => al.push({ i: '!', c: 'r', t: 'DARE vencido', s: `${l.emp.nome} · ${l.rec || ''} ref. ${l.ref || l.comp || ''}`, tag: brl(l.valorAtuN || l.valorN), e: l.emp }));
  vence7.sort((a, b) => a.v - b.v).slice(0, 8).forEach((l) => { const n = dias(l.v); al.push({ i: '⏰', c: n <= 1 ? 'r' : 'o', t: n === 0 ? 'DARE vence hoje' : n === 1 ? 'DARE vence amanhã' : `DARE vence em ${n} dias`, s: `${l.emp.nome} · ${l.rec || ''} ref. ${l.ref || l.comp || ''}`, tag: brl(l.valorAtuN || l.valorN), e: l.emp }); });
  novasF.slice(0, 6).forEach((x) => al.push({ i: 'F', c: 'o', t: 'Nova notificação Fisconforme', s: `${x.emp.nome} · ${x.desc || x.periodo || ''}`, tag: 'nova', e: x.emp }));
  certs.slice(0, 6).forEach(({ e, v }) => { const n = dias(v); al.push({ i: '🔑', c: n < 0 ? 'r' : 'y', t: n < 0 ? 'Certificado vencido' : `Certificado vence em ${n} dia(s)`, s: e.nome, tag: fmtD(v).slice(0, 5), e }); });
  html += `<h3>Alertas <small>${d.dare.meta && d.dare.meta.ultimaLeitura ? `SEFIN lida em ${esc(quando(d.dare.meta.ultimaLeitura))}` : ''}</small></h3>`;
  html += al.length ? al.map((a, i) => `<button class="al" data-al="${i}"><i class="${a.c}">${a.i}</i><div class="tx"><b>${esc(a.t)}</b><span>${esc(a.s)}</span></div><em class="tag ${a.c}">${esc(a.tag)}</em></button>`).join('') : '<div class="vazio">Nenhum alerta agora. 👍</div>';
  C().innerHTML = html;
  C().querySelectorAll('[data-al]').forEach((b) => b.addEventListener('click', () => telaEmpresa(al[+b.dataset.al].e, () => abrir('inicio'))));
  C().querySelectorAll('[data-ir]').forEach((b) => b.addEventListener('click', () => { if (b.dataset.ir) { S.filtro = b.dataset.ir; abrir('empresas'); } }));
}
function saudacao() { const h = new Date().getHours(); return h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite'; }

// Empresas: lista com busca
const FILTROS = { dare: 'com DARE em aberto', fisc: 'com Fisconforme pendente', sn: 'do Simples em aberto', cert: 'com certificado vencendo' };
async function telaEmpresas(forca) {
  const filtro = S.filtro || ''; S.filtro = '';
  topo('Empresas', filtro ? FILTROS[filtro] : 'débitos, Fisconforme, Simples e certificado');
  carregando();
  let d; try { d = await lerTudo(forca); } catch (e) { C().innerHTML = `<div class="vazio">${esc(e.message || e)}</div>`; return; }
  if (S.aba !== 'empresas') return;
  const h = hoje0();
  const passa = (e) => !filtro || (filtro === 'dare' && e.debitos.length) || (filtro === 'fisc' && e.fisc.some((x) => x.status === 'pendente'))
    || (filtro === 'sn' && e.fech && !concluida(e.fech)) || (filtro === 'cert' && e.cert && dIso(e.cert.validade) && dias(dIso(e.cert.validade)) <= 30);
  C().innerHTML = `<input class="busca" id="eBusca" type="search" placeholder="Buscar por nome, CNPJ ou IE">${filtro ? `<div class="dica">Mostrando só as empresas ${FILTROS[filtro]}. <a href="#" id="eTodas">Ver todas</a></div>` : ''}<div id="eLista"></div>`;
  const desenha = () => {
    const q = norm($('#eBusca').value), qd = so($('#eBusca').value);
    const lista = d.empresas.filter(passa).filter((e) => !q || norm(e.nome).includes(q) || (qd.length >= 3 && (e.cnpj.includes(qd) || e.ie.includes(qd))));
    $('#eLista').innerHTML = lista.length ? lista.slice(0, 300).map((e, i) => {
      const tags = [];
      const venc = e.debitos.filter((l) => dBr(l.venc) && dBr(l.venc) < h).length;
      if (e.debitos.length) tags.push(`<em class="tag ${venc ? 'r' : 'o'}">${e.debitos.length} DARE</em>`);
      const fp = e.fisc.filter((x) => x.status === 'pendente').length; if (fp) tags.push(`<em class="tag o">${fp} Fisc.</em>`);
      if (e.fech) tags.push(`<em class="tag ${concluida(e.fech) ? 'g' : 'b'}">SN ${concluida(e.fech) ? 'ok' : 'aberto'}</em>`);
      const cv = e.cert && dIso(e.cert.validade); if (cv && dias(cv) <= 30) tags.push(`<em class="tag y">cert. ${fmtD(cv).slice(0, 5)}</em>`);
      return `<button class="emp" data-i="${i}"><div class="tx"><b>${esc(e.nome || docf(e.cnpj))}</b><span>${e.cnpj ? docf(e.cnpj) : ''}${e.ie ? ` · IE ${esc(e.ie)}` : ''}</span></div><div class="tags">${tags.join('')}</div></button>`;
    }).join('') : '<div class="vazio">Nenhuma empresa encontrada.</div>';
    $('#eLista').querySelectorAll('[data-i]').forEach((b) => b.addEventListener('click', () => telaEmpresa(lista[+b.dataset.i], () => abrir('empresas'))));
  };
  $('#eBusca').addEventListener('input', desenha);
  if ($('#eTodas')) $('#eTodas').onclick = (ev) => { ev.preventDefault(); abrir('empresas'); };
  desenha();
}

// Empresa: tudo de uma empresa
async function telaEmpresa(e, voltar) {
  S.pilha.push(voltar);
  window.scrollTo(0, 0);
  topo(e.nome || docf(e.cnpj), [e.cnpj ? docf(e.cnpj) : '', e.ie ? `IE ${e.ie}` : ''].filter(Boolean).join(' · '), true);
  const h = hoje0();
  let html = '';
  // débitos
  const deb = [...e.debitos].sort((a, b) => (dBr(a.venc) || 0) - (dBr(b.venc) || 0));
  html += `<div class="box"><b>Débitos na SEFIN (em aberto)</b>${deb.length ? deb.map((l) => { const v = dBr(l.venc); const n = v ? dias(v) : null; return `<div class="row"><span>${esc(l.rec || 'Receita')} · ref. ${esc(l.ref || l.comp || '')}<small>Nº ${esc(l.nr)}${l.parc && !/^0+$/.test(l.parc) ? ` parcela ${esc(l.parc)}` : ''} · ${v ? (n < 0 ? `<span class="tag r">vencido ${fmtD(v)}</span>` : `vence ${fmtD(v)}`) : esc(l.venc || '')}</small></span><b>${brl(l.valorAtuN || l.valorN)}</b></div>`; }).join('') : `<div class="vazio">${S.dados && S.dados.dare.semAcesso ? 'Você não tem acesso ao módulo Débitos e DARE.' : 'Nenhum débito em aberto na última leitura.'}</div>`}</div>`;
  // Fisconforme
  const fs_ = e.fisc.filter((x) => x.status !== 'resolvido');
  if (fs_.length || e.fisc.length) html += `<div class="box"><b>Fisconforme</b>${fs_.length ? fs_.map((x) => `<div class="row"><span>${esc(x.desc || 'Notificação')}<small>período ${esc(x.periodo || '')} · desde ${esc(fmtD(dIso(x.primeiraVez)) || '')}</small></span><b><em class="tag ${x.status === 'pendente' ? 'o' : x.status === 'indeferido' ? 'r' : 'b'}">${esc(x.status)}</em></b></div>`).join('') : '<div class="vazio">Nada pendente.</div>'}</div>`;
  // Simples
  if (e.fech) { const f = e.fech; const et = (k, t) => `<div class="row"><span>${t}</span><b>${esc(f[k] || '—')}</b></div>`; html += `<div class="box"><b>Fechamento do Simples · ${compBr(S.dados.fech.comp)}</b>${et('esc', 'Escrituração')}${et('pgdas', 'PGDAS / Receita')}<div class="row"><span>Situação</span><b><em class="tag ${concluida(f) ? 'g' : 'b'}">${concluida(f) ? `concluída${f.fin ? ' em ' + esc(f.fin) : ''}` : 'em aberto'}</em></b></div>${f.analista ? `<div class="row"><span>Analista</span><b>${esc(f.analista)}</b></div>` : ''}</div>`; }
  // certificado
  if (e.cert && e.cert.validade) { const v = dIso(e.cert.validade); const n = dias(v); html += `<div class="box"><b>Certificado digital</b><div class="row"><span>Validade</span><b><em class="tag ${n < 0 ? 'r' : n <= 30 ? 'y' : 'g'}">${fmtD(v)}${n < 0 ? ' · vencido' : n <= 30 ? ` · ${n} dia(s)` : ''}</em></b></div></div>`; }
  html += '<div id="spedBox"></div>';
  C().innerHTML = html;
  // números do SPED (só totais), por mês
  if (e.cnpj) {
    try {
      const out = [];
      (await getDocs(query(collection(db, 'sped_totais'), where('cnpj', '==', e.cnpj)))).forEach((x) => out.push(x.data()));
      out.sort((a, b) => String(b.comp).localeCompare(String(a.comp)));
      if (out.length && $('#spedBox')) $('#spedBox').innerHTML = out.slice(0, 3).map((t) => `<div class="box"><b>SPED Fiscal · ${compBr(t.comp)}</b><div class="row"><span>Faturamento</span><b>${brl(t.faturamento)}</b></div><div class="row"><span>ICMS débitos</span><b>${brl(t.debitos)}</b></div><div class="row"><span>ICMS créditos</span><b>${brl(t.creditos)}</b></div><div class="row"><span>ICMS a recolher</span><b>${brl(t.recolher)}</b></div><div class="row"><span>Alíquota efetiva</span><b>${Number(t.aliquota || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%</b></div></div>`).join('');
    } catch (_) { /* sem a coleção ainda: não mostra */ }
  }
}

// Consultas: CNPJ (público) e débitos
function telaConsultas() {
  topo('Consultas', 'CNPJ e débitos na SEFIN');
  C().innerHTML = `<div class="seg"><button data-q="cnpj" class="on">CNPJ</button><button data-q="deb">Débitos SEFIN</button></div><div id="qArea"></div>`;
  const vai = (q) => { C().querySelectorAll('.seg button').forEach((b) => b.classList.toggle('on', b.dataset.q === q)); q === 'cnpj' ? consultaCnpj() : consultaDeb(); };
  C().querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => vai(b.dataset.q)));
  vai('cnpj');
}
function consultaCnpj() {
  $('#qArea').innerHTML = `<input class="busca" id="qCnpj" inputmode="numeric" placeholder="CNPJ (só números ou com pontuação)"><button class="btn" id="qBtn">Consultar</button><div id="qRes"></div><p class="nota">Dados públicos da Receita Federal (BrasilAPI).</p>`;
  const go = async () => {
    const c = so($('#qCnpj').value);
    if (c.length !== 14) { $('#qRes').innerHTML = '<div class="vazio">Digite os 14 números do CNPJ.</div>'; return; }
    $('#qBtn').disabled = true; $('#qRes').innerHTML = '<div class="carregando">Consultando…</div>';
    try {
      const r = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${c}`);
      if (r.status === 404) throw new Error('CNPJ não encontrado na Receita.');
      if (!r.ok) throw new Error(`A consulta não respondeu (${r.status}). Tente de novo em instantes.`);
      const x = await r.json();
      const row = (t, v) => (v ? `<div class="row"><span>${t}</span><b>${esc(v)}</b></div>` : '');
      const sit = String(x.descricao_situacao_cadastral || '').toUpperCase();
      $('#qRes').innerHTML = `<div class="box" style="margin-top:12px"><b style="font-size:14.5px">${esc(x.razao_social)}</b>${x.nome_fantasia ? `<span style="color:var(--ink3);font-size:12px">${esc(x.nome_fantasia)}</span>` : ''}<div style="margin:4px 0 6px"><em class="tag ${sit === 'ATIVA' ? 'g' : 'r'}">${esc(sit || '—')}</em></div>
        ${row('CNPJ', docf(c))}${row('Abertura', x.data_inicio_atividade ? fmtD(dIso(x.data_inicio_atividade)) : '')}${row('Atividade principal', [x.cnae_fiscal, x.cnae_fiscal_descricao].filter(Boolean).join(' · '))}
        ${row('Natureza jurídica', x.natureza_juridica)}${row('Porte', x.porte)}${row('Simples Nacional', x.opcao_pelo_simples === true ? 'Optante' : x.opcao_pelo_simples === false ? 'Não optante' : '')}${row('MEI', x.opcao_pelo_mei === true ? 'Sim' : '')}
        ${row('Município', [x.municipio, x.uf].filter(Boolean).join(' · '))}${row('Capital social', x.capital_social ? brl(x.capital_social) : '')}${row('Sócios', (x.qsa || []).length ? String((x.qsa || []).length) : '')}</div>
        ${(x.cnaes_secundarios || []).filter((s) => s.codigo).length ? `<div class="box"><b>Atividades secundárias</b>${x.cnaes_secundarios.filter((s) => s.codigo).slice(0, 12).map((s) => `<div class="row"><span>${esc(s.descricao)}</span><b>${esc(s.codigo)}</b></div>`).join('')}</div>` : ''}`;
    } catch (e) { $('#qRes').innerHTML = `<div class="vazio">${esc(e.message || e)}</div>`; }
    finally { $('#qBtn').disabled = false; }
  };
  $('#qBtn').onclick = go;
  $('#qCnpj').addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
}
async function consultaDeb() {
  $('#qArea').innerHTML = '<input class="busca" id="qDeb" type="search" placeholder="Empresa, CNPJ ou IE"><div id="qRes"><div class="carregando">Carregando…</div></div>';
  let d; try { d = await lerTudo(); } catch (e) { $('#qRes').innerHTML = `<div class="vazio">${esc(e.message || e)}</div>`; return; }
  if (d.dare.semAcesso) { $('#qRes').innerHTML = '<div class="vazio">Você não tem acesso ao módulo Débitos e DARE.</div>'; return; }
  const desenha = () => {
    const q = norm($('#qDeb').value), qd = so($('#qDeb').value);
    const l = d.empresas.filter((e) => e.debitos.length).filter((e) => !q || norm(e.nome).includes(q) || (qd.length >= 3 && (e.cnpj.includes(qd) || e.ie.includes(qd))));
    const tot = l.reduce((s, e) => s + e.debitos.reduce((a, x) => a + (x.valorAtuN || x.valorN || 0), 0), 0);
    $('#qRes').innerHTML = `<div class="dica">${l.length} empresa(s) com débito em aberto · ${brl(tot)}${d.dare.meta && d.dare.meta.ultimaLeitura ? ` · lido em ${esc(quando(d.dare.meta.ultimaLeitura))}` : ''}</div>`
      + l.map((e, i) => `<button class="emp" data-i="${i}"><div class="tx"><b>${esc(e.nome)}</b><span>${e.debitos.length} débito(s)</span></div><b>${brl(e.debitos.reduce((a, x) => a + (x.valorAtuN || x.valorN || 0), 0))}</b></button>`).join('');
    $('#qRes').querySelectorAll('[data-i]').forEach((b) => b.addEventListener('click', () => telaEmpresa(l[+b.dataset.i], () => abrir('consultas'))));
  };
  $('#qDeb').addEventListener('input', desenha);
  desenha();
}

// Ajuda tributária (função chatIA do sistema). Antes de mandar, tira CNPJ, CPF, IE e nomes das empresas conhecidas.
function anonimiza(t) {
  let s = String(t || '')
    .replace(/\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}/g, '[CNPJ]')
    .replace(/\d{3}\.?\d{3}\.?\d{3}-?\d{2}/g, '[CPF]')
    .replace(/\b\d{9,14}\b/g, '[IE]');
  const nomes = ((S.dados && S.dados.empresas) || []).map((e) => e.nome).filter((n) => n && n.length >= 6).sort((a, b) => b.length - a.length);
  for (const n of nomes) {
    const base = n.replace(/\b(LTDA|ME|EPP|EIRELI|S\/?A)\.?$/i, '').trim();
    if (base.length < 6) continue;
    s = s.replace(new RegExp(base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+'), 'gi'), '[EMPRESA]');
  }
  return s.slice(0, 8000);
}
function md(t) {
  const linhas = esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').split(/\n/);
  let out = '', lista = false;
  for (const l of linhas) {
    const m = l.match(/^\s*[-*•]\s+(.*)/);
    if (m) { if (!lista) { out += '<ul>'; lista = true; } out += `<li>${m[1]}</li>`; continue; }
    if (lista) { out += '</ul>'; lista = false; }
    if (l.trim()) out += `<p>${l.replace(/^#+\s*/, '')}</p>`;
  }
  return out + (lista ? '</ul>' : '');
}
function telaAjuda() {
  topo('Ajuda tributária', 'Dúvidas de ICMS, Simples, SPED…');
  if (!S.dados) lerTudo().catch(() => {});
  C().innerHTML = `<div class="dica">Pergunte sobre tributos e obrigações. Não precisa escrever nome, CNPJ ou IE do cliente: o app tira esses dados antes de enviar. Confira sempre a resposta com a legislação.</div><div class="chat" id="chat"></div>
    <div class="cx"><textarea id="cxTx" rows="1" placeholder="Pergunte sobre tributos…"></textarea><button id="cxBt" aria-label="Enviar">➤</button></div>`;
  const chat = $('#chat');
  const pinta = () => { chat.innerHTML = S.chat.map((m) => (m.role === 'user' ? `<div class="mq">${esc(m.mostra)}</div>` : `<div class="ma">${md(m.mostra)}</div>`)).join(''); window.scrollTo(0, document.body.scrollHeight); };
  pinta();
  const tx = $('#cxTx');
  tx.addEventListener('input', () => { tx.style.height = 'auto'; tx.style.height = Math.min(120, tx.scrollHeight) + 'px'; });
  $('#cxBt').onclick = async () => {
    const t = tx.value.trim(); if (!t) return;
    tx.value = ''; tx.style.height = 'auto'; $('#cxBt').disabled = true;
    // histórico enviado: só os pares pergunta/resposta que deram certo, como no computador
    const historico = S.chat.filter((m) => m.api).map((m) => m.api);
    const enviado = anonimiza(t);
    const q = { role: 'user', mostra: t, api: null };
    S.chat.push(q);
    pinta(); chat.insertAdjacentHTML('beforeend', '<div class="ma pensando">Pesquisando…</div>'); window.scrollTo(0, document.body.scrollHeight);
    try {
      const r = (await httpsCallable(fns, 'chatIA', { timeout: 130000 })({ mensagem: enviado, historico })).data;
      q.api = { role: 'user', content: enviado };
      S.chat.push({ role: 'assistant', mostra: r.texto || '(sem resposta)', api: r.resposta || { role: 'assistant', content: r.texto || '' } });
      if (S.chat.length > 24) S.chat = S.chat.slice(-24);
      while (S.chat.length && S.chat[0].role !== 'user') S.chat.shift();
    } catch (e) {
      S.chat.push({ role: 'assistant', mostra: `Não consegui responder agora: ${String(e.message || e).replace(/^FirebaseError:\s*/, '')}`, api: null });
    }
    $('#cxBt').disabled = false; if (S.aba === 'ajuda') pinta();
  };
}

// ------------------------------------------------------------------ versão nova (download do APK)
async function checaVersao() {
  try {
    const r = await fetch(REL_API, { headers: { Accept: 'application/vnd.github+json' } });
    if (!r.ok) return;
    const j = await r.json();
    const m = String(j.name || '').match(/(\d+)\.(\d+)\.(\d+)/);
    if (!m) return;
    const nova = m.slice(1).map(Number), atual = VERSAO.split('.').map(Number);
    const maior = nova[0] - atual[0] || nova[1] - atual[1] || nova[2] - atual[2];
    if (maior > 0) {
      S.novaVersao = m[0];
      $('#fAtualiza').hidden = false; $('#fAtualiza').textContent = `Baixar a versão ${m[0]}`;
      aviso(`Nova versão do app: <b>${m[0]}</b>.`, { t: 'Baixar', f: () => Browser.open({ url: REL_APK }) });
    }
  } catch (_) { /* sem resposta do GitHub: tenta na próxima abertura */ }
}

StatusBar.setBackgroundColor({ color: '#18214a' }).catch(() => {});
