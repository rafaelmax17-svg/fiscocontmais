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


def chamar(tok, cert, acao, contratante, cnpj, id_servico, dados, id_sistema='PGDASD', versao='1.0', proc=None):
    """Retorna {'http', 'status', 'dados'(já em dict/list quando for JSON), 'msg'}.
    proc = {'cpf', 'token'}: o pedido sai em nome do procurador pessoa física (autorPedidoDados = CPF) com o token do
    Termo de Autorização (cabeçalho autenticar_procurador_token — não vai no /Apoiar, que não o aceita)."""
    import requests
    autor = {'numero': proc['cpf'], 'tipo': 1} if proc else {'numero': contratante, 'tipo': 2}
    corpo = {
        'contratante': {'numero': contratante, 'tipo': 2},
        'autorPedidoDados': autor,
        'contribuinte': {'numero': cnpj, 'tipo': 2},
        'pedidoDados': {'idSistema': id_sistema, 'idServico': id_servico, 'versaoSistema': versao,
                        'dados': json.dumps(dados, ensure_ascii=False)},
    }
    hdr = {'Authorization': f"Bearer {tok['access_token']}", 'jwt_token': tok.get('jwt_token', ''),
           'Content-Type': 'application/json', 'Accept': 'application/json'}
    if proc and acao != 'Apoiar':
        hdr['autenticar_procurador_token'] = proc['token']
    try:
        r = requests.post(URL_API + acao, json=corpo, timeout=90, cert=cert, headers=hdr)
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


SUBPASTA_PADRAO = r'Simples Nacional\{AAAA}\{PERIODO}'
_ABREV = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']


def _norm(n):
    return unicodedata.normalize('NFD', str(n or '')).encode('ascii', 'ignore').decode().upper().strip()


def _estilo_periodo(nome, a, m):
    """Formato de uma pasta de competência ('MM', 'MMAAAA', 'MM-AAAA'…) se ela for do mês m (ano a), senão None.
    Aceita 09 · 9 · 092026 · 09-2026 · 09.2026 · 09_2026 · 09 2026 · 0926 · 09-26 · 2026-09 · 202609 · Setembro · SET-2026,
    com ou sem texto depois ("09 - Setembro")."""
    n = _norm(nome)
    mi = int(m)
    # mês numérico, com o ano junto (o ano tem que ser o da competência)
    r = re.match(r'^(\d{1,2})' + r'([\s._\-/]*)' + r'(\d{4}|\d{2})?(?!\d)(.*)$', n)
    if r and 1 <= int(r.group(1)) <= 12:
        ano = r.group(3)
        resto = r.group(4).strip(' -._')
        if resto and not re.match(r'^[A-Z]', resto):
            return None
        if ano and ano not in (a, a[2:]):
            return None
        if int(r.group(1)) != mi:
            return None
        sep = r.group(2) if ano else ''
        return ('MM' if len(r.group(1)) == 2 else 'M') + (sep + ('AAAA' if ano and len(ano) == 4 else 'AA') if ano else '')
    r = re.match(r'^(\d{4})([\s._\-/]*)(\d{2})(?!\d)', n)                        # 2026-09 / 202609
    if r:
        return (f'AAAA{r.group(2)}MM' if r.group(1) == a and int(r.group(3)) == mi else None)
    for i, (cheio, abv) in enumerate(zip(MESES, _ABREV)):                         # Setembro / SET-2026
        if re.match(rf'^({_norm(cheio)}|{abv})(?![A-Z])', n):
            ano = re.search(r'(\d{4}|\d{2})(?!\d)', n)
            if ano and ano.group(1) not in (a, a[2:]):
                return None
            return 'NOME' if i + 1 == mi else None
    return None


def _cria_periodo(pai, a, m):
    """Nome da pasta nova da competência, no mesmo formato das irmãs (o mais usado); sem irmãs, '09'."""
    estilos = {}
    try:
        for d in os.listdir(pai):
            if not os.path.isdir(os.path.join(pai, d)):
                continue
            for mm in range(1, 13):
                e = _estilo_periodo(d, a, f'{mm:02d}')
                if e:
                    estilos[e] = estilos.get(e, 0) + 1
                    break
    except OSError:
        pass
    if not estilos:                       # ano novo, ainda sem competências: segue o formato dos anos anteriores
        try:
            avo = os.path.dirname(pai)
            for ano in sorted(os.listdir(avo), reverse=True):
                ap = os.path.join(avo, ano)
                if not (re.fullmatch(r'\D*\d{4}\D*', _norm(ano)) and os.path.isdir(ap)) or ap == pai:
                    continue
                aa = re.search(r'\d{4}', ano).group()
                for d in os.listdir(ap):
                    for mm in range(1, 13):
                        e = _estilo_periodo(d, aa, f'{mm:02d}')
                        if e:
                            estilos[e] = estilos.get(e, 0) + 1
                            break
                if estilos:
                    break
        except OSError:
            pass
    e = max(estilos, key=estilos.get) if estilos else 'MM'
    if e == 'NOME':
        return MESES[int(m) - 1]
    troca = {'AAAA': a, 'AA': a[2:], 'MM': m, 'M': str(int(m))}
    return re.sub(r'AAAA|AA|MM|M', lambda t: troca[t.group()], e)


