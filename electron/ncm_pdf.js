'use strict';
// PDF ao cliente: "Ajuste de NCM conforme o XML das notas de entrada" (Corretor do SPED Fiscal · Análise Inteligente).
// Só o que foi alterado de fato no arquivo corrigido (resumo.ncm de analisar_tudo.aplicar → ncm_xml.detalhe_pdf).
// Informativo ao cliente: sem assinatura. HTML → printToPDF (main.js, admin:ncmPdf).
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const doc = (d) => { d = String(d || '').replace(/\D/g, ''); return d.length === 14 ? d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : d.length === 11 ? d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4') : d; };
const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const num = (n) => Number(n || 0).toLocaleString('pt-BR');
function periodo(e) {
  const a = String(e.dt_ini || ''), b = String(e.dt_fin || '');
  if (!/^\d{8}$/.test(a)) return '';
  const mi = `${a.slice(2, 4)}/${a.slice(4)}`, mf = /^\d{8}$/.test(b) ? `${b.slice(2, 4)}/${b.slice(4)}` : mi;
  return mi === mf ? mi : `${mi} a ${mf}`;
}
const CSS = `
@page{size:A4;margin:14mm 13mm 16mm}
*{box-sizing:border-box}
body{margin:0;font:10px/1.45 "Segoe UI",Inter,Arial,sans-serif;color:#1d2340;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.top{display:flex;align-items:center;gap:14px;padding-bottom:12px;border-bottom:2px solid #eef0f6;position:relative}
.top::after{content:"";position:absolute;left:0;bottom:-2px;width:90px;height:2px;background:#e8632b}
.top img{width:64px;height:64px;border-radius:50%}
.marca b{display:block;font-size:13px;letter-spacing:.14em;color:#2b2f6b}
.marca span{font-size:9px;color:#7a809a;letter-spacing:.04em}
.top .sp{flex:1}
.doc{text-align:right;font-size:9px;color:#7a809a}.doc b{display:block;font-size:10.5px;color:#2b2f6b;letter-spacing:.06em;text-transform:uppercase}
.hero{margin-top:16px;background:linear-gradient(120deg,#1b2350,#2b3a72);color:#fff;border-radius:12px;padding:18px 20px;position:relative;overflow:hidden}
.hero::after{content:"";position:absolute;right:-40px;top:-60px;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,rgba(232,99,43,.55),transparent 65%)}
.hero small{font-size:8.5px;letter-spacing:.16em;text-transform:uppercase;color:#c9cdf0}
.hero h1{margin:4px 0 2px;font-size:20px;line-height:1.2}
.hero p{margin:0;color:#dfe2fb;font-size:10px}
.cli{display:grid;grid-template-columns:2.2fr 1.2fr 1fr 1.4fr;gap:0;margin-top:12px;border:1px solid #e6e8f0;border-radius:10px;overflow:hidden}
.cli div{padding:8px 11px;border-left:1px solid #e6e8f0}.cli div:first-child{border-left:none}
.cli span{display:block;font-size:7.5px;letter-spacing:.1em;text-transform:uppercase;color:#8a90a6}
.cli b{font-size:10.5px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
.kpi{border:1px solid #e6e8f0;border-radius:10px;padding:10px 12px;position:relative}
.kpi::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:0 3px 3px 0;background:var(--c)}
.kpi b{display:block;font-size:20px;color:#1b2350;line-height:1.1}
.kpi span{font-size:8.5px;color:#6a7090}
.txt{margin-top:14px;display:grid;grid-template-columns:1.5fr 1fr;gap:12px}
.txt h2,.lst h2{font-size:11px;margin:0 0 4px;color:#1b2350}
.txt p{margin:0;color:#3d4462}
.leg{background:#f6f7fb;border-radius:10px;padding:10px 12px;font-size:9px;color:#3d4462}
.leg b{color:#1b2350}
.lst{margin-top:16px}
table{width:100%;border-collapse:collapse}
thead th{font-size:7.5px;letter-spacing:.1em;text-transform:uppercase;color:#8a90a6;text-align:left;padding:7px 8px;border-bottom:1.5px solid #e1e4ee;background:#fafbfd}
tbody td{padding:8px;border-bottom:1px solid #eef0f5;vertical-align:top}
tbody tr{break-inside:avoid}
td.cod{font-family:Consolas,monospace;color:#6a7090;font-size:9px;width:48px}
td .x{display:block;color:#8a90a6;font-size:8.5px;margin-top:2px}
td.ncm{white-space:nowrap;width:150px}
td.ncm .de{color:#9aa0b6;text-decoration:line-through;font-family:Consolas,monospace;font-size:9.5px}
td.ncm svg{width:16px;height:8px;margin:0 6px;color:#e8632b;vertical-align:middle}
td.ncm .para{font-family:Consolas,monospace;font-weight:700;font-size:10px;color:#0f6e48;background:#e5f6ee;border-radius:5px;padding:2px 6px}
td.ref{font-size:8.5px;color:#4d5372;width:165px}
td.ref .st{display:block;margin-top:4px;color:#9a5300;background:#fff3e2;border-radius:5px;padding:2px 6px;font-weight:600;width:max-content;max-width:100%}
.rec{margin-top:14px;display:flex;gap:10px;align-items:flex-start;border:1px solid #f4d5c4;background:#fff7f2;border-radius:10px;padding:10px 12px;break-inside:avoid}
.rec i{flex:none;width:22px;height:22px;border-radius:50%;background:#e8632b;color:#fff;font-style:normal;font-weight:800;display:flex;align-items:center;justify-content:center;font-size:12px}
.rec b{color:#1b2350}
.base{margin-top:10px;font-size:8.5px;color:#6a7090;break-inside:avoid}
`;
function html(d, logo, hoje) {
  const e = d.empresa || {}, itens = d.feitos || [];
  const seta = '<svg viewBox="0 0 20 10"><path d="M1 5h16M13 1l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const linhas = itens.map((i) => `<tr><td class="cod">${esc(i.cod)}</td><td><b>${esc(i.descr || i.cod)}</b>${i.xprod ? `<span class="x">No XML: “${esc(i.xprod)}”</span>` : ''}</td>
    <td class="ncm"><span class="de">${esc(i.de || 'em branco')}</span>${seta}<span class="para">${esc(i.para)}</span></td>
    <td class="ref">${esc(i.ref)}${i.notas > 1 ? ` <span style="color:#8a90a6">(+${i.notas - 1} nota(s))</span>` : ''}${i.st ? `<span class="st">${esc(cap(i.st.replace(/^com o NCM do XML /, '')))}</span>` : ''}</td></tr>`).join('');
  const kpis = [['#e8632b', num(itens.length), 'produto(s) com o NCM alterado'], ['#2b3a72', num(d.notas), 'nota(s) de entrada com esses produtos'],
    ['#1baf7a', num(d.conferidos), 'item(ns) de entrada conferidos com o XML'], ['#eda100', num(d.st_muda), 'produto(s) com mudança na ST de RO']];
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Ajuste de NCM · ${esc(e.nome || '')}</title><style>${CSS}</style></head><body>
<div class="top">${logo ? `<img src="${logo}" alt="Liddera">` : ''}<div class="marca"><b style="letter-spacing:.02em;font-size:12px">Liddera | Inteligência em Negócios</b><span>Departamento Fiscal</span></div><div class="sp"></div>
<div class="doc"><b>Relatório de ajustes</b>EFD ICMS/IPI (SPED Fiscal)</div></div>
<div class="hero"><small>Cadastro de produtos · Registro 0200</small><h1>Ajuste de NCM conforme o XML das notas de entrada</h1>
<p>Produtos que tiveram o NCM do cadastro alterado para o NCM informado pelo fornecedor na NF-e.</p></div>
<div class="cli"><div><span>Empresa</span><b>${esc(e.nome || '—')}</b></div><div><span>${String(e.cnpj || '').length === 11 ? 'CPF' : 'CNPJ'}</span><b>${esc(doc(e.cnpj) || '—')}</b></div><div><span>Período</span><b>${esc(periodo(e) || '—')}</b></div><div><span>Data do ajuste</span><b>${esc(hoje)}</b></div></div>
<div class="kpis">${kpis.map(([c, v, t]) => `<div class="kpi" style="--c:${c}"><b>${v}</b><span>${t}</span></div>`).join('')}</div>
<div class="txt"><div><h2>O que foi feito</h2><p>Comparamos o NCM do cadastro de cada produto no SPED Fiscal com o NCM que o fornecedor informou no XML da NF-e de entrada. Nos produtos abaixo, o NCM do cadastro foi alterado para o NCM do XML. Como o cadastro vale para o arquivo inteiro, o ajuste vale também para as saídas e para o inventário.</p></div>
<div class="leg"><b>Como ler a lista</b><br>NCM riscado = como estava no SPED · NCM em verde = como ficou.<br>A referência mostra a nota do fornecedor usada no ajuste e, quando houver, o efeito na substituição tributária de RO.</div></div>
<div class="lst"><h2>Produtos alterados</h2>
<table><thead><tr><th>Código</th><th>Produto</th><th>NCM anterior → novo</th><th>Referência</th></tr></thead><tbody>${linhas}</tbody></table></div>
<div class="rec"><i>!</i><div><b>Recomendação:</b> atualize o NCM destes produtos no cadastro do seu sistema de vendas (ERP), para que os próximos arquivos já saiam corretos e as notas de saída levem a classificação certa. Em caso de dúvida sobre a classificação de algum produto, fale com a nossa equipe.</div></div>
<div class="base"><b>Base:</b> Guia Prático da EFD ICMS/IPI — Registro 0200 (Tabela de Identificação do Item), campo 08 – COD_NCM. A classificação fiscal é de responsabilidade do contribuinte; neste ajuste foi adotado o NCM informado pelo fornecedor no XML da NF-e.</div>
</body></html>`;
}
const rodape = (hoje) => `<div style="width:100%;font-size:7.5px;color:#9aa0b6;padding:0 13mm;display:flex;justify-content:space-between;font-family:Segoe UI,Arial,sans-serif"><span>Liddera | Inteligência em Negócios · informativo gerado pelo FiscoCont+ em ${hoje}</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>`;
module.exports = { html, rodape, periodo };
