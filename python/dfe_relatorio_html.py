# -*- coding: utf-8 -*-
"""Modelo da página do Relatório DF-e (dfe_relatorio.py). Página única, sem internet: CSS, SVG e JS aqui dentro."""

HTML = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITULO__</title>
<style>
:root{color-scheme:light;
  --bg:#f3f4f8;--surface:#ffffff;--surface2:#f7f8fb;--line:#e4e6ee;--grid:#eceef4;
  --ink:#141a33;--ink2:#545b73;--ink3:#8a90a6;
  --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;
  --bad:#c93a3a;--badbg:#fdecec;--head1:#18214a;--head2:#2b3a72;--brand:#e8632b;
  --shadow:0 1px 2px rgba(20,26,51,.05),0 8px 24px rgba(20,26,51,.06)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
  --bg:#101219;--surface:#191c26;--surface2:#1f2330;--line:#2b3040;--grid:#262a38;
  --ink:#eef0f6;--ink2:#b5bacb;--ink3:#80869b;
  --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--bad:#e66767;--badbg:#3a1d22;--shadow:none}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#101219;--surface:#191c26;--surface2:#1f2330;--line:#2b3040;--grid:#262a38;
  --ink:#eef0f6;--ink2:#b5bacb;--ink3:#80869b;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--bad:#e66767;--badbg:#3a1d22;--shadow:none}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 "Segoe UI",Inter,system-ui,-apple-system,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1280px;margin:0 auto;padding:0 24px 40px}
header{background:radial-gradient(1200px 300px at 85% -40%,rgba(232,99,43,.35),transparent 60%),linear-gradient(120deg,var(--head1),var(--head2));color:#fff;padding:30px 0 74px}
header .wrap{padding-bottom:0;display:flex;gap:24px;align-items:flex-end;flex-wrap:wrap}
.h-tag{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:#c9cdf0;font-weight:600}
.h-tag i{width:8px;height:8px;border-radius:50%;background:var(--brand);box-shadow:0 0 0 4px rgba(232,99,43,.25)}
h1{margin:8px 0 4px;font-size:28px;line-height:1.15;font-weight:700;letter-spacing:-.01em}
.h-sub{color:#c9cdf0;font-size:13.5px}
.h-sp{flex:1}
.h-meta{display:flex;gap:10px;flex-wrap:wrap}
.h-pill{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:8px 14px;font-size:12px;color:#dfe2fb}
.h-pill b{display:block;font-size:16px;color:#fff;font-weight:700;margin-top:1px}
main{margin-top:-52px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}
.kpi{padding:16px 18px 12px;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c)}
.kpi-n{font-size:12.5px;color:var(--ink2);font-weight:600;display:flex;align-items:center;gap:8px}
.kpi-n .dot{width:9px;height:9px;border-radius:3px;background:var(--c)}
.kpi-v{font-size:25px;font-weight:700;letter-spacing:-.01em;margin:6px 0 2px;font-variant-numeric:tabular-nums}
.kpi-v small{font-size:14px;color:var(--ink3);font-weight:600;margin-right:3px}
.kpi-q{font-size:12.5px;color:var(--ink2)}.kpi-q b{color:var(--ink)}
.kpi-c{display:inline-block;margin-left:6px;font-size:11px;font-weight:700;color:var(--bad);background:var(--badbg);border-radius:10px;padding:1px 7px}
.kpi svg{display:block;width:100%;height:34px;margin-top:8px;clip-path:inset(0 100% 0 0);transition:clip-path 1.5s cubic-bezier(.3,.7,.2,1)}
.kpi svg.in{clip-path:inset(0 0 0 0)}
.kpi.vazio .kpi-v{color:var(--ink3);font-size:16px;font-weight:600;margin:12px 0 10px}
.grid{display:grid;gap:14px;margin-top:14px}
.g21{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}
.g11{grid-template-columns:repeat(2,minmax(0,1fr))}
.g111{grid-template-columns:repeat(3,minmax(0,1fr))}
.box{padding:18px 20px}
.box h2{margin:0;font-size:15px;font-weight:700}
.box .sub{font-size:12px;color:var(--ink3);margin:2px 0 12px}
.leg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--ink2);margin-bottom:6px}
.leg span{display:inline-flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
.leg span i{width:10px;height:10px;border-radius:3px;background:var(--c)}
.leg span.off{opacity:.38}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.ax text{fill:var(--ink3);font-size:11px}
.ax line{stroke:var(--grid);stroke-width:1}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:12px;
  box-shadow:0 8px 24px rgba(20,26,51,.16);opacity:0;transition:opacity .12s;min-width:160px;z-index:5;white-space:nowrap}
.tip b{display:block;margin-bottom:4px;font-size:12px}
.tip .r{display:flex;align-items:center;gap:7px;justify-content:space-between}.tip .r span{display:flex;align-items:center;gap:6px;color:var(--ink2)}
.tip .r i{width:8px;height:8px;border-radius:2px;background:var(--c)}
.tip .r em{font-style:normal;font-weight:600;font-variant-numeric:tabular-nums}
.ring{display:flex;flex-direction:column;align-items:center}
.ring svg{width:220px;height:220px}
.ring-c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
.ring-c small{font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.08em}
.ring-c b{font-size:19px;font-variant-numeric:tabular-nums}
.ring-wrap{position:relative;width:220px;height:220px;margin:4px auto 10px}
.ring-l{width:100%;font-size:12.5px}
.ring-l div{display:flex;align-items:center;gap:8px;padding:6px 2px;border-top:1px solid var(--line);cursor:default}
.ring-l div:first-child{border-top:none}
.ring-l i{width:10px;height:10px;border-radius:3px;background:var(--c);flex:none}
.ring-l span{flex:1;color:var(--ink2)}.ring-l b{font-variant-numeric:tabular-nums}.ring-l em{font-style:normal;color:var(--ink3);width:46px;text-align:right;font-size:11.5px}
.bars{display:flex;flex-direction:column;gap:9px}
.bar{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;font-size:12.5px;cursor:default}
.bar .nm{color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar .vl{color:var(--ink2);font-variant-numeric:tabular-nums;text-align:right}
.bar .tr{grid-column:1/3;height:8px;background:var(--surface2);border-radius:4px;overflow:hidden}
.bar .tr i{display:block;height:100%;width:0;background:var(--c);border-radius:0 4px 4px 0;transition:width 1s cubic-bezier(.2,.8,.2,1)}
.bar:hover .nm{text-decoration:underline;text-decoration-color:var(--line)}
.vazio-g{color:var(--ink3);font-size:12.5px;padding:18px 0;text-align:center}
.imp{width:100%;border-collapse:collapse;font-size:12.5px}
.imp th{text-align:right;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}
.imp th:first-child,.imp td:first-child{text-align:left}
.imp td{text-align:right;padding:8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.imp td i{display:inline-block;width:9px;height:9px;border-radius:3px;background:var(--c);margin-right:7px}
.lst .top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tab{border:1px solid var(--line);background:var(--surface2);color:var(--ink2);font:inherit;font-size:12.5px;padding:6px 12px;border-radius:18px;cursor:pointer;display:inline-flex;align-items:center;gap:7px}
.tab i{width:8px;height:8px;border-radius:2px;background:var(--c)}
.tab.on{background:var(--ink);color:var(--surface);border-color:var(--ink);font-weight:600}
.tab em{font-style:normal;opacity:.7;font-size:11.5px}
.busca{margin-left:auto;border:1px solid var(--line);background:var(--surface2);color:var(--ink);font:inherit;font-size:13px;padding:7px 12px;border-radius:10px;width:260px;max-width:100%}
.busca:focus{outline:2px solid var(--s1);outline-offset:1px}
.tw{overflow-x:auto}
table.l{width:100%;border-collapse:collapse;font-size:12.5px}
table.l th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3);font-weight:600;padding:8px;border-bottom:1.5px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}
table.l th.n,table.l td.n{text-align:right}
table.l th .so{opacity:.5;margin-left:3px}
table.l td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}
table.l tr:hover td{background:var(--surface2)}
table.l td .d{display:block;color:var(--ink3);font-size:11px}
table.l td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
table.l tfoot td{font-weight:700;border-top:1.5px solid var(--line);border-bottom:none}
.ch{font-family:Consolas,"Cascadia Mono",monospace;font-size:11px;color:var(--ink3)}
.lk{color:var(--s1);font-weight:600;text-decoration:none;margin-right:8px;font-size:12px}
.lk:hover{text-decoration:underline}
.cn{display:inline-block;font-size:10.5px;font-weight:700;color:var(--bad);background:var(--badbg);border-radius:9px;padding:1px 7px;margin-left:6px}
.pg{display:flex;align-items:center;gap:10px;justify-content:space-between;margin-top:12px;font-size:12.5px;color:var(--ink2)}
.pg button{border:1px solid var(--line);background:var(--surface2);color:var(--ink);font:inherit;font-size:12.5px;padding:6px 12px;border-radius:9px;cursor:pointer}
.pg button:disabled{opacity:.4;cursor:default}
footer{color:var(--ink3);font-size:11.5px;text-align:center;margin-top:22px}
.rv{opacity:0;transform:translateY(10px);transition:opacity .6s ease,transform .6s ease}
.rv.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){.rv{opacity:1;transform:none;transition:none}.kpi svg{clip-path:none;transition:none}.bar .tr i{transition:none}}
@media (max-width:980px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.g21,.g11,.g111{grid-template-columns:1fr}}
@media (max-width:560px){.wrap{padding:0 16px 30px}.kpis{grid-template-columns:1fr}h1{font-size:22px}.busca{width:100%}}
@media print{body{background:#fff}.kpi svg{clip-path:none}header{print-color-adjust:exact;-webkit-print-color-adjust:exact}.card{box-shadow:none;break-inside:avoid}.busca,.pg,.tabs{display:none}.rv{opacity:1;transform:none}}
</style></head>
<body>
<header><div class="wrap">
  <div><div class="h-tag"><i></i>Relatório DF-e · FiscoCont+</div>
  <h1 id="hEmp"></h1><div class="h-sub" id="hSub"></div></div>
  <div class="h-sp"></div>
  <div class="h-meta" id="hMeta"></div>
</div></header>
<main class="wrap">
  <section class="kpis" id="kpis"></section>
  <section class="grid g21">
    <div class="card box rv"><h2>Movimento por dia</h2><div class="sub">Valor das notas por data de emissão (canceladas fora)</div>
      <div class="leg" id="legDia"></div><div class="chart" id="cDia"></div></div>
    <div class="card box rv"><h2>Valor por tipo de documento</h2><div class="sub">Participação no total do mês</div>
      <div class="ring"><div class="ring-wrap"><svg id="cRing" viewBox="0 0 220 220" role="img" aria-label="Valor por tipo de documento"></svg><div class="ring-c"><small>Total</small><b id="ringTot"></b></div></div>
      <div class="ring-l" id="ringLeg"></div></div></div>
  </section>
  <section class="grid g11">
    <div class="card box rv"><h2>Principais fornecedores</h2><div class="sub">NF-e de entrada, por valor</div><div class="bars" id="cForn"></div></div>
    <div class="card box rv"><h2>Principais clientes</h2><div class="sub">NF-e de saída, por valor</div><div class="bars" id="cCli"></div></div>
  </section>
  <section class="grid g111">
    <div class="card box rv"><h2>CFOP das entradas</h2><div class="sub">NF-e e CT-e de entrada, por valor</div><div class="bars" id="cCfE"></div></div>
    <div class="card box rv"><h2>CFOP das saídas</h2><div class="sub">NF-e de saída, por valor dos produtos</div><div class="bars" id="cCfS"></div></div>
    <div class="card box rv"><h2>Origem das entradas</h2><div class="sub">UF do emitente das NF-e de entrada</div><div class="bars" id="cUf"></div></div>
  </section>
  <section class="grid">
    <div class="card box rv"><h2>Impostos destacados nas notas</h2><div class="sub">Soma dos totais dos XMLs, sem as canceladas</div>
      <div class="tw"><table class="imp" id="tImp"></table></div></div>
  </section>
  <section class="grid">
    <div class="card box lst rv"><div class="top"><div><h2>Notas do mês</h2></div></div>
      <div class="top"><div class="tabs" id="tabs"></div><input class="busca" id="busca" placeholder="Buscar número, chave, nome ou CNPJ"></div>
      <div class="tw"><table class="l" id="tLista"></table></div>
      <div class="pg"><span id="pgInfo"></span><span><button id="pgAnt">Anterior</button> <button id="pgProx">Próxima</button></span></div></div>
  </section>
  <footer id="rod"></footer>
</main>
<script>
const D = /*__DADOS__*/null;
(function(){
"use strict";
const COR=['var(--s1)','var(--s2)','var(--s3)','var(--s4)'];
const reduz=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
const $=(s)=>document.querySelector(s);
const esc=(s)=>String(s==null?'':s).replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const brl=(v)=>Number(v||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const curto=(v)=>{const a=Math.abs(v);if(a>=1e6)return (v/1e6).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mi';if(a>=1e3)return (v/1e3).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mil';return v.toLocaleString('pt-BR',{maximumFractionDigits:0});};
const docf=(d)=>{d=String(d||'');return d.length===14?d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,'$1.$2.$3/$4-$5'):d.length===11?d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/,'$1.$2.$3-$4'):d;};
const dataBr=(iso)=>iso?iso.split('-').reverse().join('/'):'';
const ENTRADA={'nfe-e':1,'cte-e':1};
// índices do item: 0 ch 1 n 2 serie 3 dia 4 emit 5 emitDoc 6 emitUf 7 dest 8 destDoc 9 destUf 10 valor 11 icms 12 st 13 ipi 14 canc 15 xml 16 pdf 17 cfops
const G=D.grupos.map((g,i)=>({...g,cor:COR[i],ativos:g.docs.filter((d)=>!d[14])}));
G.forEach((g)=>{g.valor=g.ativos.reduce((s,d)=>s+d[10],0);g.canc=g.docs.length-g.ativos.length;});
const [ano,mes]=D.compIso.split('-').map(Number);
const nDias=new Date(ano,mes,0).getDate();
const dias=Array.from({length:nDias},(_,i)=>i+1);
const porDia=(g)=>{const a=new Array(nDias).fill(0);g.ativos.forEach((d)=>{const m=String(d[3]).match(/^(\d{4})-(\d{2})-(\d{2})/);if(m&&+m[1]===ano&&+m[2]===mes)a[+m[3]-1]+=d[10];});return a;};
G.forEach((g)=>{g.dia=porDia(g);});

// cabeçalho
$('#hEmp').textContent=D.empresa;
$('#hSub').textContent=(D.cnpj?'CNPJ '+docf(D.cnpj)+' · ':'')+'Competência '+D.comp;
const totDocs=G.reduce((s,g)=>s+g.docs.length,0), totCanc=G.reduce((s,g)=>s+g.canc,0);
$('#hMeta').innerHTML=`<div class="h-pill">Documentos<b>${totDocs.toLocaleString('pt-BR')}</b></div><div class="h-pill">Canceladas<b>${totCanc.toLocaleString('pt-BR')}</b></div><div class="h-pill">Gerado em<b>${esc(D.gerado)}</b></div>`;
$('#rod').textContent='Relatório gerado pelo FiscoCont+ a partir dos XMLs baixados para esta pasta. Valores conforme os totais de cada documento.';
document.title=`Relatório DF-e · ${D.empresa} · ${D.comp}`;

// contagem animada
function conta(el,fim,fmt){if(reduz){el.textContent=fmt(fim);return;}const t0=performance.now(),dur=1300;
  const f=(t)=>{const p=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-p,4);el.textContent=fmt(fim*e);if(p<1)requestAnimationFrame(f);};requestAnimationFrame(f);}

// KPIs
const SO=(D.so&&D.so.length)?D.so:null,sel=(x)=>!SO||SO.includes(x.id);
if(SO){const t=document.querySelector('.h-tag');if(t)t.innerHTML='<i></i>Relatório '+esc(G.filter(sel).map((x)=>x.nome).join(' e '))+' · FiscoCont+';document.title=document.title.replace('DF-e',G.filter(sel).map((x)=>x.nome).join(' e '));}
$('#kpis').innerHTML=G.filter(sel).map((g,i)=>{
  if(!g.docs.length)return `<div class="card kpi vazio rv" style="--c:${g.cor}"><div class="kpi-n"><i class="dot"></i>${esc(g.nome)}</div><div class="kpi-v">Sem notas no mês</div><div class="kpi-q">Nenhum XML nesta pasta</div></div>`;
  const mx=Math.max(...g.dia,1),w=200,h=34;
  const pts=g.dia.map((v,k)=>[(k/(nDias-1))*w,h-2-(v/mx)*(h-6)]);
  const p='M'+pts.map((q)=>q[0].toFixed(1)+','+q[1].toFixed(1)).join(' L');
  return `<div class="card kpi rv" style="--c:${g.cor}"><div class="kpi-n"><i class="dot"></i>${esc(g.nome)}</div>
    <div class="kpi-v"><small>R$</small><span data-v="${g.valor}">0,00</span></div>
    <div class="kpi-q"><b>${g.ativos.length.toLocaleString('pt-BR')}</b> ${g.tipo==='cte'?'conhecimento(s)':g.tipo==='nfce'?'cupom(ns)':'nota(s)'}${g.canc?`<span class="kpi-c">${g.canc} cancelada(s)</span>`:''}</div>
    <svg class="sk" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${p} L${w},${h} L0,${h} Z" fill="${g.cor}" opacity=".12"/><path class="spk" d="${p}" fill="none" stroke="${g.cor}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg></div>`;
}).join('');

// movimento por dia (linhas)
const visivel=G.map((g)=>g.docs.length>0);
function desenhaDia(anima){
  const box=$('#cDia'),W=760,H=270,L=58,R=10,T=10,B=26,iw=W-L-R,ih=H-T-B;
  const ser=G.map((g,i)=>({g,i})).filter((s)=>visivel[s.i]);
  let mx=Math.max(1,...ser.flatMap((s)=>s.g.dia));
  const ord=Math.pow(10,Math.floor(Math.log10(mx))),passo=[1,2,2.5,5,10].map((k)=>k*ord).find((p)=>mx/p<=5)||ord*10;mx=Math.ceil(mx/passo)*passo;
  const x=(d)=>L+(d-1)/(nDias-1)*iw,y=(v)=>T+ih-(v/mx)*ih;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Movimento por dia"><g class="ax">`;
  for(let v=0;v<=mx+1e-6;v+=passo)s+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end">${curto(v)}</text>`;
  dias.forEach((d)=>{if(d===1||d%5===0||d===nDias)s+=`<text x="${x(d)}" y="${H-6}" text-anchor="middle">${String(d).padStart(2,'0')}</text>`;});
  s+='</g>';
  ser.forEach(({g})=>{const p='M'+g.dia.map((v,k)=>x(k+1).toFixed(1)+','+y(v).toFixed(1)).join(' L');
    s+=`<path d="${p} L${x(nDias)},${y(0)} L${x(1)},${y(0)} Z" fill="${g.cor}" opacity=".07"/><path class="ln" d="${p}" fill="none" stroke="${g.cor}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;});
  s+=`<line id="cx" x1="0" x2="0" y1="${T}" y2="${T+ih}" stroke="var(--ink3)" stroke-dasharray="3 3" opacity="0"/>`;
  ser.forEach(({g,i})=>{s+=`<circle class="pt" data-i="${i}" r="4.5" fill="${g.cor}" stroke="var(--surface)" stroke-width="2" opacity="0"/>`;});
  s+=`<rect id="hit" x="${L}" y="${T}" width="${iw}" height="${ih}" fill="transparent"/></svg><div class="tip" id="tipDia"></div>`;
  box.innerHTML=s;
  if(anima&&!reduz)box.querySelectorAll('.ln').forEach((p,k)=>{const len=p.getTotalLength();p.style.strokeDasharray=len;p.style.strokeDashoffset=len;p.getBoundingClientRect();p.style.transition=`stroke-dashoffset 1.6s cubic-bezier(.3,.7,.2,1) ${k*.12}s`;p.style.strokeDashoffset=0;});
  const svg=box.querySelector('svg'),tip=$('#tipDia'),cx=box.querySelector('#cx');
  const mostra=(ev)=>{const r=svg.getBoundingClientRect(),px=(ev.clientX-r.left)/r.width*W;const d=Math.max(1,Math.min(nDias,Math.round((px-L)/iw*(nDias-1))+1));
    cx.setAttribute('x1',x(d));cx.setAttribute('x2',x(d));cx.setAttribute('opacity',1);
    box.querySelectorAll('.pt').forEach((c)=>{const g=G[+c.dataset.i];c.setAttribute('cx',x(d));c.setAttribute('cy',y(g.dia[d-1]));c.setAttribute('opacity',1);});
    tip.innerHTML=`<b>${String(d).padStart(2,'0')}/${String(mes).padStart(2,'0')}/${ano}</b>`+ser.map(({g})=>`<div class="r"><span><i style="--c:${g.cor}"></i>${esc(g.nome)}</span><em>R$ ${brl(g.dia[d-1])}</em></div>`).join('');
    const tx=x(d)/W*r.width;tip.style.left=(tx>r.width*.6?tx-tip.offsetWidth-14:tx+14)+'px';tip.style.top='8px';tip.style.opacity=1;};
  svg.querySelector('#hit').addEventListener('mousemove',mostra);
  svg.querySelector('#hit').addEventListener('mouseleave',()=>{tip.style.opacity=0;cx.setAttribute('opacity',0);box.querySelectorAll('.pt').forEach((c)=>c.setAttribute('opacity',0));});
}
$('#legDia').innerHTML=G.map((g,i)=>g.docs.length?`<span data-i="${i}" style="--c:${g.cor}" title="Mostrar ou esconder"><i></i>${esc(g.nome)}</span>`:'').join('');
$('#legDia').addEventListener('click',(ev)=>{const s=ev.target.closest('span');if(!s)return;const i=+s.dataset.i;visivel[i]=!visivel[i];if(!visivel.some(Boolean)){visivel[i]=true;return;}s.classList.toggle('off',!visivel[i]);desenhaDia(false);});

// anel (valor por tipo)
function desenhaAnel(){
  const svg=$('#cRing'),tot=G.reduce((s,g)=>s+g.valor,0),C=110,R=84,SW=26,circ=2*Math.PI*R;
  $('#ringTot').textContent='R$ '+curto(tot);
  $('#ringLeg').innerHTML=G.filter(sel).map((g)=>`<div title="${esc(g.nome)}: R$ ${brl(g.valor)}"><i style="--c:${g.cor}"></i><span>${esc(g.nome)}</span><b>R$ ${brl(g.valor)}</b><em>${tot?(g.valor/tot*100).toLocaleString('pt-BR',{maximumFractionDigits:1}):0}%</em></div>`).join('');
  let s=`<circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="var(--surface2)" stroke-width="${SW}"/>`;
  const fat=G.filter((g)=>g.valor>0),gap=fat.length>1?3:0;
  let ini=0;fat.forEach((g,k)=>{const frac=g.valor/tot,len=Math.max(0,frac*circ-gap);
    s+=`<circle class="arc" data-len="${len}" data-ini="${ini}" cx="${C}" cy="${C}" r="${R}" fill="none" stroke="${g.cor}" stroke-width="${SW}" stroke-dasharray="0 ${circ}" stroke-dashoffset="${-ini}" transform="rotate(-90 ${C} ${C})"><title>${esc(g.nome)}: R$ ${brl(g.valor)}</title></circle>`;ini+=frac*circ;});
  svg.innerHTML=s;
  const arcs=[...svg.querySelectorAll('.arc')];
  const pinta=(p)=>arcs.forEach((a)=>{const l=+a.dataset.len,i0=+a.dataset.ini,vis=Math.max(0,Math.min(l,p*circ-i0));a.setAttribute('stroke-dasharray',`${vis} ${circ}`);});
  if(reduz){pinta(1);return;}const t0=performance.now();const f=(t)=>{const p=Math.min(1,(t-t0)/1400),e=1-Math.pow(1-p,3);pinta(e);if(p<1)requestAnimationFrame(f);};requestAnimationFrame(f);
}

// barras horizontais
function barras(el,lista,cor,vazio){
  if(!lista.length){el.innerHTML=`<div class="vazio-g">${vazio}</div>`;return;}
  const mx=lista[0].v||1;
  el.innerHTML=lista.map((b)=>`<div class="bar" title="${esc(b.t||b.n)}: R$ ${brl(b.v)}${b.q?` · ${b.q} documento(s)`:''}"><span class="nm">${esc(b.n)}</span><span class="vl">R$ ${brl(b.v)}</span><span class="tr"><i style="--c:${cor}" data-w="${(b.v/mx*100).toFixed(2)}"></i></span></div>`).join('');
}
const somaPor=(docs,chave,nome)=>{const m=new Map();docs.forEach((d)=>{const k=chave(d);if(!k)return;const o=m.get(k)||{n:nome(d),v:0,q:0,t:''};o.v+=d[10];o.q++;m.set(k,o);});return [...m.values()].sort((a,b)=>b.v-a.v);};
const top=(l,n)=>l.length>n?[...l.slice(0,n-1),{n:`Outros (${l.length-n+1})`,v:l.slice(n-1).reduce((s,x)=>s+x.v,0)}]:l;
const g=(id)=>G.find((x)=>x.id===id);
barras($('#cForn'),top(somaPor(g('nfe-e').ativos,(d)=>d[5]||d[4],(d)=>d[4]||docf(d[5])),8),G[0].cor,'Sem NF-e de entrada no mês');
barras($('#cCli'),top(somaPor(g('nfe-s').ativos,(d)=>d[8]||d[7],(d)=>d[7]||docf(d[8])||'Sem destinatário'),8),G[2].cor,'Sem NF-e de saída no mês');
const cfop=(docs)=>{const m=new Map();docs.forEach((d)=>Object.entries(d[17]||{}).forEach(([c,v])=>m.set(c,(m.get(c)||0)+v)));return [...m.entries()].map(([n,v])=>({n,v})).sort((a,b)=>b.v-a.v);};
barras($('#cCfE'),top(cfop([...g('nfe-e').ativos,...g('cte-e').ativos]),7),G[0].cor,'Sem entradas no mês');
barras($('#cCfS'),top(cfop(g('nfe-s').ativos),7),G[2].cor,'Sem NF-e de saída no mês');
barras($('#cUf'),top(somaPor(g('nfe-e').ativos,(d)=>d[6],(d)=>d[6]),7),G[0].cor,'Sem NF-e de entrada no mês');
if(SO){[['#cForn',['nfe-e']],['#cCli',['nfe-s']],['#cCfE',['nfe-e','cte-e']],['#cCfS',['nfe-s']],['#cUf',['nfe-e']]].forEach(([q,ids])=>{if(!ids.some((i)=>SO.includes(i))){const c=$(q).closest('.card');if(c)c.style.display='none';}});
  document.querySelectorAll('section.grid').forEach((sc)=>{if(sc.querySelector('.card')&&![...sc.querySelectorAll('.card')].some((c)=>c.style.display!=='none'))sc.style.display='none';});}

// impostos
$('#tImp').innerHTML='<thead><tr><th>Documento</th><th>Valor total</th><th>ICMS</th><th>ICMS ST</th><th>IPI</th></tr></thead><tbody>'+G.filter(sel).map((x)=>{
  const s=(k)=>x.ativos.reduce((a,d)=>a+d[k],0);
  return `<tr><td><i style="--c:${x.cor}"></i>${esc(x.nome)}</td><td>R$ ${brl(x.valor)}</td><td>R$ ${brl(s(11))}</td><td>${x.tipo==='cte'?'—':'R$ '+brl(s(12))}</td><td>${x.tipo==='cte'||x.tipo==='nfce'?'—':'R$ '+brl(s(13))}</td></tr>`;}).join('')+'</tbody>';

// lista das notas
const L={g:G.findIndex((x)=>x.docs.length)>=0?G.findIndex((x)=>x.docs.length):0,q:'',pg:0,ord:'dia',asc:true,por:50};
// na cópia da pasta do cliente os XML/PDF estão dentro dos zips: sem a coluna de arquivos
const temArq=G.some((x)=>x.docs.some((d)=>d[15]));
const COLS=[{k:'n',t:'Nº / série'},{k:'dia',t:'Emissão'},{k:'part',t:'Emitente / destinatário'},{k:'uf',t:'UF'},{k:'valor',t:'Valor',n:1},{k:'icms',t:'ICMS',n:1},...(temArq?[{k:'arq',t:'Arquivos'}]:[])];
function linhas(){const x=G[L.g],ent=!!ENTRADA[x.id],q=L.q.trim().toLowerCase().replace(/[.\-\/]/g,'');
  let ds=x.docs.map((d)=>({d,n:+d[1]||0,dia:d[3],part:ent?d[4]:(d[7]||'Consumidor'),doc:ent?d[5]:d[8],uf:ent?d[6]:d[9],valor:d[10],icms:d[11]}));
  if(q)ds=ds.filter((r)=>(r.d[1]+' '+r.d[0]+' '+r.part+' '+r.doc).toLowerCase().replace(/[.\-\/]/g,'').includes(q));
  const k=L.ord;ds.sort((a,b)=>{const va=a[k]??'',vb=b[k]??'';return (va>vb?1:va<vb?-1:0)*(L.asc?1:-1);});return ds;}
function lista(){
  $('#tabs').innerHTML=G.map((x,i)=>sel(x)?`<button class="tab ${i===L.g?'on':''}" data-i="${i}" style="--c:${x.cor}"><i></i>${esc(x.nome)} <em>${x.docs.length.toLocaleString('pt-BR')}</em></button>`:'').join('');
  const ds=linhas(),x=G[L.g],paginas=Math.max(1,Math.ceil(ds.length/L.por));L.pg=Math.min(L.pg,paginas-1);
  const pag=ds.slice(L.pg*L.por,(L.pg+1)*L.por);
  const th=COLS.map((c)=>`<th class="${c.n?'n':''}" data-k="${c.k}">${c.t}${L.ord===c.k?`<span class="so">${L.asc?'▲':'▼'}</span>`:''}</th>`).join('');
  const tb=pag.map((r)=>{const d=r.d;return `<tr><td><b>${esc(d[1])}</b>${d[2]?` <span class="ch">/${esc(d[2])}</span>`:''}${d[14]?'<span class="cn">CANCELADA</span>':''}<span class="d ch">${esc(d[0])}</span></td>
    <td>${dataBr(d[3])}</td><td>${esc(r.part)}<span class="d">${esc(docf(r.doc))}</span></td><td>${esc(r.uf)}</td>
    <td class="n">R$ ${brl(d[10])}</td><td class="n">R$ ${brl(d[11])}</td>
    ${temArq?`<td>${d[15]?`<a class="lk" href="${encodeURI(d[15])}">XML</a>`:''}${d[16]?`<a class="lk" href="${encodeURI(d[16])}">PDF</a>`:''}</td>`:''}</tr>`;}).join('');
  const at=ds.filter((r)=>!r.d[14]);
  const ft=ds.length?`<tfoot><tr><td colspan="4">${ds.length.toLocaleString('pt-BR')} documento(s)${ds.length!==at.length?` · total sem as ${ds.length-at.length} cancelada(s)`:''}</td><td class="n">R$ ${brl(at.reduce((s,r)=>s+r.valor,0))}</td><td class="n">R$ ${brl(at.reduce((s,r)=>s+r.icms,0))}</td>${temArq?'<td></td>':''}</tr></tfoot>`:'';
  $('#tLista').innerHTML=`<thead><tr>${th}</tr></thead><tbody>${tb||`<tr><td colspan="${COLS.length}" class="vazio-g">${x.docs.length?'Nada encontrado na busca':'Sem documentos deste tipo no mês'}</td></tr>`}</tbody>${ft}`;
  $('#pgInfo').textContent=ds.length?`Mostrando ${(L.pg*L.por+1).toLocaleString('pt-BR')}–${Math.min(ds.length,(L.pg+1)*L.por).toLocaleString('pt-BR')} de ${ds.length.toLocaleString('pt-BR')}`:'';
  $('#pgAnt').disabled=L.pg<=0;$('#pgProx').disabled=L.pg>=paginas-1;
}
$('#tabs').addEventListener('click',(ev)=>{const b=ev.target.closest('.tab');if(b){L.g=+b.dataset.i;L.pg=0;lista();}});
$('#tLista').addEventListener('click',(ev)=>{const th=ev.target.closest('th');if(!th||th.dataset.k==='arq')return;const k=th.dataset.k;L.asc=L.ord===k?!L.asc:!(k==='valor'||k==='icms');L.ord=k;lista();});
$('#busca').addEventListener('input',(ev)=>{L.q=ev.target.value;L.pg=0;lista();});
$('#pgAnt').addEventListener('click',()=>{L.pg--;lista();});$('#pgProx').addEventListener('click',()=>{L.pg++;lista();});
lista();

// entrada animada quando cada bloco aparece
let feito={};
const ativa=(el)=>{el.classList.add('in');
  el.querySelectorAll('[data-v]').forEach((s)=>conta(s,+s.dataset.v,brl));
  el.querySelectorAll('.bar .tr i').forEach((b,k)=>setTimeout(()=>{b.style.width=b.dataset.w+'%';},reduz?0:k*60));
  el.querySelectorAll('svg.sk').forEach((v)=>{v.classList.add('in');});
  if(el.querySelector('#cDia')&&!feito.dia){feito.dia=1;desenhaDia(true);}
  if(el.querySelector('#cRing')&&!feito.anel){feito.anel=1;desenhaAnel();}};
const els=[...document.querySelectorAll('.rv')];
if('IntersectionObserver' in window&&!reduz){const io=new IntersectionObserver((es)=>es.forEach((e)=>{if(e.isIntersecting){io.unobserve(e.target);setTimeout(()=>ativa(e.target),(els.indexOf(e.target)%4)*90);}}),{threshold:.12});els.forEach((e)=>io.observe(e));}
else els.forEach(ativa);
window.addEventListener('beforeprint',()=>els.forEach((e)=>{if(!e.classList.contains('in'))ativa(e);}));
})();
</script></body></html>"""