def _resolve_sub(raiz, modelo, comp):
    """Percorre a subpasta a partir da pasta da empresa, achando as pastas que já existem (sem diferenciar maiúsculas)
    e criando só as que faltam. {AAAA} = pasta do ano; {PERIODO} = pasta da competência em qualquer formato usual.
    Retorna (caminho | None, aviso, candidatos)."""
    a, m = comp.split('-')
    atual = raiz
    for seg in [x for x in re.split(r'[\\/]+', modelo or SUBPASTA_PADRAO) if x.strip()]:
        try:
            filhas = [d for d in os.listdir(atual) if os.path.isdir(os.path.join(atual, d))]
        except OSError:
            filhas = []
        if seg == '{PERIODO}':
            ach = [d for d in filhas if _estilo_periodo(d, a, m)]
            if len(ach) > 1:
                return None, f'Mais de uma pasta da competência {m}/{a} em {atual} — escolha a pasta da empresa no Admin.', [os.path.join(atual, d) for d in ach]
            atual = os.path.join(atual, ach[0] if ach else _cria_periodo(atual, a, m))
            continue
        alvo = seg.replace('{AAAA}', a).replace('{MM}', m).replace('{MES}', MESES[int(m) - 1]).replace('{AA}', a[2:])
        if seg == '{AAAA}':
            ach = [d for d in filhas if re.fullmatch(rf'\D*{a}\D*', _norm(d))]
        else:
            ach = [d for d in filhas if _norm(d) == _norm(alvo)]
        if len(ach) > 1 and alvo in ach:
            ach = [alvo]
        if len(ach) > 1:
            return None, f'Mais de uma pasta "{alvo}" em {atual} — escolha a pasta da empresa no Admin.', [os.path.join(atual, d) for d in ach]
        atual = os.path.join(atual, ach[0] if ach else alvo)
    return atual, '', []


def _nome_arq(nome):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', ' ', str(nome or '')).strip()
    return re.sub(r'\s+', ' ', s)[:90].rstrip(' .')


def destino_empresa(cfg, emp, comp):
    """(pasta | None, aviso, candidatos). Nunca escolhe entre duas pastas parecidas."""
    a, m = comp.split('-')
    mapa = cfg.get('mapa') or {}
    base = cfg.get('base') or ''
    fixa = mapa.get(f"{emp['id']}|{comp}")                 # pasta da competência apontada pelo Admin
    if fixa and os.path.isdir(fixa):
        return fixa, '', []
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
        cam, aviso, cand = _resolve_sub(raiz, cfg.get('subpasta') or SUBPASTA_PADRAO, comp)
        return cam, aviso, cand, 'periodo'
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
    # retificação: a Receita ainda mostra a mesma declaração → nada muda (não baixa nem emite nada)
    retif_de = re.sub(r'\D', '', str(emp.get('retifDe') or ''))
    if retif_de and r['decl'] and re.sub(r'\D', '', r['decl']) == retif_de:
        r['mesma'] = True
        return r
    suf = ''
    if retif_de and r['decl']:
        r['retificadora'], r['retifDe'] = True, retif_de
        r['msg'] = f"Retificadora · Decl. {r['decl']}"
        seq = re.sub(r'\D', '', r['decl'])[-3:]
        suf = f' (retificadora {seq})' if seq.isdigit() else ' (retificadora)'
    if not opc.get('baixar'):
        return r
    pasta, aviso, cand, nivel = (list(destino_empresa(opc.get('pastas') or {}, emp, comp)) + ['empresa'])[:4]
    if not pasta:
        r['pastaAviso'], r['candidatos'] = aviso, cand
        r['pastaChave'] = f"{emp['id']}|{comp}" if nivel == 'periodo' else emp['id']
        return r
    r['pasta'] = pasta
    nome = _nome_arq(emp['nome'])
    try:
        for rot, _arq, b in pdfs:
            tipo = 'Recibo' if 'recibo' in rot else 'Declaracao'
            r['arquivos'][tipo] = _grava(pasta, f"{'Recibo PGDAS-D' if tipo == 'Recibo' else 'Declaração PGDAS-D'} {m}-{a} - {nome}{suf}.pdf", b)
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
            r['arquivos']['DAS'] = _grava(pasta, f'DAS {m}-{a} - {nome}{suf}.pdf', das_pdf[0][2])
    except OSError as e:
        r['pastaAviso'] = f'Não consegui gravar o DAS: {e}'
        return r
    if r['dasNumero']:
        res = chamar(tok, cert, 'Consultar', contratante, cnpj, 'CONSEXTRATO16', {'numeroDas': r['dasNumero']})
        consumo['consulta'] += 1
        ex = _pdfs(res['dados']) if res['http'] == 200 else []
        if ex:
            try:
                r['arquivos']['Extrato'] = _grava(pasta, f'Extrato do DAS {m}-{a} - {nome}{suf}.pdf', ex[0][2])
            except OSError:
                pass
        elif res['http'] != 200:
            r['extratoAviso'] = ('Extrato não baixado: ' + res['msg'])[:200]
    return r


# ------------------------------------------------------------------ DCTFWeb (débitos da EFD-Reinf × declaração)
# Serviços do sistema DCTFWEB (mesmo contrato, cobrança por requisição), categoria 40 = Geral mensal:
#   • CONSDECCOMPLETA33 (Consultar): situação da declaração do período (em andamento / transmitida / não encontrada);
#   • CONSXMLDECLARACAO38 (Consultar): XML da declaração (ProcDctf) → débitos por origem e código de receita;
#   • TRANSDECLARACAO310 (Declarar): transmite o XML da Receita assinado pelo e-CNPJ do escritório (procurador);
#   • CONSRECIBO32 (Consultar): recibo de entrega em PDF.
# Base: IN RFB 2.005/2021 (DCTFWeb), com a DCTF extinta para fatos geradores a partir de 01/2025; prazo de entrega no
# último dia útil do mês seguinte ao dos fatos geradores (redação dada pela IN RFB 2.248/2025).
ORIGEM_DCTF = {'1': 'eSocial', '6': 'REINF CP', '7': 'REINF RET', '8': 'MIT'}
NS_DS = 'http://www.w3.org/2000/09/xmldsig#'


