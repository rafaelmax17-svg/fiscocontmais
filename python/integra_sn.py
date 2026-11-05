"""Robô do Fechamento do Simples Nacional · Integra Contador (Serpro).

Contrato Integra Contador da Liddera (contratante = o próprio escritório, que é o procurador dos clientes):
  • autenticação: POST https://autenticacao.sapi.serpro.gov.br/authenticate com Consumer Key/Secret (Basic) e o
    e-CNPJ do escritório (TLS mútuo) → access_token + jwt_token (validade curta, renovados sozinhos);
  • serviços: POST https://gateway.apiserpro.serpro.gov.br/integra-contador/v1/{Consultar|Emitir|Declarar}
    com contratante / autorPedidoDados / contribuinte e pedidoDados (idSistema, idServico, versaoSistema, dados);
  • cada cliente precisa ter dado procuração eletrônica no e-CAC ao CNPJ do escritório (item 4.5 do anexo do contrato).

Serviços do PGDAS-D usados (cobrança por requisição — anexo de preços do contrato):
  • CONSULTIMADECREC14 (Consultar): última declaração e recibo do período → confirma a transmissão e traz os PDFs;
  • GERARDAS12 (Emitir): DAS do período, em PDF — só até o vencimento (depois disso o DAS sai com acréscimos);
  • CONSEXTRATO16 (Consultar): extrato do DAS gerado.

Os nomes exatos dos campos de resposta são lidos de forma tolerante (o catálogo oficial não pôde ser conferido
daqui); qualquer resposta que não seja entendida vira "Verificar" com a mensagem do Serpro, nunca uma marcação.

CLI: python fiscal_core.py integra --entrada pedido.json --json resultado.json
O arquivo de entrada (com a chave e a senha do certificado) é apagado assim que é lido.
"""
import base64
import json
import os
import re
import shutil
import sys
import time
import unicodedata

URL_AUTH = 'https://autenticacao.sapi.serpro.gov.br/authenticate'
URL_API = 'https://gateway.apiserpro.serpro.gov.br/integra-contador/v1/'
MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']


# ------------------------------------------------------------------ certificado (mesmo tratamento das Baixas DF-e)
def _pem_temp(pfx, senha):
    from fiscal_core import _extrair_cert_chave_temp
    return _extrair_cert_chave_temp(pfx, senha)


