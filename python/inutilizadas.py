# -*- coding: utf-8 -*-
"""Inutilizadas × Domínio — explica cada numeração faltante do relatório "Notas não lançadas" do Domínio.

Fontes, nesta ordem:
  1) Relatório do Domínio "Notas não lançadas de Saídas/Entradas" (PDF): faixas Inicial a Final, Série e Espécie.
  2) Portal Nacional da NF-e — "Consultar Inutilização" (CNPJ do emitente + ano): a lista que o portal devolve depois que a
     pessoa marca o "Sou humano" (o sistema NÃO resolve CAPTCHA) — Ano, Modelo, Série, Número Inicial, Número Final, Protocolo,
     Data/Hora e Recebimento AN. Chega aqui já lida pelo Electron, em JSON.
  3) SPED Fiscal do cliente (opcional, um ou mais meses): C100 de emissão própria (IND_EMIT = 0) — COD_SIT 05 numeração
     inutilizada, 02/03 cancelada, 04 denegada, demais = documento escriturado (Guia Prático da EFD ICMS/IPI, C100, campo
     COD_SIT; tabela 4.1.2).

Cada número faltante recebe UMA situação, com o motivo; nada é "verificar".
"""
import json
import re
import sys
from collections import Counter, defaultdict

ESPECIE_MOD = (('NFC-E', '65'), ('CONSUMIDOR', '65'), ('NOTA FISCAL ELETR', '55'), ('NF-E', '55'), ('CONHECIMENTO', '57'),
               ('CT-E', '57'), ('NFCOM', '62'), ('NF3E', '66'), ('ENERGIA', '66'))
MOD_NOME = {'55': 'NF-e', '65': 'NFC-e', '57': 'CT-e', '62': 'NFCom', '66': 'NF3e'}
SIT = {
    'portal': ('Inutilizada no portal', '#1baf7a'),
    'cancelada': ('Cancelada no SPED do cliente', '#64748b'),
    'denegada': ('Denegada no SPED do cliente', '#94a3b8'),
    'sped_inut': ('Inutilizada só no SPED do cliente', '#eda100'),
    'escriturada': ('Escriturada no SPED, não lançada no Domínio', '#2f4090'),
    'sem_registro': ('Sem registro em nenhuma fonte', '#e34948'),
    'pendente': ('Não inutilizada no portal · falta o SPED do cliente', '#c084fc'),
    'sem_portal': ('Portal ainda não consultado', '#cbd5e1'),
}
ORDEM = list(SIT)


def _so(s):
    return re.sub(r'\D', '', s or '')


def _int(s):
    s = _so(s)
    return int(s) if s else 0


def _modelo(especie):
    e = (especie or '').upper()
    for chave, mod in ESPECIE_MOD:
        if chave in e:
            return mod
    return ''