def _periodo_dctf(comp):
    a, m = comp.split('-')
    return {'categoria': 40, 'anoPA': a, 'mesPA': m}


def _dctf(tok, cert, contratante, cnpj, metodo, servico, dados, consumo, tipo='consulta'):
    res = chamar(tok, cert, metodo, contratante, cnpj, servico, dados, id_sistema='DCTFWEB')
    consumo[tipo] = consumo.get(tipo, 0) + 1
    return res


def _msgs_txt(res):
    return _txt(res.get('msg') or '')


def dctf_situacao(res):
    """CONSDECCOMPLETA33 → em_andamento | transmitida | sem_declaracao | semproc | erro.
    Só é "transmitida" com prova: a Receita devolveu a declaração e nada diz que ela não existe."""
    t = _msgs_txt(res)
    if res.get('http') == 403 or 'procura' in t or 'nao autorizad' in t:
        return 'semproc'
    if 'em andamento' in t:
        return 'em_andamento'
    if re.search(r'nao (foi )?(encontrad|localizad)|nao existe|inexistente|nenhuma declara|sem declara', t):
        return 'sem_declaracao'
    if 200 <= (res.get('http') or 0) < 300 and res.get('dados'):
        return 'transmitida'
    if 200 <= (res.get('http') or 0) < 300:
        return 'sem_declaracao'
    return 'erro'


def dctf_xml(dados):
    if isinstance(dados, dict):
        b64 = dados.get('XMLStringBase64') or dados.get('xmlStringBase64') or _acha(dados, {'xmlstringbase64', 'xmlbase64', 'xml'})
    else:
        b64 = dados if isinstance(dados, str) else None
    if not b64:
        return None
    b64 = str(b64).strip()
    if b64.startswith('<'):
        return b64
    try:
        return base64.b64decode(b64).decode('utf-8')
    except Exception:
        return None


def _local(tag):
    return tag.split('}', 1)[-1] if isinstance(tag, str) else ''


def _numxml(v):
    s = str(v or '').strip()
    if not s:
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return round(float(s), 2)
    except ValueError:
        return None


_RX_COD = re.compile(r'(cod|codigo)\w*(rec|receita)|^cr\w*$|codreceita|receita', re.I)
_RX_VAL_DEB = re.compile(r'(valor|vlr|vl)\w*(apurad|debito|principal|devido)|debito\w*apurad', re.I)
_RX_SALDO = re.compile(r'saldo\w*pagar', re.I)


_RX_VAL_ALT = re.compile(r'^(valor|vlr|vl)', re.I)
_RX_NAO_DEB = re.compile(r'credit|dedu|compens|suspens|pagament|parcel|exclus', re.I)


def _arvore(raiz, limite=90):
    """Caminhos das tags do XML, sem nenhum valor (para o passo a passo quando o leiaute surpreende)."""
    out, vistos = [], set()

    def anda(el, cam):
        nm = _local(el.tag)
        c = f'{cam}/{nm}' if cam else nm
        if not len(el):
            tx = (el.text or '').strip()
            tipo = 'n' if re.fullmatch(r'[\d.,-]+', tx or 'x') else 't'
            k = f'{c}[{tipo}]'
            if k not in vistos and len(out) < limite:
                vistos.add(k)
                out.append(k)
            return
        for f in el:
            anda(f, c)
    anda(raiz, '')
    return out


