# -*- coding: utf-8 -*-
"""Gera python/rtc_calc_dados.py a partir do banco oficial da Calculadora de Tributos da RFB (CBS/IBS/IS).

Uso:  python tools/gerar_rtc_calc.py <calc.db> [saida]

O calc.db é o SQLite montado com os scripts oficiais do código-fonte da calculadora
(sql/criacao + sql/manutencao V0001..Vnnnn). Só entram dados do banco — nada é digitado à mão.
"""
import base64
import json
import sqlite3
import sys
import zlib
from datetime import date

ORIG = sys.argv[1] if len(sys.argv) > 1 else '/tmp/calc/calc.db'
SAIDA = sys.argv[2] if len(sys.argv) > 2 else 'python/rtc_calc_dados.py'

c = sqlite3.connect(ORIG)
hoje = date.today().isoformat()


def _d(s):
    s = (s or '')[:10]
    return None if not s or s.startswith('9999') else s


ver = c.execute('select VRBD_VERSAO_BASE_DADO, VRBD_DATA, VRBD_DESCRICAO from VERSAO_BASE_DADO order by VRBD_ID desc limit 1').fetchone()

# tributos de cada situação tributária: IBS/CBS (2,3,4) × Imposto Seletivo (1)
trib_sitr = {}
for sitr, tb in c.execute('select TRST_SITR_ID, TRST_TBTO_ID from TRIBUTO_SITUACAO_TRIBUTARIA'):
    trib_sitr.setdefault(sitr, set()).add(tb)

usadas = {r[0] for r in c.execute('select distinct NCMA_CLTR_ID from NCM_APLICAVEL')}
# classificações oficiais de bens sem lista de NCM no banco (o enquadramento depende do produto ser o descrito)
extras_cd = ('200009', '200013', '200032', '200053')
usadas |= {r[0] for r in c.execute(f"select CLTR_ID from CLASSIFICACAO_TRIBUTARIA where CLTR_CD in ({','.join('?' * len(extras_cd))})"
                                    " and CLTR_SITR_ID in (select SITR_ID from SITUACAO_TRIBUTARIA where SITR_CD='200')", extras_cd)}

classes = {}
for (cid, cd, desc, sitr, anexo, ini, fim, sitr_cd, sitr_desc) in c.execute(
        'select CLTR_ID, CLTR_CD, CLTR_DESCRICAO, CLTR_SITR_ID, CLTR_ANEXO, CLTR_INICIO_VIGENCIA, CLTR_FIM_VIGENCIA, SITR_CD, SITR_DESCRICAO '
        'from CLASSIFICACAO_TRIBUTARIA join SITUACAO_TRIBUTARIA on SITR_ID = CLTR_SITR_ID'):
    if cid not in usadas:
        continue
    tbs = trib_sitr.get(sitr, set())
    red = {}
    for tb, v, ri, rf in c.execute('select PERE_TBTO_ID, PERE_VALOR, PERE_INICIO_VIGENCIA, PERE_FIM_VIGENCIA from PERCENTUAL_REDUCAO where PERE_CLTR_ID = ?', (cid,)):
        red.setdefault({2: 'cbs', 3: 'ibsuf', 4: 'ibsmun'}.get(tb, str(tb)), []).append((float(v), _d(ri), _d(rf)))
    classes[cid] = {'cd': cd, 'desc': (desc or '').strip(), 'cst': sitr_cd, 'cst_desc': sitr_desc, 'anexo': anexo or '',
                    'ini': _d(ini), 'fim': _d(fim), 'tributo': 'IS' if tbs == {1} else 'IBSCBS', 'red': red}

anexos = {aid: (num, item, (txt or '').strip()) for aid, num, item, txt in
          c.execute('select ANXO_ID, ANXO_NUMERO, ANXO_NUMERO_ITEM, ANXO_TEXTO_ITEM from ANEXO')}

aplic = [(i, ncm, cl, ax, _d(ini), _d(fim)) for i, ncm, cl, ax, ini, fim in
         c.execute('select NCMA_ID, NCMA_NCM_CD, NCMA_CLTR_ID, NCMA_ANXO_ID, NCMA_INICIO_VIGENCIA, NCMA_FIM_VIGENCIA from NCM_APLICAVEL order by NCMA_ID')]
excecoes = {}
for ncm, ida, ini, fim in c.execute('select ENCM_NCM_CD, ENCM_NCMA_ID, ENCM_INICIO_VIGENCIA, ENCM_FIM_VIGENCIA from EXCECAO_NCM_APLICAVEL'):
    excecoes.setdefault(ida, []).append((ncm, _d(ini), _d(fim)))

aliq_ref = [({2: 'cbs', 3: 'ibsuf', 4: 'ibsmun'}[tb], float(v), _d(ini), _d(fim)) for v, ini, fim, tb in
            c.execute('select ALRE_VALOR, ALRE_INICIO_VIGENCIA, ALRE_FIM_VIGENCIA, ALRE_TBTO_ID from ALIQUOTA_REFERENCIA')]

# Imposto Seletivo por produto (ad valorem / ad rem)
is_prod = {}
for ncm, ini, fim in c.execute('select AAVP_NCM_CD, AAVP_INICIO_VIGENCIA, AAVP_FIM_VIGENCIA from ALIQUOTA_AD_VALOREM_PRODUTO '
                               'union all select AARP_NCM_CD, AARP_INICIO_VIGENCIA, AARP_FIM_VIGENCIA from ALIQUOTA_AD_REM_PRODUTO'):
    is_prod.setdefault(ncm, (_d(ini), _d(fim)))
is_exc = sorted({r[0] for r in c.execute('select EAVP_NCM_CD from EXCECAO_AD_VALOREM_PRODUTO')})

ncm_desc = {cd: d for cd, d, fim in c.execute('select NCM_CD, NCM_DESCRICAO, NCM_FIM_VIGENCIA from NCM') if (fim or '9999') >= hoje}
blob = base64.b64encode(zlib.compress(json.dumps(ncm_desc, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 9)).decode()

with open(SAIDA, 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('"""Dados oficiais da Calculadora de Tributos da RFB (CBS/IBS/IS) — gerado por tools/gerar_rtc_calc.py. Não editar à mão."""\n')
    f.write(f'VERSAO = {ver[0]!r}\nVERSAO_DATA = {ver[1][:10]!r}\nVERSAO_DESC = {ver[2]!r}\n')
    f.write(f'CLASSES = {classes!r}\n')
    f.write(f'ANEXOS = {anexos!r}\n')
    f.write(f'APLIC = {aplic!r}\n')
    f.write(f'EXCECOES = {excecoes!r}\n')
    f.write(f'ALIQ_REF = {aliq_ref!r}\n')
    f.write(f'IS_PRODUTO = {is_prod!r}\n')
    f.write(f'IS_EXCECAO = {is_exc!r}\n')
    f.write(f'_NCM_Z = {blob!r}\n')
    f.write('\n\ndef ncm_descricoes():\n    import base64, json, zlib\n'
            '    return json.loads(zlib.decompress(base64.b64decode(_NCM_Z)).decode("utf-8"))\n')
print(SAIDA, ver[0], len(classes), 'classes', len(aplic), 'NCM aplicáveis', len(ncm_desc), 'NCM')
