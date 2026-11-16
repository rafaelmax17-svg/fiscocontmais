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
    anos_cons = []
    if isinstance(portal, dict):
        consultado = bool(portal.get('consultado'))
        anos_cons = [str(a) for a in portal.get('anos') or []]
        portal = portal.get('linhas') or []
    else:
        portal = portal or []
        consultado = bool(portal)
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
                    sit, obs = 'sped_inut', f"situação 05 (numeração inutilizada) no SPED {d['periodo']}, mas não consta na consulta do portal" + (
                        ' da NF-e' if mod == '65' else '') + ' — pedir ao cliente o protocolo da inutilização'
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
            if not consultado:
                sit, obs = 'sem_portal', 'consulte o portal da NF-e (CNPJ e ano)'
            elif sped_idx is None:
                sit, obs = 'pendente', 'não está inutilizada no portal: importe o SPED Fiscal do cliente para conferir'
            else:
                sit, obs = 'sem_registro', 'não está inutilizada no portal nem no SPED do cliente: pedir ao cliente o XML da nota ou da inutilização'
                if mod == '65':
                    obs += ' (NFC-e: confirme se o portal da NF-e traz as inutilizações de NFC-e da empresa)'
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
            'portal': {'consultado': consultado, 'qtd': len(portal), 'anos': anos,
                       'modelos': sorted({str(r.get('modelo', '')) for r in portal})},
            'sped': sped_info or [], 'faixas': faixas}


def _fmt_num(f):
    return f"{f['ini']}" if f['ini'] == f['fim'] else f"{f['ini']} a {f['fim']}"