def dctf_debitos(xml):
    """Débitos da declaração por origem (1 eSocial, 6 REINF CP, 7 REINF RET, 8 MIT).
    2.4.18: no XML real o <sistemaUsuarioDctf> fica num bloco só de identificação (<identEfd> + <sistemaUsuarioDctf>);
    os débitos ficam ao lado. Para cada origem, o "escopo" é o maior bloco acima dela que não tem outra origem dentro;
    nele, cada elemento com um código de receita é um débito (créditos, deduções, compensações e pagamentos ficam fora).
    O leiaute não é publicado: a leitura é tolerante e devolve os caminhos das tags (sem valores) para o passo a passo."""
    from lxml import etree
    raiz = etree.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml, etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    out = {'origens': {}, 'reinf': {}, 'reinfOrigem': {}, 'outros': {}, 'codigos': [], 'saldo': 0.0, 'estrutura': [], 'arvore': _arvore(raiz), 'periodo': '', 'cnpj': ''}
    for el in raiz.iter():
        n = _local(el.tag).lower()
        if n in ('perapuracao', 'periodoapuracao') and not out['periodo']:
            out['periodo'] = (el.text or '').strip()
        if n in ('nrinsc', 'insccontrib', 'nrinscricao', 'cnpj') and not out['cnpj']:
            out['cnpj'] = re.sub(r'\D', '', el.text or '')
    sis = [el for el in raiz.iter() if _local(el.tag) == 'sistemaUsuarioDctf']
    arv = raiz.getroottree()
    cp = arv.getpath                   # a chave é o caminho do nó (o id() dos objetos do lxml muda a cada acesso)
    conta = {}
    for el in sis:
        for anc in el.iterancestors():
            conta[cp(anc)] = conta.get(cp(anc), 0) + 1

    def eh_cod(el):
        return not len(el) and _RX_COD.search(_local(el.tag)) and re.fullmatch(r'\d{4}(-?\d{2})?', (el.text or '').strip())

    usados = set()
    for s0 in sis:
        origem = ORIGEM_DCTF.get((s0.text or '').strip(), 'outra')
        escopo = s0.getparent()
        if escopo is None:
            continue
        for anc in s0.iterancestors():
            if conta.get(cp(anc), 0) == 1:
                escopo = anc
            else:
                break
        debitos = []
        for el in escopo.iter():
            if eh_cod(el):
                pai = el.getparent()
                if pai is None or cp(pai) in usados:
                    continue
                cam = [_local(x.tag) for x in pai.iterancestors()][:6] + [_local(pai.tag)]
                if any(_RX_NAO_DEB.search(c) for c in cam):
                    continue
                usados.add(cp(pai))
                debitos.append((el, pai))
        if len(out['estrutura']) < 4:
            out['estrutura'].append(sorted({_local(x.tag) for x in escopo.iter() if not len(x)})[:40])
        for cod_el, pai in debitos:
            tx = cod_el.text.strip()
            cod, ext = tx[:4], re.sub(r'\D', '', tx)[4:6]
            val, saldo, alt, venc = None, None, None, ''
            for el in pai.iter():
                if len(el) or el is cod_el:
                    continue
                nm, t = _local(el.tag), (el.text or '').strip()
                if not t:
                    continue
                if not venc and re.search(r'venc', nm, re.I) and re.search(r'\d{4}-?\d{2}-?\d{2}|\d{2}/\d{2}/\d{4}', t):
                    venc = t[:10]
                elif val is None and _RX_VAL_DEB.search(nm):
                    val = _numxml(t)
                elif saldo is None and _RX_SALDO.search(nm):
                    saldo = _numxml(t)
                elif alt is None and _RX_VAL_ALT.search(nm):
                    alt = _numxml(t)
            v = val if val is not None else saldo if saldo is not None else (alt or 0.0)
            out['origens'][origem] = round(out['origens'].get(origem, 0.0) + v, 2)
            out['saldo'] = round(out['saldo'] + (saldo or 0.0), 2)
            out['codigos'].append({'cod': cod, 'ext': ext, 'origem': origem, 'valor': round(v, 2), 'venc': venc})
            alvo = out['reinf'] if origem.startswith('REINF') else out['outros']
            alvo[cod] = round(alvo.get(cod, 0.0) + v, 2)
            if origem.startswith('REINF'):
                out['reinfOrigem'][cod] = origem
    # nenhum débito ligado a uma origem: se a declaração só tem UMA origem, os débitos soltos são dela
    origs = {ORIGEM_DCTF.get((x.text or '').strip(), 'outra') for x in sis}
    if not out['codigos'] and len(origs) == 1:
        origem = origs.pop()
        for el in raiz.iter():
            if eh_cod(el) and el.getparent() is not None:
                pai = el.getparent()
                cam = [_local(x.tag) for x in pai.iterancestors()][:6] + [_local(pai.tag)]
                if any(_RX_NAO_DEB.search(c) for c in cam):
                    continue
                v = next((_numxml(f.text) for f in pai if not len(f) and f is not el and (_RX_VAL_DEB.search(_local(f.tag)) or _RX_VAL_ALT.search(_local(f.tag)))), None) or 0.0
                cod = el.text.strip()[:4]
                out['codigos'].append({'cod': cod, 'ext': re.sub(r'\D', '', el.text)[4:6], 'origem': origem, 'valor': round(v, 2), 'venc': ''})
                out['origens'][origem] = round(out['origens'].get(origem, 0.0) + v, 2)
                alvo = out['reinf'] if origem.startswith('REINF') else out['outros']
                alvo[cod] = round(alvo.get(cod, 0.0) + v, 2)
                if origem.startswith('REINF'):
                    out['reinfOrigem'][cod] = origem
    return out


def dctf_conferir_empresa(tok, cert, contratante, emp, comp, consumo):
    cnpj = re.sub(r'\D', '', emp.get('cnpj') or '')
    r = {'cnpj': cnpj, 'situacao': '', 'msg': ''}
    res = _dctf(tok, cert, contratante, cnpj, 'Consultar', 'CONSDECCOMPLETA33', _periodo_dctf(comp), consumo)
    r['situacao'] = dctf_situacao(res)
    if r['situacao'] in ('semproc', 'erro', 'sem_declaracao'):
        r['msg'] = (res.get('msg') or '')[:300]
        if r['situacao'] == 'semproc':
            r['msg'] = 'Sem procuração eletrônica no e-CAC para a Liddera (DCTFWeb). ' + r['msg'][:160]
        return r
    rx = _dctf(tok, cert, contratante, cnpj, 'Consultar', 'CONSXMLDECLARACAO38', _periodo_dctf(comp), consumo)
    xml = dctf_xml(rx.get('dados')) if rx.get('http') == 200 else None
    if not xml:
        r.update(situacao='erro', msg=('Sem o XML da declaração: ' + (rx.get('msg') or f"HTTP {rx.get('http')}"))[:300])
        return r
    try:
        d = dctf_debitos(xml)
    except Exception as e:                                       # XML que não abre: não afirma nada
        r.update(situacao='erro', msg=f'Não consegui ler o XML da declaração: {e}'[:300])
        return r
    if d['cnpj'] and d['cnpj'][:8] != cnpj[:8]:
        r.update(situacao='erro', msg='O XML devolvido é de outro contribuinte.')
        return r
    r.update(origens=d['origens'], reinf=d['reinf'], reinfOrigem=d['reinfOrigem'], outros=d['outros'], codigos=d['codigos'][:80], saldo=d['saldo'], estrutura=d['estrutura'], arvore=d['arvore'])
    return r


def _c14n_trecho(el):
    """C14N 1.0 inclusivo de um trecho do documento. O lxml, ao canonicalizar um subelemento cujo namespace padrão vem
    de um ancestral, escreve xmlns="" nos netos (defeito do libxml2): por isso o trecho é copiado para uma árvore própria
    com TODOS os namespaces em vigor no ápice — exatamente o que a especificação manda renderizar."""
    import copy
    from lxml import etree
    novo = etree.Element(el.tag, attrib=dict(el.attrib), nsmap=el.nsmap)
    novo.text = el.text
    for ch in el:
        novo.append(copy.deepcopy(ch))
    return etree.tostring(novo, method='c14n', exclusive=False, with_comments=False)