# ------------------------------------------------------------------ autenticação e chamadas
def autenticar(key, secret, cert):
    import requests
    basic = base64.b64encode(f'{key}:{secret}'.encode('utf-8')).decode('ascii')
    try:
        r = requests.post(URL_AUTH, data={'grant_type': 'client_credentials'}, cert=cert, timeout=60,
                          headers={'Authorization': f'Basic {basic}', 'Role-Type': 'TERCEIROS',
                                   'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    except requests.exceptions.SSLError as e:
        return {'erro': f'O Serpro recusou o certificado do escritório (TLS): {e}'}
    except requests.exceptions.RequestException as e:
        return {'erro': f'Não consegui conectar com o Serpro: {e}'}
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code in (401, 403):
        return {'erro': 'O Serpro não aceitou a chave (Consumer Key/Secret) ou o certificado. Confira na Área do Cliente do Serpro se a chave é a de produção e se o certificado é o e-CNPJ do contratante.'}
    if r.status_code != 200 or not d.get('access_token'):
        return {'erro': f'Autenticação no Serpro falhou (HTTP {r.status_code}): {(r.text or "")[:200]}'}
    return {'access_token': d['access_token'], 'jwt_token': d.get('jwt_token', ''),
            'expira': time.time() + int(d.get('expires_in') or 1800) - 120}


def _msgs(d):
    out = []
    for m in (d or {}).get('mensagens') or []:
        if isinstance(m, dict):
            out.append(f"{m.get('codigo', '')} {m.get('texto', '')}".strip())
        elif m:
            out.append(str(m))
    return '; '.join(x for x in out if x)


def chamar(tok, cert, acao, contratante, cnpj, id_servico, dados, id_sistema='PGDASD', versao='1.0'):
    """Retorna {'http', 'status', 'dados'(já em dict/list quando for JSON), 'msg'}."""
    import requests
    corpo = {
        'contratante': {'numero': contratante, 'tipo': 2},
        'autorPedidoDados': {'numero': contratante, 'tipo': 2},
        'contribuinte': {'numero': cnpj, 'tipo': 2},
        'pedidoDados': {'idSistema': id_sistema, 'idServico': id_servico, 'versaoSistema': versao,
                        'dados': json.dumps(dados, ensure_ascii=False)},
    }
    try:
        r = requests.post(URL_API + acao, json=corpo, timeout=90, cert=cert,
                          headers={'Authorization': f"Bearer {tok['access_token']}", 'jwt_token': tok.get('jwt_token', ''),
                                   'Content-Type': 'application/json', 'Accept': 'application/json'})
    except requests.exceptions.RequestException as e:
        return {'http': 0, 'status': 0, 'dados': None, 'msg': f'Sem conexão com o Serpro: {e}'}
    try:
        d = r.json()
    except ValueError:
        d = {}
    bruto = d.get('dados') if isinstance(d, dict) else None
    if isinstance(bruto, str) and bruto.strip()[:1] in '{[':
        try:
            bruto = json.loads(bruto)
        except ValueError:
            pass
    return {'http': r.status_code, 'status': (d.get('status') if isinstance(d, dict) else 0) or r.status_code,
            'dados': bruto, 'msg': _msgs(d) or (r.text or '')[:300]}


# ------------------------------------------------------------------ leitura tolerante das respostas
def _acha(obj, chaves):
    """Primeiro valor (não vazio) de qualquer uma das chaves, em qualquer nível."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in chaves and v not in (None, '', [], {}):
                return v
        for v in obj.values():
            x = _acha(v, chaves)
            if x not in (None, ''):
                return x
    elif isinstance(obj, list):
        for v in obj:
            x = _acha(v, chaves)
            if x not in (None, ''):
                return x
    return None


def _pdfs(obj, caminho=''):
    """Lista (rotulo, nomeArquivo, bytes) de todos os PDFs em base64 da resposta."""
    out = []
    if isinstance(obj, dict):
        nome = str(obj.get('nomeArquivo') or obj.get('nome') or '')
        for k, v in obj.items():
            if isinstance(v, str) and k.lower() in ('pdf', 'arquivo', 'documento', 'conteudo') and len(v) > 200:
                try:
                    b = base64.b64decode(v, validate=False)
                except Exception:
                    continue
                if b[:4] == b'%PDF':
                    out.append(((caminho + ' ' + nome).lower(), nome, b))
            elif isinstance(v, (dict, list)):
                out += _pdfs(v, caminho + ' ' + k)
    elif isinstance(obj, list):
        for v in obj:
            out += _pdfs(v, caminho)
    return out


def _txt(s):
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()


def _classifica_erro(res):
    """Converte uma resposta sem sucesso em (situacao, mensagem)."""
    m = res.get('msg') or ''
    t = _txt(m)
    if res.get('http') in (401,):
        return 'erro', 'Acesso ao Serpro expirou; tente de novo.'
    if 'procura' in t or 'acessonegado' in t.replace(' ', '') or 'nao possui autoriza' in t or res.get('http') == 403:
        return 'semproc', 'Sem procuração no e-CAC para a Liddera (Simples Nacional). ' + m[:160]
    if res.get('http') == 404 or re.search(r'nao (foi )?(encontrad|localizad)|nao existe|nenhuma declara|inexistente|nao ha declara', t):
        return 'nao', 'Ainda não transmitido (a Receita não tem declaração do período).'
    return 'erro', (m or f'Resposta inesperada do Serpro (HTTP {res.get("http")}).')[:300]


# ------------------------------------------------------------------ pastas das empresas
_PALAVRAS_FORA = {'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'S', 'A', 'DE', 'DA', 'DO', 'DOS', 'DAS', 'E', 'EM', 'MEI', 'SLU', 'CIA', 'LTD'}


def _tokens(nome):
    n = unicodedata.normalize('NFD', str(nome or '').upper()).encode('ascii', 'ignore').decode()
    n = re.sub(r'^[\d\s._-]+(?=[A-Z])', '', n)               # "012 - EMPRESA" → "EMPRESA"
    n = re.sub(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', ' ', n)   # CNPJ no nome da pasta
    return [t for t in re.sub(r'[^A-Z0-9]+', ' ', n).split() if t not in _PALAVRAS_FORA]


def _pontos(te, tf):
    """Quantos primeiros nomes coincidem (exige o mínimo entre 2 e o tamanho do nome mais curto)."""
    if not te or not tf:
        return 0
    if te == tf:
        return 100                                           # nome igual (fora LTDA/ME/EPP…): ganha das parecidas
    n = 0
    for a, b in zip(te, tf):
        if a != b:
            break
        n += 1
    precisa = min(2, len(te), len(tf))
    return n if n >= precisa else 0


def acha_pasta_empresa(base, nome):
    """Retorna (caminho | None, candidatos[]) — None quando não acha ou acha mais de uma com a mesma força."""
    try:
        pastas = [p for p in os.listdir(base) if os.path.isdir(os.path.join(base, p))]
    except OSError:
        return None, []
    te = _tokens(nome)
    notas = [(_pontos(te, _tokens(p)), p) for p in pastas]
    notas = [x for x in notas if x[0]]
    if not notas:
        return None, []
    melhor = max(n for n, _ in notas)
    top = sorted(p for n, p in notas if n == melhor)
    cand = [os.path.join(base, p) for _, p in sorted(notas, key=lambda x: (-x[0], x[1]))][:8]
    return (os.path.join(base, top[0]) if len(top) == 1 else None), cand


def _sub(modelo, comp):
    a, m = comp.split('-')
    return (modelo or '').replace('{AAAA}', a).replace('{MM}', m).replace('{MES}', MESES[int(m) - 1]).replace('{AA}', a[2:])


def _nome_arq(nome):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', ' ', str(nome or '')).strip()
    return re.sub(r'\s+', ' ', s)[:90].rstrip(' .')


def destino_empresa(cfg, emp, comp):
    """(pasta | None, aviso, candidatos). Nunca escolhe entre duas pastas parecidas."""
    a, m = comp.split('-')
    mapa = cfg.get('mapa') or {}
    base = cfg.get('base') or ''
    raiz = mapa.get(emp['id'])
    cand = []
    if raiz and not os.path.isdir(raiz):
        raiz = None
    if not raiz and base:
        if not os.path.isdir(base):
            return None, f'A pasta das empresas não está acessível neste computador: {base}', []
        raiz, cand = acha_pasta_empresa(base, emp['nome'])
        if not raiz:
            return None, ('Mais de uma pasta parecida com o nome da empresa — escolha a pasta certa no Admin.' if cand
                          else 'Não achei a pasta da empresa pelo nome — escolha a pasta no Admin.'), cand
    if raiz:
        sub = _sub(cfg.get('subpasta') or '', comp)
        return (os.path.join(raiz, sub) if sub else raiz), '', []
    # sem pasta das empresas configurada: mesma estrutura das Baixas DF-e (<base>/MM-AAAA/<empresa>/Simples Nacional)
    fb = cfg.get('fallback') or ''
    if not fb:
        return None, 'Pasta para salvar os documentos não configurada.', []
    return os.path.join(fb, f'{m}-{a}', _nome_arq(emp['nome']), 'Simples Nacional'), '', []


def _grava(pasta, nome, dados):
    """Grava sem sobrescrever: se já existe um arquivo igual, reaproveita; se existe diferente, cria "(2)"."""
    os.makedirs(pasta, exist_ok=True)
    base, ext = os.path.splitext(nome)
    i = 1
    while True:
        cam = os.path.join(pasta, nome if i == 1 else f'{base} ({i}){ext}')
        if not os.path.exists(cam):
            with open(cam, 'wb') as f:
                f.write(dados)
            return cam
        try:
            if os.path.getsize(cam) == len(dados) and open(cam, 'rb').read() == dados:
                return cam
        except OSError:
            pass
        i += 1


# ------------------------------------------------------------------ conferência de uma empresa
def _num(v):
    try:
        return round(float(str(v).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return None


def conferir_empresa(tok, cert, contratante, emp, comp, opc, consumo):
    pa = comp.replace('-', '')
    a, m = comp.split('-')
    r = {'id': emp['id'], 'st': '', 'msg': '', 'arquivos': {}, 'pasta': ''}
    cnpj = re.sub(r'\D', '', emp.get('cnpj') or '')
    if len(cnpj) != 14:
        r.update(st='semcnpj', msg='Empresa sem CNPJ no cadastro do Fechamento.')
        return r
    res = chamar(tok, cert, 'Consultar', contratante, cnpj, 'CONSULTIMADECREC14', {'periodoApuracao': pa})
    consumo['consulta'] += 1
    if not (res['http'] == 200 and res['dados']):
        r['st'], r['msg'] = _classifica_erro(res)
        return r
    d = res['dados']
    r['decl'] = str(_acha(d, {'numerodeclaracao', 'numdeclaracao'}) or '')
    r['dataTrans'] = str(_acha(d, {'datahoratransmissao', 'datatransmissao', 'dthrtransmissao'}) or '')
    pdfs = _pdfs(d)
    if not r['decl'] and not pdfs:
        r.update(st='erro', msg='O Serpro respondeu sem número da declaração nem documentos. ' + res['msg'][:150])
        return r
    r['st'] = 'ok'
    r['msg'] = 'Transmitido' + (f" · Decl. {r['decl']}" if r['decl'] else '')
    if not opc.get('baixar'):
        return r
    pasta, aviso, cand = destino_empresa(opc.get('pastas') or {}, emp, comp)
    if not pasta:
        r['pastaAviso'], r['candidatos'] = aviso, cand
        return r
    r['pasta'] = pasta
    nome = _nome_arq(emp['nome'])
    try:
        for rot, _arq, b in pdfs:
            tipo = 'Recibo' if 'recibo' in rot else 'Declaracao'
            r['arquivos'][tipo] = _grava(pasta, f"{'Recibo PGDAS-D' if tipo == 'Recibo' else 'Declaração PGDAS-D'} {m}-{a} - {nome}.pdf", b)
    except OSError as e:
        r['pastaAviso'] = f'Não consegui gravar na pasta da empresa: {e}'
        return r
    # DAS e extrato: só até o vencimento (dia 20 do mês seguinte) e quando a etapa DAS não é N/A
    if emp.get('das') == 'N/A' or not opc.get('emitirDas'):
        return r
    res = chamar(tok, cert, 'Emitir', contratante, cnpj, 'GERARDAS12', {'periodoApuracao': pa})
    consumo['emissao'] += 1
    if res['http'] != 200 or not res['dados']:
        st, msg = _classifica_erro(res)
        r['dasAviso'] = ('DAS não gerado: ' + (res['msg'] or msg))[:240]
        return r
    das_pdf = _pdfs(res['dados'])
    r['dasNumero'] = str(_acha(res['dados'], {'numerodocumento', 'numerodas'}) or '')
    r['dasValor'] = _num(_acha(res['dados'], {'total', 'valortotal', 'valor'}))
    r['dasVenc'] = str(_acha(res['dados'], {'datavencimento', 'vencimento'}) or '')
    try:
        if das_pdf:
            r['arquivos']['DAS'] = _grava(pasta, f'DAS {m}-{a} - {nome}.pdf', das_pdf[0][2])
    except OSError as e:
        r['pastaAviso'] = f'Não consegui gravar o DAS: {e}'
        return r
    if r['dasNumero']:
        res = chamar(tok, cert, 'Consultar', contratante, cnpj, 'CONSEXTRATO16', {'numeroDas': r['dasNumero']})
        consumo['consulta'] += 1
        ex = _pdfs(res['dados']) if res['http'] == 200 else []
        if ex:
            try:
                r['arquivos']['Extrato'] = _grava(pasta, f'Extrato do DAS {m}-{a} - {nome}.pdf', ex[0][2])
            except OSError:
                pass
        elif res['http'] != 200:
            r['extratoAviso'] = ('Extrato não baixado: ' + res['msg'])[:200]
    return r


# ------------------------------------------------------------------ entrada
def processar(p):
    acao = p.get('acao')
    key, secret = p.get('key') or '', p.get('secret') or ''
    contratante = re.sub(r'\D', '', p.get('contratante') or '')
    if not key or not secret:
        return {'ok': False, 'erro': 'Chave do Serpro não informada.'}
    if len(contratante) != 14:
        return {'ok': False, 'erro': 'CNPJ do contratante inválido.'}
    try:
        cert_pem, key_pem, tmp = _pem_temp(p.get('pfx'), p.get('senha') or '')
    except Exception as e:
        return {'ok': False, 'erro': f'Não consegui abrir o certificado do escritório: {e}'}
    try:
        tok = p.get('token') if (p.get('token') or {}).get('expira', 0) > time.time() else None
        if not tok:
            # a sessão com o Serpro usa o mesmo certificado em todas as chamadas
            tok = autenticar(key, secret, (cert_pem, key_pem))
            if tok.get('erro'):
                return {'ok': False, 'erro': tok['erro']}
        if acao == 'testar':
            return {'ok': True, 'token': tok}
        consumo = {'consulta': 0, 'emissao': 0}
        out = []
        for emp in p.get('empresas') or []:
            try:
                out.append(conferir_empresa(tok, (cert_pem, key_pem), contratante, emp, p['comp'], p, consumo))
            except Exception as e:                              # uma empresa com problema não para as outras
                out.append({'id': emp.get('id'), 'st': 'erro', 'msg': f'Falha ao conferir: {e}'[:300], 'arquivos': {}})
        return {'ok': True, 'token': tok, 'resultados': out, 'consumo': consumo}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main_cli(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
    ent = opt('--entrada')
    try:
        with open(ent, encoding='utf-8') as f:
            p = json.load(f)
    except Exception as e:
        p = None
        res = {'ok': False, 'erro': f'Pedido inválido: {e}'}
    finally:
        try:
            os.remove(ent)                                     # a chave e a senha não ficam no disco
        except Exception:
            pass
    if p is not None:
        try:
            res = processar(p)
        except Exception as e:                                  # noqa: BLE001
            res = {'ok': False, 'erro': f'Falha no robô do Integra Contador: {e}'}
    with open(opt('--json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))
