# -*- coding: utf-8 -*-
"""MIT (Módulo de Inclusão de Tributos da DCTFWeb) a partir da EFD-Contribuições — 2.4.26.

Leitura (computador da equipe, sem internet):
  • 0000 (CNPJ, nome, período, original/retificadora) e 0110 (COD_INC_TRIB: 1 não cumulativo, 2 cumulativo, 3 ambos);
  • M205 (PIS) e M605 (COFINS): código de receita e valor de cada débito a recolher — já depois de créditos,
    retenções e deduções (é o valor da guia);
  • M200 / M600: total a recolher do mês; 1100 / 1500 (SLD_CRED_FIM) ou M100 / M500 (SLD_CRED): saldo credor.

Montagem do MIT (leiaute JSON de importação 1.0, Receita Federal, retificado em 20/02/2025 — o mesmo do serviço
ENCAPURACAO314): grupos na ordem Irpj, Csll, …, PisPasep, Cofins; IdDebito único e sequencial na apuração;
CodigoDebito com 6 dígitos; ValorDebito com 2 casas. TransmissaoImediata só no sem movimento (obrigatório lá; com
movimento a Receita recusa o campo). RegimePisCofins só no Real/imune/isenta; BalancoLucroReal no Real anual.

"Sem movimento": a IN RFB 2.237/2024, art. 6º, § 2º, trata do mês em que houve "interrupção temporária da ocorrência de
fatos geradores". Com saldo credor a empresa teve fato gerador; por isso o sistema não envia sozinho — só quando a equipe
marca, e o robô ainda confere antes se a DCTFWeb do mês tem débito de outra origem (eSocial / EFD-Reinf).

CLI: python fiscal_core.py mit-ler --efd a.txt [b.txt ...] --json saida.json
"""
import json
import re
import sys
from collections import defaultdict

ROTULO = {'691201': 'PIS não cumulativo', '810902': 'PIS cumulativo', '585601': 'COFINS não cumulativo',
          '217201': 'COFINS cumulativo'}
# TributacaoLucro (leiaute): 1 Real Anual · 2 Real Trimestral · 3 Presumido · 4 Arbitrado · 5 Imune · 6 Isenta · 7 Simples
TRIBUTACAO = {1: 'Lucro Real Anual', 2: 'Lucro Real Trimestral', 3: 'Lucro Presumido', 4: 'Lucro Arbitrado',
              5: 'Imune do IRPJ', 6: 'Isenta do IRPJ'}
REGIME = {1: 'não cumulativo', 2: 'cumulativo', 3: 'não cumulativo e cumulativo'}
# IRPJ / CSLL digitados pela equipe (só com movimento): códigos mais comuns, a equipe pode informar outro
CODIGOS_IRPJ_CSLL = {
    'Irpj': [('236201', 'IRPJ · estimativa mensal (Lucro Real anual)'), ('022001', 'IRPJ · Lucro Real trimestral'),
             ('208901', 'IRPJ · Lucro Presumido')],
    'Csll': [('248401', 'CSLL · estimativa mensal (Lucro Real anual)'), ('601201', 'CSLL · Lucro Real trimestral'),
             ('237201', 'CSLL · Lucro Presumido')],
}


def _ler(caminho):
    raw = open(caminho, 'rb').read()
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def _v(s):
    try:
        return round(float(str(s or '0').replace('.', '').replace(',', '.')), 2)
    except ValueError:
        return 0.0


def _cod(s):
    d = re.sub(r'\D', '', s or '')
    return d.zfill(6) if d else ''


def ler_efd(caminho):
    """Uma EFD-Contribuições → dados do MIT de PIS/COFINS da empresa (CNPJ da escrituração)."""
    t = _ler(caminho)
    emp = {'arquivo': caminho, 'cnpj': '', 'nome': '', 'comp': '', 'retificadora': False, 'regime': 0,
           'pis': [], 'cofins': [], 'pis_rec': 0.0, 'cofins_rec': 0.0, 'saldo_pis': 0.0, 'saldo_cofins': 0.0, 'erro': ''}
    soma = {'pis': defaultdict(float), 'cofins': defaultdict(float)}
    sld = {'1100': 0.0, '1500': 0.0, 'M100': 0.0, 'M500': 0.0}
    for linha in t.replace('\r\n', '\n').split('\n'):
        c = linha.split('|')
        if len(c) < 3:
            continue
        r = c[1]
        if r == '0000' and len(c) > 9:
            emp['retificadora'] = c[3] == '1'
            ini = c[6]
            if len(ini) == 8:
                emp['comp'] = f'{ini[4:]}-{ini[2:4]}'
            emp['nome'], emp['cnpj'] = c[8].strip(), re.sub(r'\D', '', c[9])
        elif r == '0110' and len(c) > 2:
            emp['regime'] = int(c[2]) if c[2].strip().isdigit() else 0
        elif r in ('M205', 'M605') and len(c) > 4:
            k = 'pis' if r == 'M205' else 'cofins'
            cod = _cod(c[3])
            if cod:
                soma[k][cod] += _v(c[4])
        elif r == 'M200' and len(c) > 13:
            emp['pis_rec'] = _v(c[13])
        elif r == 'M600' and len(c) > 13:
            emp['cofins_rec'] = _v(c[13])
        elif r in ('1100', '1500') and len(c) > 18:
            sld[r] += _v(c[18])
        elif r in ('M100', 'M500') and len(c) > 15:
            sld[r] += _v(c[15])
        elif r == '9999':
            break
    if not emp['cnpj'] or not emp['comp']:
        emp['erro'] = 'Arquivo sem o registro 0000 da EFD-Contribuições'
    for k in ('pis', 'cofins'):
        emp[k] = [{'cod': cod, 'rotulo': ROTULO.get(cod, ''), 'valor': round(v, 2)} for cod, v in sorted(soma[k].items()) if round(v, 2) > 0]
    emp['saldo_pis'] = round(sld['1100'] or sld['M100'], 2)
    emp['saldo_cofins'] = round(sld['1500'] or sld['M500'], 2)
    emp['total'] = round(sum(x['valor'] for x in emp['pis'] + emp['cofins']), 2)
    # sugestão de tributação do lucro (a equipe confere; fica guardada por empresa): não cumulativo → Lucro Real
    emp['tributacao_sugerida'] = 3 if emp['regime'] == 2 else 1
    return emp