def ler_dominio(caminho):
    """Lê o PDF "Notas não lançadas" do Domínio."""
    import pdfplumber
    out = {'empresa': '', 'cnpj': '', 'ie': '', 'tipo': '', 'faixas': []}
    rx = re.compile(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*$')
    with pdfplumber.open(caminho) as pdf:
        for pg in pdf.pages:
            for ln in (pg.extract_text() or '').splitlines():
                if ln.startswith('Empresa:') and not out['empresa']:
                    out['empresa'] = re.sub(r'\s+Emiss[ãa]o:.*$', '', ln[8:]).strip()
                elif ln.startswith('CNPJ:') and not out['cnpj']:
                    out['cnpj'] = _so(ln.split('Página')[0])[:14]
                elif ln.startswith('Insc. Est.:') and not out['ie']:
                    out['ie'] = _so(ln)
                elif 'Notas não lançadas' in ln and not out['tipo']:
                    out['tipo'] = 'Entradas' if 'Entrada' in ln else 'Saídas'
                else:
                    m = rx.match(ln)
                    if m and not ln.startswith('Inicial'):
                        ini, fim, serie, esp = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                        if fim >= ini and fim - ini < 100000:
                            out['faixas'].append({'ini': ini, 'fim': fim, 'serie': serie, 'especie': esp, 'modelo': _modelo(esp)})
    if not out['faixas']:
        raise ValueError('Não encontrei as faixas de numeração no PDF. Use o relatório "Notas não lançadas" do Domínio.')
    return out


def ler_sped(caminhos):
    """{(modelo, série, número): {...}} das notas de emissão própria (C100 IND_EMIT = 0)."""
    import fiscal_core as fc
    idx, info = {}, []
    for c in caminhos or []:
        texto, _ = fc._ler_sped(c)
        per = cnpj = nome = ''
        for ln in texto.splitlines():
            if not ln.startswith('|'):
                continue
            f = ln.split('|')
            if f[1] == '0000':
                per = f'{f[4][2:4]}/{f[4][4:]}' if len(f) > 4 and len(f[4]) == 8 else ''
                nome, cnpj = (f[6] if len(f) > 6 else ''), (f[7] if len(f) > 7 else '')
            elif f[1] == 'C100' and len(f) > 9 and f[3] == '0':
                k = (f[5], _int(f[7]), _int(f[8]))
                idx[k] = {'sit': f[6], 'chave': f[9] if len(f) > 9 else '', 'data': f[10] if len(f) > 10 else '',
                          'valor': f[12] if len(f) > 12 else '', 'periodo': per}
        info.append({'arquivo': c.replace('\\', '/').split('/')[-1], 'periodo': per, 'cnpj': cnpj, 'empresa': nome})
    return idx, info


def _br_data(d):
    return f'{d[:2]}/{d[2:4]}/{d[4:]}' if len(d or '') == 8 else (d or '')


def conferir(dominio, portal=None, sped_idx=None, sped_info=None):
    # portal: lista de linhas, ou {'consultado': True, 'anos': ['2026'], 'linhas': [...]} (consulta feita, mesmo sem nenhuma inutilização)
    # 'fontes': portais consultados — 'nfe' (Portal Nacional da NF-e) e 'nfce-ro' (portal da NFC-e da SEFIN-RO)
    anos_cons, fontes = [], None
    if isinstance(portal, dict):
        consultado = bool(portal.get('consultado'))
        anos_cons = [str(a) for a in portal.get('anos') or []]
        if portal.get('fontes') is not None:
            fontes = set(portal.get('fontes') or [])
        portal = portal.get('linhas') or []
    else:
        portal = portal or []
        consultado = bool(portal)

    def _consultado(mod):
        if fontes is None:
            return consultado
        return ('nfce-ro' in fontes) if mod == '65' else ('nfe' in fontes)

    def _onde(mod):
        return 'no portal da NFC-e (SEFIN-RO)' if mod == '65' else 'no portal da NF-e'
    pf = defaultdict(list)
    for r in portal:
        pf[(str(r.get('modelo') or '').strip(), _int(r.get('serie')))].append(r)
    nums = []
    for fx in dominio['faixas']:
        for n in range(fx['ini'], fx['fim'] + 1):
            nums.append((fx['modelo'], fx['serie'], n, fx['especie']))
    res = []
    for mod, ser, n, esp in nums:
        sit, prot, data, obs = '', '', '', ''
        for r in pf.get((mod, ser), []):
            if _int(r.get('ini')) <= n <= _int(r.get('fim')):
                sit, prot, data = 'portal', r.get('protocolo', ''), r.get('data', '')
                obs = f"recebido no Ambiente Nacional em {r['receb']}" if r.get('receb') else ''
                break
        if not sit and sped_idx is not None:
            d = sped_idx.get((mod, ser, n))
            if d:
                cs = d['sit']
                if cs == '05':
                    sit, obs = 'sped_inut', f"situação 05 (numeração inutilizada) no SPED {d['periodo']}, mas não consta na consulta " + _onde(mod).replace('no ', 'do ', 1) + ' — pedir ao cliente o protocolo da inutilização'
                elif cs in ('02', '03'):
                    sit, obs = 'cancelada', f"situação {cs} no SPED {d['periodo']}: nota autorizada e cancelada — não é numeração faltante"
                elif cs == '04':
                    sit, obs = 'denegada', f"situação 04 no SPED {d['periodo']}: uso denegado — não é numeração faltante"
                else:
                    sit = 'escriturada'
                    obs = f"está no SPED do cliente ({d['periodo']}" + (f", emitida em {_br_data(d['data'])}" if d['data'] else '') + (
                        f", R$ {d['valor']}" if d['valor'] else '') + '): falta lançar no Domínio'
                    prot = d['chave']
        if not sit:
            if not _consultado(mod):
                sit, obs = 'sem_portal', ('consulte o portal da NFC-e de Rondônia (CNPJ e ano)' if mod == '65' else 'consulte o portal da NF-e (CNPJ e ano)')
            elif sped_idx is None:
                sit, obs = 'pendente', f'não está inutilizada {_onde(mod)}: importe o SPED Fiscal do cliente para conferir'
            else:
                sit, obs = 'sem_registro', f'não está inutilizada {_onde(mod)} nem no SPED do cliente: pedir ao cliente o XML da nota ou da inutilização'
        res.append({'modelo': mod, 'serie': ser, 'num': n, 'especie': esp, 'sit': sit, 'prot': prot, 'data': data, 'obs': obs})
    # junta de volta em faixas (números seguidos com a mesma situação e o mesmo protocolo)
    faixas = []
    for r in res:
        u = faixas[-1] if faixas else None
        if u and u['modelo'] == r['modelo'] and u['serie'] == r['serie'] and u['fim'] + 1 == r['num'] and u['sit'] == r['sit'] \
                and u['prot'] == r['prot'] and u['obs'] == r['obs'] and r['sit'] != 'escriturada':
            u['fim'] = r['num']
            u['qtd'] += 1
        else:
            faixas.append({'modelo': r['modelo'], 'serie': r['serie'], 'ini': r['num'], 'fim': r['num'], 'qtd': 1, 'sit': r['sit'],
                           'prot': r['prot'], 'data': r['data'], 'obs': r['obs'], 'especie': r['especie']})
    cont = Counter(r['sit'] for r in res)
    por_serie = defaultdict(Counter)
    for r in res:
        por_serie[(r['modelo'], r['serie'])][r['sit']] += 1
    anos = sorted(set(anos_cons) | {('20' + str(r['ano'])) if len(str(r.get('ano', ''))) == 2 else str(r['ano']) for r in portal if r.get('ano')})
    return {'empresa': dominio.get('empresa', ''), 'cnpj': dominio.get('cnpj', ''), 'ie': dominio.get('ie', ''),
            'tipo': dominio.get('tipo', ''), 'faixas_dominio': len(dominio['faixas']), 'numeros': len(res),
            'situacao': {k: cont.get(k, 0) for k in ORDEM if cont.get(k)},
            'por_serie': [{'modelo': m, 'serie': s, 'nome': f"{MOD_NOME.get(m, m or '?')} · série {s}", 'total': sum(c.values()),
                           'sit': dict(c)} for (m, s), c in sorted(por_serie.items(), key=lambda x: (x[0][0] != '55', x[0][0], x[0][1]))],
            'portal': {'consultado': consultado, 'fontes': sorted(fontes) if fontes is not None else (['nfe'] if consultado else []), 'qtd': len(portal), 'anos': anos,
                       'modelos': sorted({str(r.get('modelo', '')) for r in portal})},
            'sped': sped_info or [], 'faixas': faixas}


def _fmt_num(f):
    return f"{f['ini']}" if f['ini'] == f['fim'] else f"{f['ini']} a {f['fim']}"


HTML = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Inutilizadas × Domínio</title><style>
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Inter,Arial,sans-serif;background:#f4f6fb;color:#141b2d;padding:18px 22px;font-size:13px}
.kp{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}.kp div{background:#fff;border-radius:12px;padding:11px 13px;border-top:4px solid #c9cfdc;box-shadow:0 4px 14px rgba(20,27,45,.06);animation:sobe .45s both}
.kp span{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#5a6785}.kp b{display:block;font-size:24px;margin-top:2px}.kp small{font-size:11px;color:#5a6785}
.g2{display:grid;grid-template-columns:1fr 1.4fr;gap:14px;margin-bottom:14px}.c{background:#fff;border:1px solid #e8ebf3;border-radius:12px;padding:14px 16px;animation:sobe .5s both}.c h4{margin:0 0 10px;font-size:13.5px}
.dn{display:flex;align-items:center;gap:22px}.lgs{flex:1;display:flex;flex-direction:column;gap:12px}
.lg{display:grid;grid-template-columns:12px 1fr auto;gap:4px 9px;align-items:center;font-size:12.5px;cursor:pointer;border-radius:10px;padding:5px 7px;transition:background .2s,opacity .2s}
.lg:hover{background:#f4f6fb}.lg i{width:12px;height:12px;border-radius:4px}.lg b{font-size:15px;font-variant-numeric:tabular-nums}
.lg .br{grid-column:2/4;height:7px;background:#eef0f6;border-radius:8px;overflow:hidden}.lg .br em{display:block;height:100%;width:0;border-radius:8px}
.lg.apaga,.arco.apaga{opacity:.28}.arco{cursor:pointer;transition:opacity .25s}
#dn text{font-family:"Segoe UI",Inter,Arial,sans-serif}
.srg{display:grid;grid-template-columns:minmax(120px,auto) 1fr 66px;gap:16px 14px;align-items:center}.srl{display:flex;flex-direction:column;gap:3px;font-size:13px;font-weight:700}.srl small{font-weight:500;color:#5a6785;font-size:11.5px}.md{display:inline-block;font-size:10.5px;font-weight:800;letter-spacing:.03em;border-radius:6px;padding:2px 6px;color:#fff;margin-right:5px;background:#64748b}.sb{display:flex;gap:4px;height:34px}.sb i{display:flex;align-items:center;justify-content:flex-end;padding-right:9px;color:#fff;font-style:normal;font-weight:800;font-size:12.5px;border-radius:9px;overflow:hidden;white-space:nowrap;height:100%;width:0;min-width:0;cursor:pointer;transition:opacity .2s;font-variant-numeric:tabular-nums}.sb i.apaga{opacity:.28}.spc{text-align:right;font-size:18px;font-weight:800;font-variant-numeric:tabular-nums}.spc small{display:block;font-size:10.5px;color:#5a6785;font-weight:600}.slg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:11.5px;color:#475569;margin-top:14px}.slg span{display:flex;align-items:center;gap:5px}.slg i{width:9px;height:9px;border-radius:3px}
.tw{background:#fff;border:1px solid #e8ebf3;border-radius:12px;overflow:hidden;animation:sobe .55s both}.tb{display:flex;gap:7px;align-items:center;padding:10px 12px;border-bottom:1px solid #eef0f6;flex-wrap:wrap}
.f{border:1px solid #d8dcea;border-radius:999px;padding:5px 11px;font-size:11.5px;font-weight:600;color:#475569;cursor:pointer;user-select:none}.f.on{background:#1f2a5a;color:#fff;border-color:#1f2a5a}
.q{margin-left:auto;border:1px solid #d8dcea;border-radius:9px;padding:7px 10px;width:240px;font-size:12px;outline:0}
table{width:100%;border-collapse:collapse;font-size:12.3px}th{background:#f6f7fb;text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:#5a6785;padding:8px 10px;border-bottom:1px solid #e8ebf3;position:sticky;top:0}
td{padding:8px 10px;border-bottom:1px solid #f0f2f7;vertical-align:top}.mono{font-family:Consolas,monospace;font-weight:700;white-space:nowrap}.pl{display:inline-block;font-size:11px;font-weight:800;border-radius:999px;padding:3px 9px;white-space:nowrap;color:#fff}
.ob{color:#475569;max-width:430px}.mais{padding:10px;text-align:center;color:#5a6785;font-size:12px}
.src{font-size:11.5px;color:#5a6785;margin:-4px 0 12px;line-height:1.5}
@keyframes sobe{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.kp div,.c,.tw{animation:none}}
</style></head><body>
<div class="src" id="src"></div>
<div class="kp" id="kp"></div>
<div class="g2"><div class="c"><h4>Situação dos números faltantes</h4><div class="dn"><svg width="220" height="220" viewBox="0 0 220 220" id="dn"></svg><div class="lgs" id="lgs"></div></div></div>
<div class="c"><h4>Por modelo e série</h4><div id="series"></div></div></div>
<div class="tw"><div class="tb" id="fil"></div><table><thead><tr><th>Modelo</th><th style="text-align:center">Série</th><th>Número</th><th>Situação</th><th>Protocolo / chave</th><th>Data da inutilização</th><th>Observação</th></tr></thead><tbody id="tb"></tbody></table></div>
<script>
const D=/*DADOS*/;const S=/*SIT*/;const MN={'55':'NF-e','65':'NFC-e','57':'CT-e','62':'NFCom','66':'NF3e'};
const $=s=>document.querySelector(s);const e=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const n=v=>(v||0).toLocaleString('pt-BR');const sit=D.situacao;
const g=k=>sit[k]||0;
$('#src').innerHTML=`<b>${e(D.empresa)}</b> · CNPJ ${e(D.cnpj)} · relatório do Domínio: ${n(D.faixas_dominio)} faixa(s), ${n(D.numeros)} número(s) · portais: ${D.portal.consultado?`${e((D.portal.fontes||[]).map(f=>f==='nfce-ro'?'NFC-e RO':'NF-e').join(' e '))} · ${n(D.portal.qtd)} inutilização(ões) no ano ${e(D.portal.anos.join(', '))}`:'não consultados'} · SPED do cliente: ${D.sped.length?D.sped.map(s=>`${e(s.periodo)}${s.cnpj&&D.cnpj&&s.cnpj!==D.cnpj?' <b style="color:#b4234a">(outro CNPJ)</b>':''}`).join(', '):'não importado'}`;
const K=[['Números faltantes no Domínio',D.numeros,`${n(D.faixas_dominio)} faixa(s)`,'#c9cfdc'],['Inutilizados no portal',g('portal'),'com protocolo e data','#1baf7a'],
['Explicados pelo SPED',g('cancelada')+g('denegada')+g('sped_inut'),'cancelada · denegada · inutilizada','#64748b'],['Faltam lançar no Domínio',g('escriturada'),'estão no SPED do cliente','#2f4090'],
['Sem explicação ainda',g('sem_registro')+g('pendente')+g('sem_portal'),g('sem_registro')?'pedir ao cliente':(g('pendente')?'importe o SPED do cliente':'consulte o portal'),'#e34948']];
$('#kp').innerHTML=K.map(([t,v,s,c],i)=>`<div style="border-top-color:${c};animation-delay:${i*.06}s"><span>${t}</span><b>${n(v)}</b><small>${s}</small></div>`).join('');
// Anel segmentado (modelo A): pontas arredondadas, espaço entre as fatias, brilho e desenho animado com o número subindo
const tot=D.numeros||1,R=84,SW=22,TAU=Math.PI*2,CX=110;
const claro=(h,f)=>{const x=parseInt(h.slice(1),16),r=x>>16,g2=x>>8&255,b=x&255,m=v=>Math.round(v+(255-v)*f);return`rgb(${m(r)},${m(g2)},${m(b)})`};
const ents=Object.entries(sit).filter(([k,v])=>v>0);
const semExp=g('sem_registro')+g('pendente')+g('sem_portal'),expl=Math.round(100*(tot-semExp)/tot);
let defs='<defs><filter id="gl" filterUnits="userSpaceOnUse" x="0" y="0" width="220" height="220"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>';
ents.forEach(([k],i)=>{defs+=`<linearGradient id="gr${i}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${claro(S[k][1],.32)}"/><stop offset="1" stop-color="${S[k][1]}"/></linearGradient>`;});
defs+='</defs>';
$('#dn').innerHTML=defs+`<circle cx="${CX}" cy="${CX}" r="${R}" fill="none" stroke="#eef0f6" stroke-width="${SW}"/>`
 +ents.map(([k],i)=>`<path class="arco" data-k="${k}" fill="none" stroke="url(#gr${i})" stroke-width="${SW}" stroke-linecap="round" filter="url(#gl)"/>`).join('')
 +`<text x="${CX}" y="${CX+4}" text-anchor="middle" font-size="44" font-weight="800" fill="#141b2d" id="dnN">0</text>`
 +`<text x="${CX}" y="${CX+26}" text-anchor="middle" font-size="12" fill="#5a6785">números faltantes</text>`
 +`<text x="${CX}" y="${CX+45}" text-anchor="middle" font-size="12" font-weight="700" fill="${expl===100?'#109868':'#b45309'}" id="dnP" opacity="0">${expl}% explicados</text>`;
$('#lgs').innerHTML=ents.map(([k,v])=>`<div class="lg" data-k="${k}"><i style="background:${S[k][1]}"></i><span>${S[k][0]}</span><b data-v="${v}">0</b><div class="br"><em data-w="${100*v/tot}" style="background:linear-gradient(90deg,${claro(S[k][1],.32)},${S[k][1]})"></em></div></div>`).join('');
const arcoD=(a0,a1)=>{if(a1-a0<0.0005)a1=a0+0.0005;const p=a=>[CX+R*Math.cos(a-Math.PI/2),CX+R*Math.sin(a-Math.PI/2)];const[x0,y0]=p(a0),[x1,y1]=p(a1);return`M${x0.toFixed(2)} ${y0.toFixed(2)}A${R} ${R} 0 ${a1-a0>Math.PI?1:0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`};
const GAP=ents.length>1?(SW/R)+0.06:0;let ac=0;
// fatia pequena (ex.: 1 de 286) ganha um tamanho mínimo para não sumir nem encostar na vizinha; a diferença sai da maior
const MIN=GAP+0.07,ang=ents.map(([k,v])=>v/tot*TAU);
if(ents.length>1){let falta=0;ang.forEach((a,i)=>{if(a<MIN){falta+=MIN-a;ang[i]=MIN;}});const im=ang.indexOf(Math.max(...ang));ang[im]-=falta;}
const fat=ents.map(([k],i)=>{const a0=ac,a1=ac+ang[i];ac=a1;return{k,a0,a1}});
const pathEls=[...document.querySelectorAll('#dn .arco')],bs=[...document.querySelectorAll('.lg b')],ems=[...document.querySelectorAll('.lg em')];
const eo=x=>1-Math.pow(1-Math.max(0,Math.min(1,x)),3);
function quadro(t){
 const pr=eo(t/1.6)*TAU;
 fat.forEach((f,i)=>{const ini=f.a0+GAP/2,fimF=Math.max(ini,f.a1-GAP/2);const el=pathEls[i];
  if(ents.length===1&&pr>=TAU-1e-6){el.setAttribute('d',`M${CX} ${CX-R}A${R} ${R} 0 1 1 ${CX-0.01} ${CX-R}`);return;}
  if(pr<=ini){el.setAttribute('d','');return;} el.setAttribute('d',arcoD(ini,Math.min(fimF,pr)));});
 const k=eo(t/1.9);$('#dnN').textContent=n(Math.round(tot*k));
 $('#dnP').setAttribute('opacity',Math.max(0,Math.min(1,(t-1.7)/0.4)));
 bs.forEach((b,i)=>{const kk=eo((t-0.15-i*0.12)/1.3);b.textContent=n(Math.round(+b.dataset.v*kk));ems[i].style.width=(+ems[i].dataset.w*kk)+'%';});
}
const reduz=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if(reduz){quadro(9);}else{const t0=performance.now();const passo=now=>{const t=(now-t0)/1000;quadro(t);if(t<2.4)requestAnimationFrame(passo);else quadro(9);};requestAnimationFrame(passo);}
// Por modelo e série (modelo B): barra segmentada com o número dentro e o % já explicado
const SEMX=['sem_registro','pendente','sem_portal'],MC={'55':'#2f4090','65':'#7c3aed','57':'#0e7490'};
$('#series').innerHTML='<div class="srg">'+D.por_serie.map((s,i)=>{const ks=Object.keys(S).filter(k=>s.sit[k]);const m=ks.length;
 const ex=Math.round(100*(s.total-SEMX.reduce((a,k)=>a+(s.sit[k]||0),0))/s.total);
 return `<div class="srl"><span><span class="md" style="background:${MC[s.modelo]||'#64748b'}">${e(MN[s.modelo]||s.modelo||'?')}</span>série ${e(s.serie)}</span><small>${n(s.total)} número(s)</small></div>`
 +`<div class="sb">${ks.map(k=>{const p=100*s.sit[k]/s.total;return`<i data-k="${k}" data-v="${s.sit[k]}" data-w="calc(${p}% - ${(4*(m-1)*p/100).toFixed(2)}px)" data-p="${p}" style="background:linear-gradient(90deg,${claro(S[k][1],.32)},${S[k][1]})" title="${e(S[k][0])}: ${n(s.sit[k])}"></i>`}).join('')}</div>`
 +`<div class="spc" style="color:${ex===100?'#109868':'#b45309'}" data-ex="${ex}">0%<small>explicado</small></div>`}).join('')+'</div>'
 +'<div class="slg">'+Object.keys(S).filter(k=>sit[k]).map(k=>`<span><i style="background:${S[k][1]}"></i>${e(S[k][0])}</span>`).join('')+'</div>';
const segs=[...document.querySelectorAll('.sb i')],pcs=[...document.querySelectorAll('.spc')];
segs.forEach(x=>{x.style.width=x.dataset.w;x.dataset.px=x.getBoundingClientRect().width;x.style.width='0';x.style.minWidth='0';});
function quadroS(t){
 document.querySelectorAll('.sb').forEach((b,i)=>{const k=eo((t-0.25-i*0.15)/1.3);
  b.querySelectorAll('i').forEach(x=>{x.style.width=`calc((${x.dataset.w}) * ${k.toFixed(4)})`;x.style.minWidth=k>0.05?'6px':'0';x.textContent=(+x.dataset.px>=34&&k>0.45)?n(Math.round(+x.dataset.v*k)):'';});
  const pc=pcs[i];pc.firstChild.textContent=Math.round(+pc.dataset.ex*k)+'%';});
}
if(reduz){quadroS(9);}else{const t1=performance.now();const passoS=now=>{const t=(now-t1)/1000;quadroS(t);if(t<2.4)requestAnimationFrame(passoS);else quadroS(9);};requestAnimationFrame(passoS);}
let filtro='',busca='';
const FIL=[['','Todos'],...Object.keys(S).filter(k=>sit[k]).map(k=>[k,S[k][0]])];
$('#fil').innerHTML=FIL.map(([k,t])=>`<span class="f${k===''?' on':''}" data-k="${k}">${e(t)} (${k?n(D.faixas.filter(f=>f.sit===k).length):n(D.faixas.length)})</span>`).join('')+'<input class="q" id="q" placeholder="Buscar número, série ou protocolo">';
function desenha(){let L=D.faixas.filter(f=>(!filtro||f.sit===filtro)&&(!busca||`${f.ini} ${f.fim} ${f.serie} ${f.prot} ${f.obs}`.toLowerCase().includes(busca)||(f.ini<=+busca&&+busca<=f.fim)));
 $('#tb').innerHTML=L.slice(0,1500).map(f=>`<tr><td>${MN[f.modelo]||e(f.especie)}</td><td style="text-align:center">${f.serie}</td><td class="mono">${f.ini===f.fim?f.ini:f.ini+' a '+f.fim}${f.qtd>1?` <span style="color:#8a93a8;font-weight:400">(${f.qtd})</span>`:''}</td>
 <td><span class="pl" style="background:${S[f.sit][1]}">${e(S[f.sit][0])}</span></td><td class="mono" style="font-size:11.5px">${e(f.prot)||'—'}</td><td>${e(f.data)||'—'}</td><td class="ob">${e(f.obs)||'—'}</td></tr>`).join('')
 +(L.length>1500?`<tr><td colspan="7" class="mais">Mostrando 1.500 de ${n(L.length)} — a lista completa está no Excel.</td></tr>`:'')+(L.length?'':'<tr><td colspan="7" class="mais">Nada com esse filtro.</td></tr>');
 document.querySelectorAll('.f').forEach(x=>x.classList.toggle('on',x.dataset.k===filtro));
 document.querySelectorAll('.lg,.arco,.sb i').forEach(x=>x.classList.toggle('apaga',!!filtro&&x.dataset.k!==filtro));}
document.querySelectorAll('.f').forEach(x=>x.onclick=()=>{filtro=x.dataset.k;desenha();});
document.querySelectorAll('.lg,.arco,.sb i').forEach(x=>x.addEventListener('click',()=>{filtro=filtro===x.dataset.k?'':x.dataset.k;desenha();}));
$('#q').oninput=ev=>{busca=ev.target.value.trim().toLowerCase();desenha();};desenha();
</script></body></html>'''


def gerar_html(res, caminho):
    h = HTML.replace('/*DADOS*/', json.dumps(res, ensure_ascii=False).replace('</', '<\\/')).replace('/*SIT*/', json.dumps(SIT, ensure_ascii=False))
    with open(caminho, 'w', encoding='utf-8') as fh:
        fh.write(h)


def gerar_xlsx(res, caminho):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = 'Numeração faltante'
    ws.append([f"Inutilizadas × Domínio — {res['empresa']} · CNPJ {res['cnpj']}"])
    ws['A1'].font = Font(bold=True, size=13)
    ws.append([f"{res['numeros']} número(s) em {res['faixas_dominio']} faixa(s) do relatório do Domínio · portal: "
               + (f"{res['portal']['qtd']} inutilização(ões) ({', '.join(res['portal']['anos'])})" if res['portal']['consultado'] else 'não consultado')])
    ws.append([])
    cab = ['Modelo', 'Série', 'Número inicial', 'Número final', 'Quantidade', 'Situação', 'Protocolo / chave', 'Data da inutilização', 'Observação']
    ws.append(cab)
    for c in ws[4]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='1F2A5A')
    for f in res['faixas']:
        ws.append([MOD_NOME.get(f['modelo'], f['especie']), f['serie'], f['ini'], f['fim'], f['qtd'], SIT[f['sit']][0], f['prot'], f['data'], f['obs']])
    for col, w in zip('ABCDEFGHI', (9, 7, 14, 14, 11, 40, 48, 20, 90)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = 'A5'
    r = wb.create_sheet('Resumo')
    r.append(['Situação', 'Números'])
    for k, v in res['situacao'].items():
        r.append([SIT[k][0], v])
    r.append([])
    r.append(['Modelo e série', 'Números'] + [SIT[k][0] for k in ORDEM])
    for s in res['por_serie']:
        r.append([s['nome'], s['total']] + [s['sit'].get(k, 0) for k in ORDEM])
    for c in r[1]:
        c.font = Font(bold=True)
    r.column_dimensions['A'].width = 46
    for row in ws.iter_rows(min_row=5):
        row[8].alignment = Alignment(wrap_text=True, vertical='top')
    wb.save(caminho)


def main_cli(argv):
    def opt(nm, multi=False):
        if nm not in argv:
            return [] if multi else None
        i = argv.index(nm) + 1
        if not multi:
            return argv[i] if i < len(argv) else None
        out = []
        while i < len(argv) and not argv[i].startswith('--'):
            out.append(argv[i])
            i += 1
        return out
    js = opt('--json')
    try:
        dom = ler_dominio(opt('--dominio'))
        portal = []
        if opt('--portal'):
            with open(opt('--portal'), encoding='utf-8') as fh:
                portal = json.load(fh)
        speds = opt('--sped', True)
        idx, info = ler_sped(speds) if speds else (None, [])
        res = conferir(dom, portal, idx, info)
        if opt('--html'):
            gerar_html(res, opt('--html'))
        if opt('--xlsx'):
            gerar_xlsx(res, opt('--xlsx'))
        out = {k: v for k, v in res.items() if k != 'faixas'}
        out['faixas_n'] = len(res['faixas'])
    except Exception as e:
        out = {'erro': str(e)}
    with open(js, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))
