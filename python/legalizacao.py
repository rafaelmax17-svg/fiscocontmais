# -*- coding: utf-8 -*-
"""Levantamento geral da empresa para a Legalização (uso interno — módulo restrito ao Admin).

Entrada:
  * dados do CNPJ (BrasilAPI / Receita Federal) — buscados pelo aplicativo;
  * o "estado" do checklist, preenchido pelo analista (status e validade de cada item que
    não tem consulta automática: licenças, certidões, certificado digital etc.).

Saída: dados da empresa, atividades (CNAE), quadro societário, itens do checklist aplicáveis
às atividades, plano de ação por urgência e índice de regularidade (0 a 100).

IMPORTANTE: o que é "automático" aqui é só o cadastro da Receita. Licenças e certidões não têm
consulta pública sem certificado ou captcha, então ficam como checklist manual. A lista de
licenças por CNAE é uma referência do que costuma ser exigido, e o órgão local (prefeitura,
corpo de bombeiros, vigilância, órgão ambiental) é quem define a exigência real.
"""
import json
import re
from datetime import date, datetime, timedelta


def _d(s):
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _fmt(d):
    return d.strftime('%d/%m/%Y') if d else ''


def _cnpj_fmt(c):
    c = re.sub(r'\D', '', str(c or '')).zfill(14)
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}'


def _cnae_cod(c):
    c = re.sub(r'\D', '', str(c or ''))
    return c.zfill(7)[:7]


def _cnae_fmt(c):
    c = _cnae_cod(c)
    return f'{c[:4]}-{c[4]}/{c[5:]}'


# ----------------------------------------------------------------------------- regras por CNAE
def _alimentos(c):
    return c[:2] in ('10', '11') or c[:4] in ('4711', '4712', '4721', '4722', '4723', '4724', '4729') or c[:2] == '56'


def _saude(c):
    return c[:2] == '86' or c[:4] in ('4771', '4772') or c[:4] == '9602'


def _combustivel(c):
    return c[:5] in ('47318', '46818') or c[:4] == '4731' or c[:5] == '46818'


def _ambiental(c):
    return _combustivel(c) or c[:4] in ('4520', '4530', '4541') or c[:2] in ('24', '38', '19', '20', '22', '23') or c[:4] in ('1011', '1012', '1013')


def _conselho(c):
    return c[:2] in ('69', '71', '86', '75') or c[:4] in ('7020', '7210')


# (id, grupo, nome, órgão, tem validade, peso, função(lista de cnaes)->bool, dica)
ITENS = [
    ('alvara', 'Licenças e alvarás', 'Alvará de funcionamento', 'Prefeitura', True, 2, lambda cs: True,
     'Confirmar o prazo de renovação na prefeitura do município.'),
    ('bombeiros', 'Licenças e alvarás', 'Corpo de Bombeiros (AVCB/CLCB)', 'Corpo de Bombeiros', True, 2, lambda cs: True,
     'A exigência depende da área e do risco da edificação.'),
    ('vigilancia', 'Licenças e alvarás', 'Licença sanitária (Vigilância Sanitária)', 'Vigilância Sanitária', True, 2,
     lambda cs: any(_alimentos(c) or _saude(c) for c in cs), 'Alimentos, saúde, estética e farmácia costumam exigir.'),
    ('ambiental', 'Licenças e alvarás', 'Licença ambiental', 'Órgão ambiental estadual/municipal', True, 2,
     lambda cs: any(_ambiental(c) for c in cs), 'Postos, oficinas e indústrias costumam exigir. Confirmar o enquadramento.'),
    ('anp', 'Licenças e alvarás', 'Autorização da ANP', 'ANP', False, 2,
     lambda cs: any(_combustivel(c) for c in cs), 'Atividade com combustíveis exige autorização para operar.'),
    ('conselho', 'Licenças e alvarás', 'Registro no conselho de classe', 'Conselho profissional', False, 1,
     lambda cs: any(_conselho(c) for c in cs), 'Atividades regulamentadas podem exigir registro da empresa no conselho.'),
    ('cnd_federal', 'Certidões de regularidade', 'Certidão federal (RFB/PGFN)', 'Receita Federal / PGFN', True, 2, lambda cs: True,
     'Emitir no portal da Receita ou pelo e-CAC.'),
    ('cnd_estadual', 'Certidões de regularidade', 'Certidão estadual (SEFAZ)', 'SEFAZ do estado', True, 2, lambda cs: True, ''),
    ('cnd_municipal', 'Certidões de regularidade', 'Certidão municipal', 'Prefeitura', True, 2, lambda cs: True, ''),
    ('fgts', 'Certidões de regularidade', 'Certificado de Regularidade do FGTS (CRF)', 'Caixa Econômica Federal', True, 1, lambda cs: True, ''),
    ('cndt', 'Certidões de regularidade', 'Certidão Negativa de Débitos Trabalhistas (CNDT)', 'Justiça do Trabalho (TST)', True, 1, lambda cs: True, ''),
    ('certificado', 'Acessos e documentos', 'Certificado digital e-CNPJ', 'Autoridade certificadora', True, 2, lambda cs: True,
     'Sem ele, o escritório não baixa notas nem transmite obrigações.'),
    ('procuracao', 'Acessos e documentos', 'Procuração eletrônica (e-CAC)', 'Receita Federal', True, 2, lambda cs: True,
     'Necessária para o escritório acessar dados fiscais do cliente.'),
    ('contrato', 'Acessos e documentos', 'Contrato social atualizado', 'Junta Comercial', False, 1, lambda cs: True,
     'Conferir se a última alteração reflete os sócios e as atividades atuais.'),
    ('inscr_mun', 'Acessos e documentos', 'Inscrição municipal', 'Prefeitura', False, 1, lambda cs: True, ''),
    ('inscr_est', 'Acessos e documentos', 'Inscrição estadual habilitada', 'SEFAZ do estado', False, 1,
     lambda cs: any(c[:2] not in ('69', '70', '71', '73', '74', '85', '86', '90', '96') for c in cs),
     'Para atividades de comércio e indústria.'),
]

