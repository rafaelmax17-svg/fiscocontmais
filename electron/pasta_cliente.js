'use strict';
// Pasta de cada empresa no drive do escritório (pedido do Rafael, 17/11/2026):
//   G:\Drives compartilhados\Fiscal - Lucro Presumido | Fiscal - Lucro Real | Fiscal - Simples Nacional \ <Empresa>
// Os arquivos do mês vão para  <Empresa>\Relatórios\<AAAA>\<mês>.
//
// • A pasta da empresa é achada pelo nome (sem diferença de maiúscula, acento e pontuação). Filial: o CNPJ diz se é
//   matriz (0001) ou filial; filial só usa pasta com "Filial" no nome — nunca a pasta da matriz.
// • O sistema NUNCA cria a pasta da empresa. Dentro dela, cria só o que faltar de Relatórios\AAAA\mês.
// • O mês usa a pasta que já existir, com qualquer um destes nomes: 10, 102026, 10-2026, 10.2026, 2026-10, "10 - Outubro"…
//   Se não houver, cria "10" (dois dígitos).
// • Sem pasta encontrada: quem chama salva no caminho de sempre e avisa.

const fs = require('fs');
const path = require('path');

const RAIZES = process.env.FC_RAIZES_CLIENTE ? JSON.parse(process.env.FC_RAIZES_CLIENTE) : [
  'G:\\Drives compartilhados\\Fiscal - Lucro Presumido',
  'G:\\Drives compartilhados\\Fiscal - Lucro Real',
  'G:\\Drives compartilhados\\Fiscal - Simples Nacional',
];
const CACHE_MS = 10 * 60 * 1000;
let _cache = { em: 0, lista: [] };

const norm = (s) => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/&/g, ' e ').replace(/[^a-z0-9]+/g, ' ').trim();
// tira o tipo societário (Ltda, ME, EPP, EIRELI, S/A) para "Comercio X Ltda." e "COMERCIO X LTDA" serem o mesmo nome
const chave = (s) => norm(s).replace(/\b(ltda|me|epp|eireli|s a|sa|ss)\b/g, ' ').replace(/\s+/g, ' ').trim();

function _lista() {
  if (Date.now() - _cache.em < CACHE_MS && _cache.lista.length) return _cache.lista;
  const lista = [];
  for (const raiz of RAIZES) {
    let nomes = [];
    try { nomes = fs.readdirSync(raiz, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name); } catch (_) { continue; }
    for (const nome of nomes) lista.push({ nome, dir: path.join(raiz, nome), k: chave(nome), regime: path.basename(raiz).replace(/^Fiscal - /, '') });
  }
  _cache = { em: Date.now(), lista };
  return lista;
}
// 2.4.59: nome da Receita × nome da pasta com conectivos diferentes ("TALITA YURI COMERCIO…" × "Talita e Yuri Comercio…")
const LIGA = new Set(['e', 'de', 'da', 'do', 'das', 'dos', 'para', 'com', 'em', 'a', 'o']);
const _tok = (k) => k.split(' ').filter((w) => w && !LIGA.has(w));
const _solta = (k) => _tok(k).sort().join(' ');
function _parecido(k, lista) {
  const alvo = new Set(_tok(k));
  if (alvo.size < 2) return null;
  const nomes = lista.filter((d) => !/\bfilial\b/.test(d.k));
  const iguais = nomes.filter((d) => _solta(d.k) === _solta(k));
  if (iguais.length) return iguais.length === 1 ? iguais[0] : null;
  const nota = nomes.map((d) => {
    const t = new Set(_tok(d.k));
    let c = 0; t.forEach((w) => { if (alvo.has(w)) c++; });
    return { d, j: c / (alvo.size + t.size - c) };
  }).sort((a, b) => b.j - a.j);
  if (nota[0] && nota[0].j >= 0.85 && (!nota[1] || nota[0].j - nota[1].j >= 0.1)) return nota[0].d;
  return null;
}
function limparCache() { _cache = { em: 0, lista: [] }; }

// 2.4.60: pasta da empresa escolhida pela equipe quando o nome não bate (guardada na nuvem, em mit_empresas/<cnpj>.pasta)
const _escolhidas = new Map();
function lembrar(cnpj, dir) { const c = String(cnpj || '').replace(/\D/g, ''); if (c && dir) _escolhidas.set(c, dir); }
// a pasta escolhida pode ser uma subpasta (Sped - Contribuições, Relatórios…): sobe até a pasta da empresa, que é a filha
// direta de "Fiscal - <regime>"
function pastaDaEmpresa(dir) {
  const d = path.resolve(String(dir || ''));
  for (const raiz of RAIZES) {
    const r = path.resolve(raiz);
    const rel = path.relative(r, d);
    if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) return path.join(r, rel.split(path.sep)[0]);
  }
  return d;
}
function disponivel() { return RAIZES.some((r) => { try { return fs.statSync(r).isDirectory(); } catch (_) { return false; } }); }