def assinar_dctf(xml, chave_priv, cert_der_b64):
    """XMLDSig envelopada do <ConteudoDeclaracao id="..."> do ProcDctf: C14N 1.0, SHA-256, RSA-SHA256, X509Certificate;
    a assinatura vai como último filho de <ProcDctf>. Assina o XML devolvido pela Receita sem alterar o conteúdo."""
    import hashlib
    from lxml import etree
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    raiz = etree.fromstring(xml.encode('utf-8'), etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_blank_text=False))
    alvo = next((el for el in raiz.iter() if _local(el.tag) == 'ConteudoDeclaracao'), None)
    if alvo is None:
        raise ValueError('o XML não tem o ConteudoDeclaracao')
    ref = alvo.get('id') or alvo.get('Id') or alvo.get('ID')
    if not ref:
        raise ValueError('o ConteudoDeclaracao não tem id')
    proc = raiz if _local(raiz.tag) == 'ProcDctf' else next((el for el in raiz.iter() if _local(el.tag) == 'ProcDctf'), raiz)
    for velha in [el for el in proc if _local(el.tag) == 'Signature']:
        proc.remove(velha)
    digest = base64.b64encode(hashlib.sha256(_c14n_trecho(alvo)).digest()).decode('ascii')
    E = lambda n: '{%s}%s' % (NS_DS, n)                       # noqa: E731
    sig = etree.SubElement(proc, E('Signature'), nsmap={None: NS_DS})
    si = etree.SubElement(sig, E('SignedInfo'))
    etree.SubElement(si, E('CanonicalizationMethod'), Algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
    etree.SubElement(si, E('SignatureMethod'), Algorithm='http://www.w3.org/2001/04/xmldsig-more#rsa-sha256')
    rf = etree.SubElement(si, E('Reference'), URI='#' + ref)
    tr = etree.SubElement(rf, E('Transforms'))
    etree.SubElement(tr, E('Transform'), Algorithm='http://www.w3.org/2000/09/xmldsig#enveloped-signature')
    etree.SubElement(tr, E('Transform'), Algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
    etree.SubElement(rf, E('DigestMethod'), Algorithm='http://www.w3.org/2001/04/xmlenc#sha256')
    etree.SubElement(rf, E('DigestValue')).text = digest
    canon_si = _c14n_trecho(si)
    etree.SubElement(sig, E('SignatureValue')).text = base64.b64encode(chave_priv.sign(canon_si, padding.PKCS1v15(), hashes.SHA256())).decode('ascii')
    ki = etree.SubElement(sig, E('KeyInfo'))
    etree.SubElement(etree.SubElement(ki, E('X509Data')), E('X509Certificate')).text = cert_der_b64
    return etree.tostring(raiz.getroottree(), encoding='UTF-8', xml_declaration=True).decode('utf-8')


def _numero_recibo(pdf):
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            t = '\n'.join((pg.extract_text() or '') for pg in doc.pages[:2])
        m = re.search(r'recibo[^\n\d]{0,40}([\d][\d.\-/]{8,})', t, re.I)
        return m.group(1) if m else ''
    except Exception:
        return ''


def dctf_transmitir_empresa(tok, cert, contratante, emp, comp, consumo, chave_priv, cert_b64):
    """Transmite só se a declaração continua em andamento e os débitos da REINF ainda conferem com o que a equipe viu."""
    cnpj = re.sub(r'\D', '', emp.get('cnpj') or '')
    r = {'cnpj': cnpj, 'ok': False, 'msg': ''}
    sit = dctf_situacao(_dctf(tok, cert, contratante, cnpj, 'Consultar', 'CONSDECCOMPLETA33', _periodo_dctf(comp), consumo))
    if sit == 'transmitida':
        r.update(ok=True, jaTransmitida=True, msg='A DCTFWeb já estava transmitida.')
    elif sit != 'em_andamento':
        r['msg'] = {'sem_declaracao': 'A Receita não tem DCTFWeb em andamento nesta competência.', 'semproc': 'Sem procuração eletrônica no e-CAC para a Liddera (DCTFWeb).'}.get(sit, 'A situação da DCTFWeb não pôde ser confirmada; nada foi transmitido.')
        return r
    if not r.get('jaTransmitida'):
        rx = _dctf(tok, cert, contratante, cnpj, 'Consultar', 'CONSXMLDECLARACAO38', _periodo_dctf(comp), consumo)
        xml = dctf_xml(rx.get('dados')) if rx.get('http') == 200 else None
        if not xml:
            r['msg'] = 'Sem o XML da declaração na Receita; nada foi transmitido.'
            return r
        d = dctf_debitos(xml)
        outras = {k: v for k, v in d['origens'].items() if not k.startswith('REINF') and v > 0.009}
        if emp.get('esperadoTudo') is not None:
            # 2.4.17: declaração com folha (eSocial) e/ou MIT — a pessoa confirmou que estão fechados. Todos os débitos
            # (de todas as origens) precisam ser exatamente os que ela viu na tela.
            visto = {k[:4]: round(float(v), 2) for k, v in (emp.get('esperadoTudo') or {}).items()}
            agora = {}
            for x in d['codigos']:
                agora[x['cod']] = round(agora.get(x['cod'], 0.0) + x['valor'], 2)
            if not agora or any(abs(agora.get(k, 0.0) - v) > 0.01 for k, v in visto.items()) or any(k not in visto and v > 0.01 for k, v in agora.items()):
                r.update(msg='Os débitos da DCTFWeb mudaram desde que você conferiu; nada foi transmitido. Atualize a DCTFWeb e confira de novo.', origens=d['origens'])
                return r
        else:
            esperado = {k[:4]: round(float(v), 2) for k, v in (emp.get('esperado') or {}).items()}
            if not esperado or any(abs(d['reinf'].get(k, 0.0) - v) > 0.01 for k, v in esperado.items()) or any(k not in esperado and v > 0.01 for k, v in d['reinf'].items()):
                r.update(msg='Os débitos da REINF na DCTFWeb mudaram desde a conferência; nada foi transmitido. Atualize a conferência.', reinf=d['reinf'])
                return r
            if outras:                                   # eSocial / MIT sem a confirmação da pessoa: não transmite
                r.update(msg='A DCTFWeb tem débitos de ' + ', '.join(sorted(outras)) + ': confirme a folha e o MIT antes de transmitir.', origens=d['origens'])
                return r
        assinado = assinar_dctf(xml, chave_priv, cert_b64)
        dados = {**_periodo_dctf(comp), 'xmlAssinadoBase64': base64.b64encode(assinado.encode('utf-8')).decode('ascii')}
        rt = _dctf(tok, cert, contratante, cnpj, 'Declarar', 'TRANSDECLARACAO310', dados, consumo, 'declaracao')
        t = _msgs_txt(rt)
        if 200 <= (rt.get('http') or 0) < 300 and 'sucesso' in t:
            r.update(ok=True, msg='Transmitida.')
        elif re.search(r'ja_?\s*transmitida|ja foi transmitida', t):
            r.update(ok=True, jaTransmitida=True, msg='A DCTFWeb já estava transmitida.')
        else:
            r['msg'] = ('A Receita não aceitou a transmissão: ' + (rt.get('msg') or f"HTTP {rt.get('http')}"))[:400]
            return r
        r.update(origens=d['origens'], reinf=d['reinf'], saldo=d['saldo'])
    # recibo de entrega (PDF) na pasta do cliente
    rr = _dctf(tok, cert, contratante, cnpj, 'Consultar', 'CONSRECIBO32', _periodo_dctf(comp), consumo)
    pdfs = _pdfs(rr.get('dados')) if rr.get('http') == 200 else []
    if not pdfs and isinstance(rr.get('dados'), dict) and rr['dados'].get('PDFByteArrayBase64'):
        try:
            pdfs = [('recibo', '', base64.b64decode(rr['dados']['PDFByteArrayBase64']))]
        except Exception:
            pdfs = []
    if pdfs:
        r['recibo'] = _numero_recibo(pdfs[0][2])
        pasta = emp.get('pasta') or ''
        if pasta:
            a, m = comp.split('-')
            try:
                r['arquivo'] = _grava(pasta, f'Recibo DCTFWeb {m}{a} - {_nome_arq(emp.get("nome") or cnpj)}.pdf', pdfs[0][2])
            except OSError as e:
                r['aviso'] = f'Recibo não gravado na pasta: {e}'[:200]
    else:
        r['aviso'] = ('Recibo ainda não disponível: ' + (rr.get('msg') or ''))[:200]
    return r


ORIGEM_ID = {'eSocial': 1, 'REINF CP': 6, 'REINF RET': 7, 'MIT': 8}


def _pdf_resposta(dados):
    if isinstance(dados, str):
        try:
            dados = json.loads(dados)
        except Exception:
            return None
    if isinstance(dados, dict):
        for k in ('PDFByteArrayBase64', 'pdfByteArrayBase64', 'pdf', 'darf'):
            v = dados.get(k)
            if isinstance(v, str) and len(v) > 200:
                try:
                    b = base64.b64decode(v)
                    if b[:4] == b'%PDF':
                        return b
                except Exception:
                    pass
        pdfs = _pdfs(dados)
        if pdfs:
            return pdfs[0][2]
    return None


def dctf_guia_empresa(tok, cert, contratante, emp, comp, consumo):
    """Guia (DARF) da DCTFWeb: GERARGUIA31 (declaração transmitida) ou GERARGUIAANDAMENTO313 (em andamento).
    idsSistemaOrigem escolhe as origens dos débitos (1 eSocial, 6 REINF CP, 7 REINF RET, 8 MIT): a guia só tem as receitas
    dessas origens. A Receita calcula valor, vencimento, multa/juros e o código de barras; o PDF vai para a pasta do cliente."""
    cnpj = re.sub(r'\D', '', emp.get('cnpj') or '')
    r = {'cnpj': cnpj, 'ok': False, 'msg': ''}
    sit = emp.get('situacao') or dctf_situacao(_dctf(tok, cert, contratante, cnpj, 'Consultar', 'CONSDECCOMPLETA33', _periodo_dctf(comp), consumo))
    dados = dict(_periodo_dctf(comp))
    ids = sorted({ORIGEM_ID[o] for o in (emp.get('origens') or []) if o in ORIGEM_ID})
    if ids:
        dados['idsSistemaOrigem'] = ids
    if sit == 'transmitida':
        if emp.get('data'):
            dados['DataAcolhimentoProposta'] = int(re.sub(r'\D', '', str(emp['data']))[:8])
        res = _dctf(tok, cert, contratante, cnpj, 'Emitir', 'GERARGUIA31', dados, consumo, 'emissao')
    elif sit == 'em_andamento':
        res = _dctf(tok, cert, contratante, cnpj, 'Emitir', 'GERARGUIAANDAMENTO313', dados, consumo, 'emissao')
    else:
        r['msg'] = {'sem_declaracao': 'A Receita não tem DCTFWeb nesta competência.', 'semproc': 'Sem procuração eletrônica no e-CAC para a Liddera (DCTFWeb).'}.get(sit, 'A situação da DCTFWeb não pôde ser confirmada.')
        return r
    pdf = _pdf_resposta(res.get('dados')) if 200 <= (res.get('http') or 0) < 300 else None
    if not pdf:
        r['msg'] = ('A Receita não gerou a guia: ' + (res.get('msg') or f"HTTP {res.get('http')}"))[:400]
        return r
    r.update(ok=True, emAndamento=(sit == 'em_andamento'), msg='Guia gerada.')
    pasta = emp.get('pasta') or ''
    if pasta:
        a, m = comp.split('-')
        rot = emp.get('rotulo') or 'DCTFWeb'
        try:
            r['arquivo'] = _grava(pasta, f'DARF {rot} {m}-{a} - {_nome_arq(emp.get("nome") or cnpj)}.pdf', pdf)
        except OSError as e:
            r['aviso'] = f'Guia não gravada na pasta: {e}'[:200]
    return r


# ------------------------------------------------------------------ MIT (2.4.26 · 2.4.27)
# O MIT vai com a Liddera (e-CNPJ, contratante) como procuradora dos clientes — o mesmo caminho da DCTFWeb e do PGDAS.
# O responsável pela apuração (CPF, telefone, e-mail, CRC) vai só DENTRO do MIT (DadosIniciais.ResponsavelApuracao).
MIT_SIT = {1: 'em edição com pendências', 2: 'em edição', 3: 'encerrada', 4: 'encerramento em curso'}


def _mit_lista(res):
    d = res.get('dados')
    lst = _acha(d, ['Apuracoes', 'apuracoes']) if isinstance(d, (dict, list)) else None
    if lst is None and isinstance(d, list):
        lst = d
    return [x for x in (lst or []) if isinstance(x, dict)]


def _k(x, *nomes):
    for n in nomes:
        for k, v in x.items():
            if k.lower() == n.lower():
                return v
    return None


def mit_consultar_empresa(tok, cert, contratante, proc, emp, comp, consumo):
    """LISTAAPURACOES317: a apuração MIT mais recente do período (situação, valor, data)."""
    cnpj = re.sub(r'\D', '', emp.get('cnpj') or '')
    a, m = comp.split('-')
    res = chamar(tok, cert, 'Consultar', contratante, cnpj, 'LISTAAPURACOES317', {'anoApuracao': int(a), 'mesApuracao': int(m)}, id_sistema='MIT', proc=proc)
    consumo['consulta'] = consumo.get('consulta', 0) + 1
    r = {'cnpj': cnpj, 'ok': False, 'msg': ''}
    if not (200 <= (res.get('http') or 0) < 300):
        txt = res.get('msg') or f"HTTP {res.get('http')}"
        r['msg'] = ('Sem procuração eletrônica no e-CAC para a Liddera (MIT). ' if re.search(r'procura', txt, re.I) else '') + txt[:300]
        r['semProc'] = bool(re.search(r'procura', txt, re.I))
        return r
    aps = []
    for x in _mit_lista(res):
        try:
            sid = int(_k(x, 'situacao', 'situacaoApuracao') or 0)
        except (TypeError, ValueError):
            sid = 0
        aps.append({'id': _k(x, 'idApuracao'), 'situacao': sid, 'texto': MIT_SIT.get(sid, str(sid)),
                    'data': str(_k(x, 'dataEncerramento') or ''), 'valor': _num(_k(x, 'valorTotalApurado')) or 0.0})
    aps.sort(key=lambda y: int(y['id'] or 0))
    r.update(ok=True, apuracoes=aps, ultima=aps[-1] if aps else None)
    return r


def mit_enviar_empresa(tok, cert, contratante, proc, emp, comp, consumo, chk_dctf=False):
    """ENCAPURACAO314 + acompanhamento (SITUACAOENC315). Não envia se já houver apuração encerrada no período.
    chk_dctf (sem movimento): antes confere se a DCTFWeb do mês tem débito de outra origem — se tiver, não envia."""
    cnpj = re.sub(r'\D', '', emp.get('cnpj') or '')
    r = {'cnpj': cnpj, 'ok': False, 'msg': ''}
    ja = mit_consultar_empresa(tok, cert, contratante, proc, emp, comp, consumo)
    if not ja['ok']:
        r['msg'] = ja['msg']
        return r
    enc = [x for x in ja['apuracoes'] if x['situacao'] in (3, 4)]
    if enc:
        u = enc[-1]
        brl = f"{u['valor']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        r.update(msg=f"Já existe apuração MIT {u['texto']} neste período (nº {u['id']}, R$ {brl}).",
                 jaEnviado=True, idApuracao=u['id'], situacao=u['situacao'])
        return r
    if chk_dctf:
        d = dctf_conferir_empresa(tok, cert, contratante, {'cnpj': cnpj}, comp, consumo)
        if d.get('situacao') in ('em_andamento', 'transmitida'):
            tot = sum(float(v or 0) for v in (d.get('reinf') or {}).values()) + sum(float(v or 0) for v in (d.get('outros') or {}).values())
            if tot > 0 or d.get('codigos'):
                r['msg'] = 'A DCTFWeb deste mês já tem débitos de outra origem (eSocial / EFD-Reinf): o MIT sem movimento não foi enviado.'
                return r
        elif d.get('situacao') not in ('sem_declaracao',):
            r['msg'] = 'Não consegui confirmar a DCTFWeb do mês (necessário para o sem movimento): ' + (d.get('msg') or d.get('situacao') or '')
            return r
    res = chamar(tok, cert, 'Declarar', contratante, cnpj, 'ENCAPURACAO314', emp['payload'], id_sistema='MIT', proc=proc)
    consumo['declaracao'] = consumo.get('declaracao', 0) + 1
    d = res.get('dados') if isinstance(res.get('dados'), dict) else {}
    prot = _k(d, 'protocoloEncerramento') if d else None
    if not (200 <= (res.get('http') or 0) < 300) or not prot:
        r['msg'] = ('A Receita não aceitou o MIT: ' + (res.get('msg') or f"HTTP {res.get('http')}"))[:500]
        return r
    r.update(protocolo=prot, idApuracao=_k(d, 'idApuracao'))
    sit, avisos, data = 4, [], ''
    for _ in range(18):                                          # até ~90 s
        time.sleep(5)
        rs = chamar(tok, cert, 'Apoiar', contratante, cnpj, 'SITUACAOENC315', {'protocoloEncerramento': prot}, id_sistema='MIT', proc=proc)
        ds = rs.get('dados') if isinstance(rs.get('dados'), dict) else {}
        try:
            sit = int(_k(ds, 'situacaoApuracao') or sit)
        except (TypeError, ValueError):
            pass
        avisos = [str(a) for a in (_k(ds, 'avisosDctf') or []) if a]
        data = str(_k(ds, 'dataEncerramento') or '')
        if _k(ds, 'idApuracao'):
            r['idApuracao'] = _k(ds, 'idApuracao')
        if sit != 4:
            break
    r.update(situacao=sit, texto=MIT_SIT.get(sit, str(sit)), avisos=avisos[:10], dataEncerramento=data)
    if sit == 3:
        r.update(ok=True, msg='MIT encerrado' + (f' · {avisos[0]}' if avisos else ''))
    elif sit == 4:
        r.update(ok=True, emCurso=True, msg='MIT enviado; o encerramento ainda está em curso na Receita (consulte de novo em alguns minutos).')
    else:
        r['msg'] = f'O MIT ficou "{MIT_SIT.get(sit, sit)}" na Receita: ' + ('; '.join(avisos) or 'confira as pendências no portal da DCTFWeb.')
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
        cert = (cert_pem, key_pem)
        if acao.startswith('mit_'):
            proc = None                                         # autor do pedido = a própria Liddera (contratante)
            consumo = {'consulta': 0, 'emissao': 0, 'declaracao': 0}
            if acao == 'mit_consultar':
                out = []
                for emp in p.get('empresas') or []:
                    try:
                        out.append(mit_consultar_empresa(tok, cert, contratante, proc, emp, p['comp'], consumo))
                    except Exception as e:
                        out.append({'cnpj': emp.get('cnpj'), 'ok': False, 'msg': f'Falha na consulta: {e}'[:300]})
                return {'ok': True, 'token': tok, 'proc': proc, 'resultados': out, 'consumo': consumo}
            if acao == 'mit_enviar':
                import mit as _mit
                emp = dict(p.get('empresa') or {})
                sem = bool(p.get('semMovimento'))
                try:
                    # sem movimento: a DCTFWeb (sem movimento) é transmitida logo após o encerramento (TransmissaoImediata)
                    emp['payload'] = _mit.montar(emp.get('dados') or {}, p.get('resp') or {}, sem_movimento=sem,
                                                 tributacao=emp.get('tributacao'), extras=emp.get('extras'), transmissao_imediata=sem)
                except (ValueError, KeyError) as e:
                    return {'ok': True, 'token': tok, 'proc': proc, 'resultado': {'cnpj': emp.get('cnpj'), 'ok': False, 'msg': str(e)[:300]}, 'consumo': consumo}
                try:
                    r = mit_enviar_empresa(tok, cert, contratante, proc, emp, p['comp'], consumo, chk_dctf=sem)
                except Exception as e:
                    r = {'cnpj': (p.get('empresa') or {}).get('cnpj'), 'ok': False, 'msg': f'Falha no envio: {e}'[:300]}
                return {'ok': True, 'token': tok, 'proc': proc, 'resultado': r, 'consumo': consumo}
            return {'ok': False, 'erro': 'Ação do MIT desconhecida.', 'token': tok}
        if acao == 'dctf_conferir':
            consumo = {'consulta': 0, 'emissao': 0, 'declaracao': 0}
            out = []
            for emp in p.get('empresas') or []:
                try:
                    out.append(dctf_conferir_empresa(tok, cert, contratante, emp, p['comp'], consumo))
                except Exception as e:                          # uma empresa com problema não para as outras
                    out.append({'cnpj': emp.get('cnpj'), 'situacao': 'erro', 'msg': f'Falha na consulta: {e}'[:300]})
            return {'ok': True, 'token': tok, 'resultados': out, 'consumo': consumo}
        if acao == 'dctf_guia':
            consumo = {'consulta': 0, 'emissao': 0, 'declaracao': 0}
            try:
                r = dctf_guia_empresa(tok, cert, contratante, p['empresa'], p['comp'], consumo)
            except Exception as e:
                r = {'cnpj': (p.get('empresa') or {}).get('cnpj'), 'ok': False, 'msg': f'Falha ao gerar a guia: {e}'[:300]}
            return {'ok': True, 'token': tok, 'resultado': r, 'consumo': consumo}
        if acao == 'dctf_transmitir':
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography import x509
            from cryptography.hazmat.primitives.serialization import Encoding
            with open(key_pem, 'rb') as fh:
                chave = load_pem_private_key(fh.read(), None)
            with open(cert_pem, 'rb') as fh:
                crt = x509.load_pem_x509_certificate(fh.read())
            cert_b64 = base64.b64encode(crt.public_bytes(Encoding.DER)).decode('ascii')
            consumo = {'consulta': 0, 'emissao': 0, 'declaracao': 0}
            try:
                r = dctf_transmitir_empresa(tok, cert, contratante, p['empresa'], p['comp'], consumo, chave, cert_b64)
            except Exception as e:
                r = {'cnpj': (p.get('empresa') or {}).get('cnpj'), 'ok': False, 'msg': f'Falha na transmissão: {e}'[:300]}
            return {'ok': True, 'token': tok, 'resultado': r, 'consumo': consumo}
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
            res = {'ok': False, 'erro': f'Falha na consulta à Receita: {e}'}
    with open(opt('--json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))