STATUS = ('regular', 'irregular', 'nao_aplica', 'nao_verificado')
JANELA_ATENCAO = 60


def _avaliar_item(estado_item, tem_validade, hoje):
    st = (estado_item or {}).get('status') or 'nao_verificado'
    if st not in STATUS:
        st = 'nao_verificado'
    val = _d((estado_item or {}).get('validade'))
    dias = (val - hoje).days if val else None
    if st == 'nao_aplica':
        return 'nao_aplica', 'Não se aplica', val, dias
    if st == 'irregular':
        return 'critico', 'Irregular', val, dias
    if st == 'nao_verificado':
        return 'pendente', 'Não verificado', val, dias
    if tem_validade and val:
        if dias < 0:
            return 'critico', f'Vencido em {_fmt(val)}', val, dias
        if dias <= JANELA_ATENCAO:
            return 'atencao', f'Vence em {dias} dias ({_fmt(val)})', val, dias
        return 'ok', f'Vigente até {_fmt(val)}', val, dias
    if tem_validade and not val:
        return 'atencao', 'Regular, sem data de validade informada', val, dias
    return 'ok', 'Regular', val, dias


def montar(api, estado=None, hoje=None):
    estado = estado or {}
    hoje = hoje or date.today()
    itens_estado = estado.get('itens', {}) if isinstance(estado, dict) else {}

    principal = {'codigo': _cnae_cod(api.get('cnae_fiscal')), 'descricao': api.get('cnae_fiscal_descricao', '')}
    secund = [{'codigo': _cnae_cod(x.get('codigo')), 'descricao': x.get('descricao', '')}
              for x in (api.get('cnaes_secundarios') or []) if x.get('codigo') and str(x.get('codigo')) != '0']
    cnaes = [principal['codigo']] + [x['codigo'] for x in secund]

    situacao = (api.get('descricao_situacao_cadastral') or '').upper()
    ativa = situacao == 'ATIVA'
    simples = api.get('opcao_pelo_simples')
    mei = api.get('opcao_pelo_mei')
    regime_ult = ''
    rt = api.get('regime_tributario') or []
    if rt:
        try:
            regime_ult = sorted(rt, key=lambda x: x.get('ano', 0))[-1].get('forma_de_tributacao', '')
        except Exception:
            regime_ult = ''
    if mei:
        regime = 'MEI'
    elif simples:
        regime = 'Simples Nacional'
    else:
        regime = regime_ult or 'Não identificado'
    inicio = _d(api.get('data_inicio_atividade'))

    qsa = [{'nome': q.get('nome_socio', ''), 'qualificacao': q.get('qualificacao_socio', ''),
            'entrada': _fmt(_d(q.get('data_entrada_sociedade')))} for q in (api.get('qsa') or [])]

    dados = [
        ('Razão social', api.get('razao_social', '')),
        ('Nome fantasia', api.get('nome_fantasia', '') or '—'),
        ('CNPJ', _cnpj_fmt(api.get('cnpj'))),
        ('Matriz ou filial', api.get('descricao_identificador_matriz_filial', '') or '—'),
        ('Abertura', _fmt(inicio) or '—'),
        ('Natureza jurídica', api.get('natureza_juridica', '') or '—'),
        ('Porte', api.get('porte', '') or '—'),
        ('Capital social', 'R$ {:,.2f}'.format(float(api.get('capital_social') or 0)).replace(',', 'X').replace('.', ',').replace('X', '.')),
        ('Regime (cadastro Receita)', regime),
        ('Município / UF', f"{api.get('municipio', '')} / {api.get('uf', '')}"),
    ]

    # --- alertas automáticos do cadastro
    alertas = []
    if not ativa:
        alertas.append({'nivel': 'critico', 'texto': f'Situação cadastral na Receita: {situacao.title() or "não informada"}. Regularizar antes de qualquer outra providência.'})
    if api.get('situacao_especial'):
        alertas.append({'nivel': 'atencao', 'texto': 'Há situação especial registrada no cadastro: ' + str(api.get('situacao_especial'))})
    if api.get('data_exclusao_do_simples'):
        alertas.append({'nivel': 'atencao', 'texto': f"Consta exclusão do Simples Nacional em {_fmt(_d(api.get('data_exclusao_do_simples')))}. Conferir o regime atual."})
    if not qsa and not mei:
        alertas.append({'nivel': 'atencao', 'texto': 'O quadro societário não veio na consulta. Conferir com o contrato social.'})
    if qsa and not any('administrador' in (q['qualificacao'] or '').lower() for q in qsa):
        alertas.append({'nivel': 'atencao', 'texto': 'Nenhum sócio aparece como administrador no cadastro. Conferir quem representa a empresa.'})
    if len(secund) >= 10:
        alertas.append({'nivel': 'info', 'texto': f'{len(secund)} atividades secundárias. Conferir se todas são realmente exercidas e se há licença para cada uma.'})

    # --- checklist
    itens, plano = [], []
    pontos, peso_total = 0.0, 0.0
    cont = {'ok': 0, 'atencao': 0, 'critico': 0, 'pendente': 0}
    for id_, grupo, nome, orgao, tem_val, peso, aplica, dica in ITENS:
        if not aplica(cnaes):
            continue
        ei = itens_estado.get(id_, {})
        nivel, rotulo, val, dias = _avaliar_item(ei, tem_val, hoje)
        it = {'id': id_, 'grupo': grupo, 'nome': nome, 'orgao': orgao, 'tem_validade': tem_val, 'peso': peso,
              'nivel': nivel, 'rotulo': rotulo, 'validade': val.isoformat() if val else '', 'dias': dias,
              'obs': ei.get('obs', ''), 'status': ei.get('status') or 'nao_verificado', 'dica': dica}
        itens.append(it)
        if nivel == 'nao_aplica':
            continue
        peso_total += peso
        pontos += peso * {'ok': 1.0, 'atencao': 0.5, 'pendente': 0.25, 'critico': 0.0}[nivel]
        cont[nivel] += 1
        if nivel in ('critico', 'atencao', 'pendente'):
            plano.append({'item': nome, 'nivel': nivel, 'rotulo': rotulo, 'orgao': orgao, 'dica': dica, 'peso': peso, 'dias': dias})
    # a situação cadastral também pesa no índice
    peso_total += 3
    pontos += 3 if ativa else 0
    if not ativa:
        cont['critico'] += 1
        plano.append({'item': 'Situação cadastral na Receita', 'nivel': 'critico', 'rotulo': situacao.title(), 'orgao': 'Receita Federal', 'dica': 'Regularizar o cadastro.', 'peso': 3, 'dias': None})
    else:
        cont['ok'] += 1
    ordem = {'critico': 0, 'atencao': 1, 'pendente': 2}
    plano.sort(key=lambda p: (ordem[p['nivel']], -p['peso'], p['dias'] if p['dias'] is not None else 9999))
    indice = round(100 * pontos / peso_total) if peso_total else 0

    return {
        'cnpj': re.sub(r'\D', '', str(api.get('cnpj') or '')), 'razao_social': api.get('razao_social', ''),
        'situacao': situacao.title(), 'ativa': ativa, 'regime': regime, 'dados': [{'rotulo': k, 'valor': v} for k, v in dados],
        'cnae_principal': {'codigo': _cnae_fmt(principal['codigo']), 'descricao': principal['descricao']},
        'cnaes_secundarios': [{'codigo': _cnae_fmt(x['codigo']), 'descricao': x['descricao']} for x in secund],
        'qsa': qsa, 'alertas': alertas, 'itens': itens, 'plano': plano, 'indice': indice, 'contagem': cont,
        'gerado_em': hoje.isoformat(),
    }