// { dir, regime } da pasta da empresa, ou null
function achar({ nome, cnpj } = {}) {
  const esc = _escolhidas.get(String(cnpj || '').replace(/\D/g, ''));
  if (esc) { try { if (fs.statSync(esc).isDirectory()) return { nome: path.basename(esc), dir: esc, k: chave(path.basename(esc)), regime: path.basename(path.dirname(esc)).replace(/^Fiscal - /, ''), escolhida: true }; } catch (_) {} }
  const k = chave(nome);
  if (!k) return null;
  const lista = _lista();
  if (!lista.length) return null;
  const doc = String(cnpj || '').replace(/\D/g, '');
  const ordem = doc.length === 14 ? parseInt(doc.slice(8, 12), 10) : 1;
  // o próprio nome cadastrado já diz a filial ("... - Filial 01 - Guajara Mirim"): nome exato resolve
  const exatos = lista.filter((d) => d.k === k);
  if (/\bfilial\b/.test(k)) return exatos.length === 1 ? exatos[0] : null;
  // sem CNPJ não dá para saber se é matriz ou filial: se a empresa tem pasta de filial, não arrisca
  if (doc.length !== 14 && lista.some((d) => d.k.startsWith(`${k} `) && /\bfilial\b/.test(d.k))) return null;
  if (ordem <= 1) return exatos.length === 1 ? exatos[0] : (exatos.length ? null : _parecido(k, lista));
  // filial: só pastas "<nome> ... filial N ..."
  const filiais = lista.filter((d) => d.k.startsWith(`${k} `) && /\bfilial\b/.test(d.k));
  if (filiais.length === 1) return filiais[0];
  const numero = (d) => { const m = d.k.match(/\bfilial\s*0*(\d+)/); return m ? parseInt(m[1], 10) : null; };
  for (const alvo of [ordem - 1, ordem]) {
    const c = filiais.filter((d) => numero(d) === alvo);
    if (c.length === 1) return c[0];
  }
  return null;
}

function _filho(dir, teste) {
  try { return fs.readdirSync(dir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name).find(teste) || null; } catch (_) { return null; }
}
// <Empresa>\Relatórios\<AAAA>\<mês> — usa o que existir, cria só o que faltar (nunca a pasta da empresa)
function pastaMes(dirEmp, ano, mes, criar = true) {
  if (!dirEmp || !fs.existsSync(dirEmp)) return null;
  const rel = _filho(dirEmp, (n) => /^relatorios?$/.test(norm(n))) || 'Relatórios';
  return _anoMes(path.join(dirEmp, rel), ano, mes, criar);
}

// 2.4.57: <Empresa>\Sped - Contribuições (ou "EFD-Contribuições", "SPED Contribuições"…)\<AAAA>\<mês> — recibo da
// DCTFWeb e guia do MIT acompanham a EFD-Contribuições da competência. Sem a pasta, cria "Sped - Contribuições".
function pastaContribMes(dirEmp, ano, mes, criar = true) {
  if (!dirEmp || !fs.existsSync(dirEmp)) return null;
  const ehContrib = (n) => { const k = norm(n); return /\bcontribuicoes\b/.test(k) && /\b(sped|efd)\b/.test(k) && !/\bfiscal\b/.test(k); };
  const base = _filho(dirEmp, ehContrib) || 'Sped - Contribuições';
  return _anoMes(path.join(dirEmp, base), ano, mes, criar);
}
function pastaContribDoMes(emp, ano, mes, criar = true) {
  const p = achar(emp);
  if (!p) return null;
  try { return pastaContribMes(p.dir, ano, mes, criar); } catch (_) { return null; }
}

function _anoMes(dRel, ano, mes, criar) {
  ano = String(ano); const mm = String(mes).padStart(2, '0'), m = String(parseInt(mes, 10));
  const a = _filho(dRel, (n) => norm(n) === ano) || ano;
  const dAno = path.join(dRel, a);
  const okMes = (n) => {
    const d = String(n).replace(/\D+/g, ' ').trim().split(' ');
    const j = d.join('');
    if (j === mm || j === m || j === mm + ano || j === m + ano || j === ano + mm || j === ano + m) return true;
    return (d[0] === mm || d[0] === m) && (d.length === 1 || d[1] === ano) && !/^\d{3,}$/.test(d[0]);
  };
  const ms = _filho(dAno, okMes) || mm;
  const dMes = path.join(dAno, ms);
  if (criar) fs.mkdirSync(dMes, { recursive: true });
  return dMes;
}

// atalho: pasta do mês da empresa (ou null, sem criar nada se a empresa não tiver pasta)
function pastaDoMes(emp, ano, mes, criar = true) {
  const p = achar(emp);
  if (!p) return null;
  try { return pastaMes(p.dir, ano, mes, criar); } catch (_) { return null; }
}

module.exports = { RAIZES, achar, pastaMes, pastaDoMes, pastaContribMes, pastaContribDoMes, disponivel, limparCache, chave, lembrar, pastaDaEmpresa };