HTML = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Inutilizadas × Domínio</title><style>
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Inter,Arial,sans-serif;background:#f4f6fb;color:#141b2d;padding:18px 22px;font-size:13px}
.kp{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}.kp div{background:#fff;border-radius:12px;padding:11px 13px;border-top:4px solid #c9cfdc;box-shadow:0 4px 14px rgba(20,27,45,.06);animation:sobe .45s both}
.kp span{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:#5a6785}.kp b{display:block;font-size:24px;margin-top:2px}.kp small{font-size:11px;color:#5a6785}
.g2{display:grid;grid-template-columns:1fr 1.4fr;gap:14px;margin-bottom:14px}.c{background:#fff;border:1px solid #e8ebf3;border-radius:12px;padding:14px 16px;animation:sobe .5s both}.c h4{margin:0 0 10px;font-size:13.5px}
.dn{display:flex;align-items:center;gap:18px}.lgs{flex:1;display:flex;flex-direction:column;gap:8px}.lg{display:flex;gap:8px;align-items:center;font-size:12.5px;cursor:pointer;border-radius:8px;padding:2px 4px}.lg:hover{background:#f4f6fb}.lg i{width:11px;height:11px;border-radius:3px;flex:none}.lg span{flex:1}
.arco{transition:stroke-dasharray 1.1s cubic-bezier(.2,.8,.2,1)}
.sr{margin-bottom:12px}.sr .l{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:5px}.sr .l span{color:#5a6785}.sr .t{display:flex;height:16px;border-radius:999px;overflow:hidden;background:#eef0f6}.sr .t div{height:100%;width:0;transition:width 1s cubic-bezier(.2,.8,.2,1)}
.tw{background:#fff;border:1px solid #e8ebf3;border-radius:12px;overflow:hidden;animation:sobe .55s both}.tb{display:flex;gap:7px;align-items:center;padding:10px 12px;border-bottom:1px solid #eef0f6;flex-wrap:wrap}
.f{border:1px solid #d8dcea;border-radius:999px;padding:5px 11px;font-size:11.5px;font-weight:600;color:#475569;cursor:pointer;user-select:none}.f.on{background:#1f2a5a;color:#fff;border-color:#1f2a5a}
.q{margin-left:auto;border:1px solid #d8dcea;border-radius:9px;padding:7px 10px;width:240px;font-size:12px;outline:0}
table{width:100%;border-collapse:collapse;font-size:12.3px}th{background:#f6f7fb;text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:#5a6785;padding:8px 10px;border-bottom:1px solid #e8ebf3;position:sticky;top:0}
td{padding:8px 10px;border-bottom:1px solid #f0f2f7;vertical-align:top}.mono{font-family:Consolas,monospace;font-weight:700;white-space:nowrap}.pl{display:inline-block;font-size:11px;font-weight:800;border-radius:999px;padding:3px 9px;white-space:nowrap;color:#fff}
.ob{color:#475569;max-width:430px}.mais{padding:10px;text-align:center;color:#5a6785;font-size:12px}
.src{font-size:11.5px;color:#5a6785;margin:-4px 0 12px;line-height:1.5}
@keyframes sobe{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.kp div,.c,.tw{animation:none}.arco,.sr .t div{transition:none}}
</style></head><body>
<div class="src" id="src"></div>
<div class="kp" id="kp"></div>
<div class="g2"><div class="c"><h4>Situação dos números faltantes</h4><div class="dn"><svg width="190" height="190" viewBox="0 0 190 190" id="dn"></svg><div class="lgs" id="lgs"></div></div></div>
<div class="c"><h4>Por modelo e série</h4><div id="series"></div></div></div>
<div class="tw"><div class="tb" id="fil"></div><table><thead><tr><th>Modelo</th><th style="text-align:center">Série</th><th>Número</th><th>Situação</th><th>Protocolo / chave</th><th>Data da inutilização</th><th>Observação</th></tr></thead><tbody id="tb"></tbody></table></div>
<script>
const D=/*DADOS*/;const S=/*SIT*/;const MN={'55':'NF-e','65':'NFC-e','57':'CT-e','62':'NFCom','66':'NF3e'};
const $=s=>document.querySelector(s);const e=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const n=v=>(v||0).toLocaleString('pt-BR');const sit=D.situacao;
const g=k=>sit[k]||0;
$('#src').innerHTML=`<b>${e(D.empresa)}</b> · CNPJ ${e(D.cnpj)} · relatório do Domínio: ${n(D.faixas_dominio)} faixa(s), ${n(D.numeros)} número(s) · portal: ${D.portal.consultado?`${n(D.portal.qtd)} inutilização(ões) no ano ${e(D.portal.anos.join(', '))}${D.portal.qtd?` (modelo ${e(D.portal.modelos.join(', '))})`:''}`:'não consultado'} · SPED do cliente: ${D.sped.length?D.sped.map(s=>`${e(s.periodo)}${s.cnpj&&D.cnpj&&s.cnpj!==D.cnpj?' <b style="color:#b4234a">(outro CNPJ)</b>':''}`).join(', '):'não importado'}`;
const K=[['Números faltantes no Domínio',D.numeros,`${n(D.faixas_dominio)} faixa(s)`,'#c9cfdc'],['Inutilizados no portal',g('portal'),'com protocolo e data','#1baf7a'],
['Explicados pelo SPED',g('cancelada')+g('denegada')+g('sped_inut'),'cancelada · denegada · inutilizada','#64748b'],['Faltam lançar no Domínio',g('escriturada'),'estão no SPED do cliente','#2f4090'],
['Sem explicação ainda',g('sem_registro')+g('pendente')+g('sem_portal'),g('sem_registro')?'pedir ao cliente':(g('pendente')?'importe o SPED do cliente':'consulte o portal'),'#e34948']];
$('#kp').innerHTML=K.map(([t,v,s,c],i)=>`<div style="border-top-color:${c};animation-delay:${i*.06}s"><span>${t}</span><b>${n(v)}</b><small>${s}</small></div>`).join('');
const tot=D.numeros||1,R=72,C=2*Math.PI*R;let off=0,arcs='';
Object.entries(sit).forEach(([k,v])=>{const L=C*v/tot;arcs+=`<circle class="arco" data-l="${L}" data-k="${k}" cx="95" cy="95" r="${R}" fill="none" stroke="${S[k][1]}" stroke-width="28" stroke-dasharray="0 ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 95 95)" style="cursor:pointer"/>`;off+=L;});
$('#dn').innerHTML=`<circle cx="95" cy="95" r="${R}" fill="none" stroke="#eef0f6" stroke-width="28"/>${arcs}<text x="95" y="92" text-anchor="middle" font-size="30" font-weight="800">${n(D.numeros)}</text><text x="95" y="112" text-anchor="middle" font-size="11" fill="#5a6785">números</text>`;
$('#lgs').innerHTML=Object.entries(sit).map(([k,v])=>`<div class="lg" data-k="${k}"><i style="background:${S[k][1]}"></i><span>${S[k][0]}</span><b>${n(v)}</b></div>`).join('');
$('#series').innerHTML=D.por_serie.map(s=>`<div class="sr"><div class="l"><b>${e(s.nome)}</b><span>${n(s.total)} número(s)${s.sit.portal?` · ${n(s.sit.portal)} inutilizado(s) no portal`:''}</span></div><div class="t">${Object.keys(S).filter(k=>s.sit[k]).map(k=>`<div data-w="${100*s.sit[k]/s.total}" style="background:${S[k][1]}" title="${e(S[k][0])}: ${n(s.sit[k])}"></div>`).join('')}</div></div>`).join('');
requestAnimationFrame(()=>requestAnimationFrame(()=>{document.querySelectorAll('.arco').forEach((a,i)=>{a.style.transitionDelay=(i*.12)+'s';a.setAttribute('stroke-dasharray',`${a.dataset.l} ${C}`);});document.querySelectorAll('.sr .t div').forEach(d=>d.style.width=d.dataset.w+'%');}));
let filtro='',busca='';
const FIL=[['','Todos'],...Object.keys(S).filter(k=>sit[k]).map(k=>[k,S[k][0]])];
$('#fil').innerHTML=FIL.map(([k,t])=>`<span class="f${k===''?' on':''}" data-k="${k}">${e(t)} (${k?n(D.faixas.filter(f=>f.sit===k).length):n(D.faixas.length)})</span>`).join('')+'<input class="q" id="q" placeholder="Buscar número, série ou protocolo">';
function desenha(){let L=D.faixas.filter(f=>(!filtro||f.sit===filtro)&&(!busca||`${f.ini} ${f.fim} ${f.serie} ${f.prot} ${f.obs}`.toLowerCase().includes(busca)||(f.ini<=+busca&&+busca<=f.fim)));
 $('#tb').innerHTML=L.slice(0,1500).map(f=>`<tr><td>${MN[f.modelo]||e(f.especie)}</td><td style="text-align:center">${f.serie}</td><td class="mono">${f.ini===f.fim?f.ini:f.ini+' a '+f.fim}${f.qtd>1?` <span style="color:#8a93a8;font-weight:400">(${f.qtd})</span>`:''}</td>
 <td><span class="pl" style="background:${S[f.sit][1]}">${e(S[f.sit][0])}</span></td><td class="mono" style="font-size:11.5px">${e(f.prot)||'—'}</td><td>${e(f.data)||'—'}</td><td class="ob">${e(f.obs)||'—'}</td></tr>`).join('')
 +(L.length>1500?`<tr><td colspan="7" class="mais">Mostrando 1.500 de ${n(L.length)} — a lista completa está no Excel.</td></tr>`:'')+(L.length?'':'<tr><td colspan="7" class="mais">Nada com esse filtro.</td></tr>');
 document.querySelectorAll('.f').forEach(x=>x.classList.toggle('on',x.dataset.k===filtro));}
document.querySelectorAll('.f').forEach(x=>x.onclick=()=>{filtro=x.dataset.k;desenha();});
document.querySelectorAll('.lg,.arco').forEach(x=>x.addEventListener('click',()=>{filtro=filtro===x.dataset.k?'':x.dataset.k;desenha();}));
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