# ----------------------------------------------------------------------------- HTML para imprimir / PDF
def _e(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def gerar_html(res):
    cor = {'ok': '#0b5e44;background:#e8f6f0', 'atencao': '#6b4a00;background:#fff6e5', 'critico': '#8a1f1f;background:#fdecec',
           'pendente': '#4a5373;background:#eef1f8', 'nao_aplica': '#4a5373;background:#eef1f8'}
    nome = {'ok': 'Em dia', 'atencao': 'Atenção', 'critico': 'Crítico', 'pendente': 'A verificar', 'nao_aplica': 'Não se aplica'}
    linhas = ''
    grupo = None
    for it in res['itens']:
        if it['grupo'] != grupo:
            grupo = it['grupo']
            linhas += f'<tr><td colspan="3" style="font-weight:600;color:#4a2bb0;padding-top:14px">{_e(grupo)}</td></tr>'
        linhas += (f'<tr><td>{_e(it["nome"])}<br><small style="color:#6b7390">{_e(it["orgao"])}</small></td>'
                   f'<td>{_e(it["rotulo"])}</td><td><span style="border-radius:20px;padding:2px 10px;font-size:11px;color:{cor[it["nivel"]]}">{nome[it["nivel"]]}</span></td></tr>')
    plano = ''.join(f'<li><b>{_e(p["item"])}</b>: {_e(p["rotulo"])} <small style="color:#6b7390">({_e(p["orgao"])})</small></li>' for p in res['plano']) or '<li>Nenhuma pendência.</li>'
    dados = ''.join(f'<tr><td style="color:#6b7390;width:34%">{_e(d["rotulo"])}</td><td>{_e(d["valor"])}</td></tr>' for d in res['dados'])
    socios = ''.join(f'<tr><td>{_e(q["nome"])}</td><td>{_e(q["qualificacao"])}</td><td>{_e(q["entrada"])}</td></tr>' for q in res['qsa']) or '<tr><td colspan="3">Sem dados</td></tr>'
    cnaes = f'<li><b>{_e(res["cnae_principal"]["codigo"])}</b> {_e(res["cnae_principal"]["descricao"])} (principal)</li>' + ''.join(
        f'<li>{_e(c["codigo"])} {_e(c["descricao"])}</li>' for c in res['cnaes_secundarios'])
    return f'''<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Levantamento — {_e(res["razao_social"])}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;color:#1f2a44;margin:24px;font-size:13px}}h1{{font-size:20px;color:#4a2bb0;margin:0}}h2{{font-size:15px;color:#4a2bb0;margin:22px 0 6px;border-bottom:1px solid #e3e8ef;padding-bottom:4px}}
table{{width:100%;border-collapse:collapse}}td{{padding:6px 4px;border-bottom:1px solid #eef1f8;vertical-align:top}}.idx{{display:inline-block;font-size:34px;font-weight:600;color:#4a2bb0}}
@media print{{body{{margin:12mm}}*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}</style></head><body>
<h1>Levantamento da empresa</h1><div style="color:#6b7390">{_e(res["razao_social"])} · CNPJ {_e(_cnpj_fmt(res["cnpj"]))} · gerado em {_e(_fmt(_d(res["gerado_em"])))}</div>
<h2>Índice de regularidade</h2><span class="idx">{res["indice"]}</span> <span style="color:#6b7390">de 100 · {res["contagem"]["critico"]} críticos, {res["contagem"]["atencao"]} em atenção, {res["contagem"]["pendente"]} a verificar</span>
<h2>Plano de ação</h2><ol>{plano}</ol><h2>Dados cadastrais (Receita Federal)</h2><table>{dados}</table>
<h2>Atividades (CNAE)</h2><ul>{cnaes}</ul><h2>Quadro societário</h2><table>{socios}</table>
<h2>Licenças, certidões e acessos</h2><table>{linhas}</table>
<p style="margin-top:22px;color:#6b7390;font-size:11px">Dados cadastrais da Receita Federal. Licenças e certidões foram informadas pelo analista. A lista de licenças por atividade é uma referência: a exigência real é definida pelos órgãos competentes.</p></body></html>'''


def main_cli(argv):
    """fiscal_core.py legalizacao-levantamento --api api.json [--estado estado.json] --json out.json [--html out.html]"""
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    api_p, est_p, js, ht = opt('--api'), opt('--estado'), opt('--json'), opt('--html')
    if not api_p or not js:
        print('uso: legalizacao-levantamento --api api.json [--estado estado.json] --json out.json [--html out.html]')
        return 1
    try:
        with open(api_p, encoding='utf-8') as f:
            api = json.load(f)
        est = {}
        if est_p:
            with open(est_p, encoding='utf-8') as f:
                est = json.load(f)
        res = montar(api, est)
        if ht:
            with open(ht, 'w', encoding='utf-8') as f:
                f.write(gerar_html(res))
    except Exception as e:
        res = {'erro': str(e)}
    with open(js, 'w', encoding='utf-8') as f:
        f.write(json.dumps(res, ensure_ascii=False))
    print(json.dumps({'indice': res.get('indice')}))
    return 0 if 'erro' not in res else 1