def montar(emp, resp, sem_movimento=False, tributacao=None, extras=None, transmissao_imediata=False, balanco=False):
    """JSON do ENCAPURACAO314 (leiaute do MIT). resp = {cpf, tel, email, crcUf, crcNum}."""
    a, m = emp['comp'].split('-')
    cpf = re.sub(r'\D', '', resp.get('cpf') or '')
    if len(cpf) != 11:
        raise ValueError('CPF do responsável pela apuração não configurado (Admin › Integra Contador).')
    rp = {'CpfResponsavel': cpf}
    tel = re.sub(r'\D', '', resp.get('tel') or '')
    if len(tel) in (10, 11):
        rp['TelResponsavel'] = {'Ddd': tel[:2], 'NumTelefone': tel[2:]}
    em = (resp.get('email') or '').strip()
    if 5 <= len(em) <= 60:
        rp['EmailResponsavel'] = em
    # RegistroCrc é opcional; se for enviado, o leiaute exige a UF — sem UF ele não vai
    uf, crc = (resp.get('crcUf') or '').strip().upper(), re.sub(r'\s', '', resp.get('crcNum') or '')
    if len(uf) == 2 and 6 <= len(crc) <= 11:
        rp['RegistroCrc'] = {'UfRegistro': uf, 'NumRegistro': crc}
    ini = {'SemMovimento': bool(sem_movimento), 'QualificacaoPj': 1}
    out = {'PeriodoApuracao': {'MesApuracao': int(m), 'AnoApuracao': int(a)}}
    if sem_movimento:
        ini['ResponsavelApuracao'] = rp
        out['DadosIniciais'] = ini
        out['TransmissaoImediata'] = bool(transmissao_imediata)
        return out
    trib = int(tributacao or emp.get('tributacao_sugerida') or 1)
    ini['TributacaoLucro'] = trib
    ini['VariacoesMonetarias'] = 2                                   # regime de competência
    # RegimePisCofins (leiaute): obrigatório com QualificacaoPj 1 só quando TributacaoLucro é 1, 2, 5 ou 6 (Real anual,
    # Real trimestral, imune, isenta); no Presumido e no Arbitrado a Receita recusa o campo (EntradaIncorreta-MIT-MSG_0003)
    if trib in (1, 2, 5, 6):
        ini['RegimePisCofins'] = emp.get('regime') if emp.get('regime') in (1, 2, 3) else 4
    ini['ResponsavelApuracao'] = rp
    out['DadosIniciais'] = ini
    grupos = {'Irpj': [], 'Csll': [], 'PisPasep': [], 'Cofins': []}
    for x in extras or []:
        if x.get('grupo') in ('Irpj', 'Csll') and _cod(x.get('cod')) and float(x.get('valor') or 0) > 0:
            grupos[x['grupo']].append((_cod(x['cod']), round(float(x['valor']), 2)))
    grupos['PisPasep'] = [(d['cod'], d['valor']) for d in emp.get('pis') or []]
    grupos['Cofins'] = [(d['cod'], d['valor']) for d in emp.get('cofins') or []]
    deb, n = {}, 0
    # BalancoLucroReal (leiaute): obrigatório no Lucro Real Anual (sem evento especial) — true = IRPJ/CSLL do mês por
    # balanço/balancete de suspensão ou redução; false = estimativa sobre a receita bruta
    if trib == 1:
        deb['BalancoLucroReal'] = bool(balanco)
    for g in ('Irpj', 'Csll', 'PisPasep', 'Cofins'):                 # ordem exigida pelo leiaute
        if not grupos[g]:
            continue
        lista = []
        for cod, val in grupos[g]:
            n += 1
            lista.append({'IdDebito': n, 'CodigoDebito': cod, 'ValorDebito': val})
        deb[g] = {'ListaDebitos': lista}
    if not any(k in deb for k in ('Irpj', 'Csll', 'PisPasep', 'Cofins')):
        raise ValueError('Sem débito a declarar: com saldo credor o MIT não é necessário (ou marque "sem movimento").')
    out['Debitos'] = deb
    # TransmissaoImediata só vai no sem movimento (com movimento a Receita recusa: EntradaIncorreta-MIT-MSG_0020)
    return out


def main_cli(argv):
    def lista(n):
        if n not in argv:
            return []
        out = []
        for a in argv[argv.index(n) + 1:]:
            if a.startswith('--'):
                break
            out.append(a)
        return out
    js = argv[argv.index('--json') + 1] if '--json' in argv else None
    arqs = lista('--efd')
    if not js or not arqs:
        print('uso: mit-ler --efd a.txt [b.txt ...] --json saida.json')
        return 1
    out = []
    for a in arqs:
        try:
            out.append(ler_efd(a))
        except Exception as e:                                          # noqa: BLE001
            out.append({'arquivo': a, 'erro': f'Não consegui ler o arquivo: {e}'[:200]})
    with open(js, 'w', encoding='utf-8') as f:
        json.dump({'ok': True, 'empresas': out, 'codigos_irpj_csll': CODIGOS_IRPJ_CSLL}, f, ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))
