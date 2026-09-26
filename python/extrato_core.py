"""
Núcleo de leitura de extratos bancários (Word/.docx exportado de PDF) —
módulo de Conciliação de Fornecedores, Liddera | Inteligência em Negócios.

Cada banco tem um layout de tabela DIFERENTE (confirmado analisando exemplos
reais dos 16 bancos que a Liddera usa: ITAU, BRADESCO, SICOOB, STONE, INTER,
SAFRA, SANTANDER, SISPRIME, TRIBANCO, AMAZONIA, BANCO_DO_BRASIL, CORA,
CREDISIS, CRESOL, INFINITYPAY, INFOPAGO) — por isso um parser DEDICADO por
banco, não um genérico. Todos devolvem a MESMA estrutura de saída (lista de
dicts: data, descricao, valor, cnpj, tipo), pra o resto do sistema (a
conciliação com o plano de contas) não precisar saber qual banco gerou aquele
extrato.

Se o parser fixo de um banco não achar nenhuma transação, ou achar dado que
não bate (data/valor inválido, ou soma não bate com o saldo declarado quando
o extrato traz esse total), cai pra IA como reforço — ver `precisa_reforco_ia()`.
"""
import re


def _parse_valor(txt):
    """Converte string de valor BR (R$ 1.234,56 / -R$ 1.234,56 / 1.234,56D /
    +1.234,56) pra float com sinal. Aceita as variações vistas nos 16 bancos."""
    if not txt:
        return None
    txt = txt.strip()
    if txt in ('---', '', '-'):
        return None
    neg = False
    if txt.startswith('-'):
        neg = True
        txt = txt[1:].strip()
    elif txt.startswith('+'):
        txt = txt[1:].strip()
    txt_upper = txt.upper()
    if txt_upper.endswith('D'):
        neg = True
        txt = txt[:-1].strip()
    elif txt_upper.endswith('C'):
        txt = txt[:-1].strip()
    txt = txt.replace('R$', '').strip()
    txt = re.sub(r',,', ',', txt)  # vírgula duplicada (visto no AMAZONIA, resíduo da conversão do PDF)
    txt = txt.replace('.', '').replace(',', '.')
    try:
        v = float(txt)
    except ValueError:
        return None
    return -v if neg else v


_MESES = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12,
}
_DATA_BR_RE = re.compile(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?')
_DATA_EXTENSO_RE = re.compile(r'(\d{1,2})\s*(?:de\s*)?([A-Za-zçÇ]{3})[a-zçÇ]*,?\s*(?:de\s*)?(\d{4})?', re.IGNORECASE)


def _parse_data(txt, ano_padrao=None):
    """Aceita dd/mm, dd/mm/aaaa, dd/mm/aa, e "20 Jan, 2026" (InfinityPay/Cora
    style) — devolve 'dd/mm/aaaa' (string) ou None. `ano_padrao`: usado quando
    o extrato só traz dd/mm (ano vem do cabeçalho do período, não da linha)."""
    if not txt:
        return None
    txt = txt.strip()
    m = _DATA_BR_RE.search(txt)
    if m:
        d, mo, y = m.groups()
        d, mo = int(d), int(mo)
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return None
        if y:
            y = int(y)
            if y < 100:
                y += 2000
        else:
            y = ano_padrao
        if not y:
            return None
        return f'{d:02d}/{mo:02d}/{y}'
    m = _DATA_EXTENSO_RE.search(txt)
    if m:
        d, mes_txt, y = m.groups()
        mes = _MESES.get(mes_txt.lower()[:3])
        if not mes:
            return None
        y = int(y) if y else ano_padrao
        if not y:
            return None
        return f'{int(d):02d}/{mes:02d}/{y}'
    return None


_CNPJ_RE = re.compile(r'\d{2}\.?\d{3}\.?\d{3}[/\s]\d{4}-?\d{2}')
_CPF_RE = re.compile(r'\d{3}\.?\d{3}\.?\d{3}-\d{2}')


def _extrai_cnpj(txt):
    """Só CNPJ (14 dígitos) — CPF de pessoa física não interessa pra achar
    fornecedor no plano de contas (Passivo, Fornecedores é sempre PJ)."""
    m = _CNPJ_RE.search(txt or '')
    return re.sub(r'\D', '', m.group(0)) if m else None


def precisa_reforco_ia(transacoes, saldo_final_declarado=None, saldo_inicial_declarado=None):
    """Decide se o parser fixo falhou e precisa cair pra IA. Critérios
    combinados com o Rafael: (1) nenhuma transação encontrada; (2) alguma
    data/valor não interpretável (já teria virado None nos campos, aqui só
    confirma que não sobrou nenhuma); (3) soma não bate com o saldo final
    declarado, quando o extrato traz esse total."""
    if not transacoes:
        return True, 'nenhuma transação encontrada'
    if any(t['data'] is None or t['valor'] is None for t in transacoes):
        return True, 'data ou valor não reconhecido em pelo menos uma linha'
    if saldo_final_declarado is not None and saldo_inicial_declarado is not None:
        soma = sum(t['valor'] for t in transacoes)
        calculado = saldo_inicial_declarado + soma
        if abs(calculado - saldo_final_declarado) > 0.02:
            return True, f'soma não bate com o saldo declarado (calculado {calculado:.2f}, extrato diz {saldo_final_declarado:.2f})'
    return False, None


def parse_sicoob(caminho_docx, ano_padrao):
    """SICOOB — tabelas pequenas (uma por página, ~70+ num extrato de 1 mês),
    linha principal com Data(dd/mm)/Histórico/Valor+D-ou-C, seguida de 0+
    linhas de CONTINUAÇÃO (Data e Valor vazios) trazendo subtipo, nome do
    favorecido, CPF mascarado, ou "DOC.: NNNN" — tudo isso junto forma a
    descrição real da transação (o "Histórico" sozinho só diz um código
    genérico tipo "DÉB.TIT.COMPE.EFETI", não quem é o fornecedor).
    `ano_padrao`: obrigatório, o extrato só traz dd/mm em cada linha."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    saldo_inicial = None

    for t in d.tables:
        rows = [[c.text.strip() for c in r.cells] for r in t.rows]
        i = 0
        while i < len(rows):
            row = rows[i]
            if len(row) < 3:
                i += 1
                continue
            data_raw, hist, valor_raw = row[0], row[1], row[2]
            if not data_raw or data_raw.upper() == 'DATA':
                i += 1
                continue
            data_multilinha = '\n' in data_raw
            data = _parse_data(data_raw.split('\n')[0].strip(), ano_padrao)
            if data is None:
                # linha sem data reconhecível (ex.: rodapé "RESUMO", "(+) SALDO
                # EM CONTA:" etc.) — não é transação, encerra essa tabela.
                break
            valor = _parse_valor(valor_raw.split('\n')[0].replace('*', '').strip())
            if hist.upper() in ('SALDO ANTERIOR', 'SALDO BLOQ.ANTERIOR'):
                if hist.upper() == 'SALDO ANTERIOR':
                    saldo_inicial = valor
                i += 1
                continue
            if 'SALDO DO DIA' in hist.upper() and not data_multilinha:
                # "SALDO DO DIA" é só um checkpoint de saldo, não transação —
                # às vezes vem sozinho, às vezes emendado (sem separador) no
                # histórico de uma transação anterior (achado real, causava
                # diferença de milhares de reais na conferência do saldo).
                # Só NÃO pula quando a data também veio em 2 linhas (aí a
                # PRIMEIRA data/valor already are a transação de verdade,
                # tratado abaixo via split('\n')[0]).
                i += 1
                continue
            detalhes = []
            j = i + 1
            while j < len(rows) and len(rows[j]) >= 2 and not rows[j][0]:
                texto_detalhe = rows[j][1].strip()
                if texto_detalhe:
                    detalhes.append(texto_detalhe)
                j += 1
            descricao_completa = (hist + ' ' + ' '.join(detalhes)).strip()
            transacoes.append({
                'data': data, 'descricao': descricao_completa, 'valor': valor,
                'cnpj': _extrai_cnpj(descricao_completa), 'banco': 'SICOOB',
            })
            i = j
    return transacoes, saldo_inicial


def parse_sisprime(caminho_docx):
    """SISPRIME — tabela única, limpa: Data/Documento/Histórico/Descrição/
    Débito/Crédito/Saldo, uma transação por linha, sem continuação. Débito e
    Crédito já vêm em colunas separadas (não precisa achar sinal no texto).
    Saldo vem em toda linha — dá pra validar transação por transação, não só
    o total do mês (mais forte que os outros bancos que só têm saldo final)."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    saldo_anterior = 0.0
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 7 or cells[0].upper() == 'DATA':
                continue
            data = _parse_data(cells[0])
            debito = _parse_valor(cells[4])
            credito = _parse_valor(cells[5])
            saldo_linha = _parse_valor(cells[6])
            valor = (credito or 0.0) - (debito or 0.0)
            descricao = ' '.join(x for x in (cells[2], cells[3]) if x).strip()
            transacoes.append({
                'data': data, 'descricao': descricao, 'valor': valor,
                'cnpj': _extrai_cnpj(descricao), 'banco': 'SISPRIME',
                '_saldo_esperado': round(saldo_anterior + valor, 2),
                '_saldo_declarado': saldo_linha,
            })
            if saldo_linha is not None:
                saldo_anterior = saldo_linha
    return transacoes, 0.0


def parse_credisis(caminho_docx):
    """CREDISIS — tabela única, mas em ORDEM REVERSA (mês mais recente
    primeiro) — achado real, diferente de todos os outros bancos vistos até
    agora. Termina com uma linha "Saldo anterior" (o saldo ANTES da primeira
    transação, que aqui é a ÚLTIMA da lista por causa da ordem invertida),
    seguida de um bloco de resumo de conta (cheque especial etc.) que não é
    transação. Tem Saldo por linha — mesma validação granular do SISPRIME,
    só que precisa inverter a lista no final pra ficar cronológica."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes_rev = []
    saldo_inicial = None
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 6:
                continue
            data_raw, desc = cells[0], cells[2]
            if data_raw.upper() == 'DATA' or data_raw.startswith('Saldo em') or data_raw.startswith('Saldos em'):
                continue
            if desc.strip() in ('Saldo final',):
                continue
            if desc.strip() == 'Saldo anterior':
                saldo_inicial = _parse_valor(cells[-1])
                continue
            data = _parse_data(data_raw)
            if data is None:
                break  # bloco de resumo de conta no rodapé, encerra
            valor = _parse_valor(cells[4])
            saldo_linha = _parse_valor(cells[-1])
            transacoes_rev.append({
                'data': data, 'descricao': desc.replace('\n', ' ').strip(), 'valor': valor,
                'cnpj': _extrai_cnpj(desc), 'banco': 'CREDISIS',
                '_saldo_declarado': saldo_linha,
            })
    transacoes = list(reversed(transacoes_rev))
    saldo_acum = saldo_inicial or 0.0
    for t in transacoes:
        saldo_acum = round(saldo_acum + t['valor'], 2)
        t['_saldo_esperado'] = saldo_acum
    return transacoes, saldo_inicial


def parse_cresol(caminho_docx):
    """CRESOL — dados de verdade ficam em PARÁGRAFOS (a única tabela do
    arquivo só tem o resumo de saldo geral), em grupos de 4 linhas cada:
    "DATA\\tSaldo do Dia: + valor" / "DATA" (repetida) / "Descrição" /
    "+/- R$ valor". Ordem REVERSA (mais recente primeiro), igual o CREDISIS —
    termina com "Saldo Anterior:\\t+ valor" (o saldo ANTES da 1ª transação)."""
    import docx
    d = docx.Document(caminho_docx)
    paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    transacoes_rev = []
    saldo_inicial = None
    i = 0
    while i < len(paras):
        p = paras[i]
        if p.startswith('Saldo Anterior:'):
            saldo_inicial = _parse_valor(p.split('\t')[-1])
            i += 1
            continue
        if '\tSaldo do Dia:' in p and i + 3 < len(paras):
            data = _parse_data(p.split('\t')[0])
            descricao = paras[i + 2]
            valor = _parse_valor(paras[i + 3])
            transacoes_rev.append({
                'data': data, 'descricao': descricao, 'valor': valor,
                'cnpj': _extrai_cnpj(descricao), 'banco': 'CRESOL',
            })
            i += 4
            continue
        i += 1
    transacoes = list(reversed(transacoes_rev))
    return transacoes, saldo_inicial


_PALAVRAS_DEBITO = ('DEB', 'TARIFA', 'PGTO', 'PAGAMENTO', 'ENVIADO', 'SAIDA', 'SAÍDA')
_PALAVRAS_CREDITO = ('RECEB', 'CRED', 'ENTRADA', 'DEPOSITO', 'DEPÓSITO')


def parse_amazonia(caminho_docx):
    """AMAZONIA — achado real importante: o valor NÃO vem com sinal nem D/C,
    diferente de todos os outros bancos vistos — precisa DEDUZIR débito ou
    crédito pela palavra-chave da descrição. Isso é mais fraco que um sinal
    explícito, então aqui a checagem contra o "Saldo do dia" (que o extrato
    intercala periodicamente) é ESSENCIAL, não só reforço — se não bater,
    quase certo que uma dedução de sinal errou, e cai pra IA.
    Valores também vêm com vírgula duplicada (R$ 45,,00), já tratado em
    `_parse_valor`."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    saldo_inicial = None
    saldo_checkpoints = []  # (indice_da_transacao_apos_a_qual, valor_declarado)

    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) == 1 and cells[0].startswith('Saldo Anterior:'):
                saldo_inicial = _parse_valor(cells[0].split('\t')[-1])
                continue
            if len(cells) < 6:
                continue
            data_raw, desc = cells[0], cells[2]
            if not data_raw and 'Saldo do dia' in cells[3]:
                saldo_checkpoints.append((len(transacoes), _parse_valor(cells[5])))
                continue
            data = _parse_data(data_raw)
            if not data:
                continue
            valor_abs = _parse_valor(cells[4])
            desc_upper = desc.upper()
            if any(p in desc_upper for p in _PALAVRAS_DEBITO):
                sinal = -1
            elif any(p in desc_upper for p in _PALAVRAS_CREDITO):
                sinal = 1
            else:
                sinal = None  # não deu pra decidir — fica marcado, conta como valor None pra forçar reforço da IA
            valor = (sinal * valor_abs) if (sinal is not None and valor_abs is not None) else None
            transacoes.append({
                'data': data, 'descricao': desc, 'valor': valor,
                'cnpj': _extrai_cnpj(desc), 'banco': 'AMAZONIA',
            })

    # confirma os checkpoints de "Saldo do dia" — validação essencial aqui
    # (mais importante que nos outros bancos, já que o sinal foi ADIVINHADO)
    saldo_acum = saldo_inicial or 0.0
    idx_checkpoint = 0
    checkpoints_batem = True
    for i, t in enumerate(transacoes):
        if t['valor'] is not None:
            saldo_acum = round(saldo_acum + t['valor'], 2)
        while idx_checkpoint < len(saldo_checkpoints) and saldo_checkpoints[idx_checkpoint][0] == i + 1:
            _, declarado = saldo_checkpoints[idx_checkpoint]
            if declarado is not None and abs(saldo_acum - declarado) > 0.02:
                checkpoints_batem = False
            idx_checkpoint += 1
    if not checkpoints_batem:
        for t in transacoes:
            t['valor'] = None  # força precisa_reforco_ia() a pegar o arquivo inteiro
    return transacoes, saldo_inicial


def parse_itau(caminho_docx):
    """ITAU — 6 colunas: Data/Histórico/Nome/CNPJ/Valor/SaldoTotalDia (a
    última só vem preenchida na linha de checkpoint "SALDO TOTAL DISPONÍVEL
    DIA"). CNPJ já vem numa coluna própria — ótimo pra achar fornecedor com
    certeza, sem depender de nome. Débito vem com sinal de menos explícito,
    crédito vem sem sinal (positivo) — confirmado comparando contra os
    checkpoints diários que o próprio extrato intercala."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    checkpoints = []
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 6:
                continue
            data, hist, nome, cnpj_txt, valor_txt, saldo_dia_txt = cells[:6]
            if not data or data.upper() == 'DATA':
                continue
            data_parsed = _parse_data(data)
            if not data_parsed:
                continue
            if 'SALDO TOTAL DISPONÍVEL' in hist.upper():
                checkpoints.append((len(transacoes), _parse_valor(saldo_dia_txt)))
                continue
            valor = _parse_valor(valor_txt)
            descricao = f'{hist} {nome}'.strip()
            transacoes.append({
                'data': data_parsed, 'descricao': descricao, 'valor': valor,
                'cnpj': _extrai_cnpj(cnpj_txt) or _extrai_cnpj(descricao), 'banco': 'ITAU',
            })
    return transacoes, checkpoints


def parse_cora(caminho_docx):
    """CORA — 4 colunas: Tipo/Nome(truncado com "…" no Word, não confiar
    nele sozinho)/CNPJ-ou-CPF/Valor com sinal explícito. Linha "Saldo do dia"
    intercalada (cols 1-2 vazias) só separa, não é transação. Não declara
    saldo inicial/final, mas declara o TOTAL de entradas e saídas do período
    logo no topo — uso isso pra validar (soma dos créditos == total de
    entradas declarado, mesma coisa pros débitos)."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    total_entradas_decl = total_saidas_decl = None
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 4:
                continue
            if 'Total de entradas' in cells[0]:
                partes = cells[-1].split('\n')
                partes = [p.strip() for p in partes if p.strip()]
                if len(partes) >= 2:
                    total_entradas_decl = _parse_valor(partes[0])
                    total_saidas_decl = _parse_valor(partes[1])
                continue
            tipo, nome, doc_txt, valor_txt = cells[0], cells[1], cells[2], cells[3]
            if not tipo or 'Saldo do dia' in doc_txt:
                continue
            valor = _parse_valor(valor_txt)
            cnpj = _extrai_cnpj(doc_txt)
            descricao = f'{tipo} {nome}'.strip()
            transacoes.append({
                'data': None, 'descricao': descricao, 'valor': valor,
                'cnpj': cnpj, 'banco': 'CORA',
            })
    if total_entradas_decl is not None:
        soma_creditos = round(sum(t['valor'] for t in transacoes if t['valor'] and t['valor'] > 0), 2)
        soma_debitos = round(sum(t['valor'] for t in transacoes if t['valor'] and t['valor'] < 0), 2)
        bate = (abs(soma_creditos - total_entradas_decl) < 0.02
                and abs(soma_debitos - total_saidas_decl) < 0.02)
        if not bate:
            for t in transacoes:
                t['valor'] = None
    return transacoes, (total_entradas_decl, total_saidas_decl)


# ---------------------------------------------------------------------------
# Conciliação: casa cada transação do extrato com um fornecedor do plano de
# contas. Primeiro tenta por CNPJ (mais confiável); se não achar, cai pra
# comparação por NOME (a maioria dos bancos não traz CNPJ de forma confiável
# — pedido explícito do Rafael: "o sistema tem que comparar também com o
# nome, caso não tiver CNPJ na descrição").
# ---------------------------------------------------------------------------
import unicodedata

_PALAVRAS_IGNORAR_NOME = {
    'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'S/A', 'CIA', 'COMERCIO', 'COMERCIAL',
    'IND', 'INDUSTRIA', 'INDUSTRIAL', 'DE', 'DO', 'DA', 'DOS', 'DAS', 'E',
}


def _normaliza_nome(nome):
    """Maiúsculo, sem acento, sem pontuação, sem as palavras genéricas de
    razão social (LTDA/ME/EIRELI/etc.) que não ajudam a diferenciar uma
    empresa da outra — devolve o CONJUNTO de palavras significativas."""
    if not nome:
        return set()
    nome = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode('ascii')
    nome = re.sub(r'[^A-Za-z0-9\s]', ' ', nome).upper()
    palavras = [p for p in nome.split() if p not in _PALAVRAS_IGNORAR_NOME and len(p) > 1]
    return set(palavras)


def _palavras_em_comum(pa, pb):
    """Conta como "em comum" tanto palavra IDÊNTICA quanto uma sendo PREFIXO
    da outra (mínimo 4 letras) — extrato de banco abrevia muito ("COMBUST"
    em vez de "COMBUSTÍVEIS", "AUTOM" em vez de "AUTOMOTIVOS"), achado real
    testando com nomes parecidos com os que já vi nesse projeto."""
    comuns = pa & pb
    restantes_a = pa - comuns
    restantes_b = pb - comuns
    for wa in list(restantes_a):
        if len(wa) < 4:
            continue
        for wb in restantes_b:
            if len(wb) >= 4 and (wa.startswith(wb) or wb.startswith(wa)):
                comuns.add(wa)
                break
    return comuns


def _similaridade_nome(nome_extrato, nome_fornecedor):
    """Pontuação combinando (1) quantas palavras significativas em comum
    (identicas ou uma prefixo da outra, pra pegar abreviação — proporção
    sobre o menor dos dois conjuntos, assim um nome curto do plano de contas
    contido numa descrição longa do extrato ainda pontua bem) e (2)
    similaridade de caractere pra reforçar (ex.: "L L PROD AUTOMOTIVOS" vs
    "L.L. Produtos Automotivos")."""
    import difflib
    pa = _normaliza_nome(nome_extrato)
    pb = _normaliza_nome(nome_fornecedor)
    if not pa or not pb:
        return 0.0
    comuns = _palavras_em_comum(pa, pb)
    score_palavras = len(comuns) / min(len(pa), len(pb))
    score_char = difflib.SequenceMatcher(None, ' '.join(sorted(pa)), ' '.join(sorted(pb))).ratio()
    return 0.7 * score_palavras + 0.3 * score_char


_FAV_RE = re.compile(r'FAV\.?:?\s*(.+?)(?:\s+(?:Transfer[eê]ncia|Recebimento|Pagamento|DOC\.?:|REM\.?:|DES\.?:)|$)', re.IGNORECASE)


def _trecho_favorecido(descricao):
    """Achado real: uma linha do extrato pode citar mais de uma empresa (o
    FAVORECIDO de verdade, marcado "FAV.:", e outra empresa incidental, tipo
    quem originou a transferência) — as duas podem pontuar quase igual na
    comparação normal. Quando existe um "FAV.:" explícito, o nome logo
    depois dele é o payee de verdade — prioriza esse trecho."""
    m = _FAV_RE.search(descricao)
    return m.group(1).strip() if m else None


def _similaridade_nome_pre(pa, nome_fornecedor_normalizado):
    """Mesma pontuação de `_similaridade_nome`, mas recebendo o conjunto de
    palavras do EXTRATO já normalizado (pa) e o do FORNECEDOR pré-computado
    — achado real de performance: recalcular a normalização do fornecedor
    a cada transação, com 1.000+ fornecedores × 1.000+ transações, passava
    de 5 minutos. Pré-computando o lado do fornecedor uma vez só (ver
    `prepara_fornecedores`), cai pra poucos segundos."""
    import difflib
    pb = nome_fornecedor_normalizado
    if not pa or not pb:
        return 0.0
    comuns = _palavras_em_comum(pa, pb)
    score_palavras = len(comuns) / min(len(pa), len(pb))
    score_char = difflib.SequenceMatcher(None, ' '.join(sorted(pa)), ' '.join(sorted(pb))).ratio()
    return 0.7 * score_palavras + 0.3 * score_char


def _chaves_indice(palavras):
    """Chave de índice pra cada palavra: os 4 primeiros caracteres (pra
    palavra >= 4 letras) ou a palavra inteira (< 4 letras) — assim
    "COMBUSTIVEIS" e "COMBUST" caem na MESMA chave ("COMB"), preservando o
    casamento por abreviação (`_palavras_em_comum`) mesmo usando índice."""
    return {p[:4] if len(p) >= 4 else p for p in palavras}


def prepara_fornecedores(fornecedores):
    """Pré-computa a normalização do nome de cada fornecedor UMA VEZ, e monta
    um ÍNDICE CHAVE→FORNECEDORES — achado real de performance: comparar
    CADA transação contra TODOS os 1.000+ fornecedores (~1,1 milhão de
    comparações numa conciliação real) levava 84s, lento demais. Com o
    índice, cada transação só compara contra os fornecedores que já
    compartilham ALGUMA chave com ela — cai bem mais."""
    preparados = []
    indice = {}
    for i, f in enumerate(fornecedores):
        f2 = dict(f)
        palavras = _normaliza_nome(f.get('nome', ''))
        f2['_palavras'] = palavras
        preparados.append(f2)
        for chave in _chaves_indice(palavras):
            indice.setdefault(chave, set()).add(i)
    return {'lista': preparados, 'indice': indice}


def encontra_fornecedor(transacao, fornecedores_preparados, limiar=0.55):
    """`fornecedores_preparados`: resultado de `prepara_fornecedores()`
    (essencial pra performance com bases grandes — usa índice pra não
    comparar contra TODOS os fornecedores a cada transação). Devolve
    (fornecedor_ou_None, confianca, metodo)."""
    lista = fornecedores_preparados['lista']
    indice = fornecedores_preparados['indice']
    cnpj_transacao = transacao.get('cnpj')
    if cnpj_transacao:
        for f in lista:
            if f.get('cnpj') and f['cnpj'] == cnpj_transacao:
                return _sem_campo_interno(f), 1.0, 'cnpj'

    def _melhor_match(texto):
        palavras_texto = _normaliza_nome(texto)
        if not palavras_texto:
            return None, 0.0
        candidatos = set()
        for chave in _chaves_indice(palavras_texto):
            candidatos |= indice.get(chave, set())
        melhor, melhor_score = None, 0.0
        for i in candidatos:
            f = lista[i]
            score = _similaridade_nome_pre(palavras_texto, f['_palavras'])
            if score > melhor_score:
                melhor, melhor_score = f, score
        return melhor, melhor_score

    trecho_fav = _trecho_favorecido(transacao.get('descricao', ''))
    if trecho_fav:
        melhor, melhor_score = _melhor_match(trecho_fav)
        if melhor and melhor_score >= limiar:
            return _sem_campo_interno(melhor), melhor_score, 'nome'
    melhor, melhor_score = _melhor_match(transacao.get('descricao', ''))
    if melhor and melhor_score >= limiar:
        return _sem_campo_interno(melhor), melhor_score, 'nome'
    return None, melhor_score, None


def _sem_campo_interno(f):
    return {k: v for k, v in f.items() if k != '_palavras'}


def _agrupa_por_linha_vazia(texto):
    """CAIXA empacota VÁRIAS transações na mesma célula da tabela, separadas
    por uma linha em branco — agrupa as linhas não-vazias consecutivas."""
    grupos, atual = [], []
    for linha in texto.split('\n'):
        if linha.strip():
            atual.append(linha.strip())
        elif atual:
            grupos.append(' '.join(atual))
            atual = []
    if atual:
        grupos.append(' '.join(atual))
    return grupos


def parse_caixa(caminho_docx):
    """CAIXA — achado real, o mais bagunçado dos 16: várias transações
    compactadas na MESMA célula da tabela via quebra de linha, com linha
    vazia separando cada uma nas colunas Histórico/Valor/Saldo (mas NÃO na
    coluna Data, que não separa de forma confiável). Uso a contagem de
    grupos do Valor como "verdade" de quantas transações tem no bloco — se
    Histórico não bater com essa contagem, ou se não achar nenhuma data no
    bloco, marca como suspeito (valor=None) pra cair no reforço da IA em vez
    de arriscar reconstrução errada."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    for t in d.tables:
        for row in t.rows:
            cells = [c.text for c in row.cells]
            if len(cells) < 5 or cells[0].strip().upper().startswith('DATA'):
                continue
            datas_no_bloco = re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', cells[0])
            historicos = _agrupa_por_linha_vazia(cells[2])
            valores_txt = [v for v in cells[3].split('\n') if v.strip()]
            saldos_txt = [s for s in cells[4].split('\n') if s.strip()]
            n = len(valores_txt)
            suspeito = not (len(historicos) == n and len(saldos_txt) == n and datas_no_bloco)
            for i in range(n):
                hist = historicos[i] if i < len(historicos) else ''
                data = _parse_data(datas_no_bloco[min(i, len(datas_no_bloco) - 1)]) if datas_no_bloco else None
                valor = None if suspeito else _parse_valor(valores_txt[i])
                transacoes.append({
                    'data': data, 'descricao': hist, 'valor': valor,
                    'cnpj': _extrai_cnpj(hist), 'banco': 'CAIXA',
                })
    return transacoes, None


def parse_bradesco(caminho_docx):
    """BRADESCO — achado real e importante: nesse export específico pra
    Word, os VALORES das transações não existem em lugar nenhum do arquivo
    (nem tabela, nem parágrafo) — só o resumo geral da conta (saldo total)
    tem número. O texto das transações vem em parágrafos soltos e
    embaralhados (fragmentos de nomes de empresas diferentes intercalados,
    sem ordem confiável), mas SEM NENHUM VALOR pra associar. Isso não é algo
    que um parser (nem reforço de IA) consiga recuperar — o dado não está no
    arquivo. Devolve lista vazia de propósito, pra acionar o aviso de que
    esse banco precisa de um export diferente (o PDF original, ou OFX)."""
    return [], None


_VALOR_DC_RE = re.compile(r'([\d.]+,\d{2})\s*\n?\s*([DC])\b')


def parse_banco_do_brasil(caminho_docx):
    """BANCO_DO_BRASIL — achado real: as 17 "páginas" (tabelas) do arquivo
    têm CADA UMA um número diferente de colunas (2 a 8!) e alternam entre
    células separadas e tudo compactado com tab numa célula só — o mais
    inconsistente dos 16 bancos. Abordagem mais flexível aqui: por linha,
    busca data e valor+D/C em QUALQUER posição via regex, em vez de depender
    de coluna fixa (que muda de tabela pra tabela). Linha onde TODAS as
    células são idênticas = nome/CNPJ do favorecido (não é transação, é
    complemento da transação anterior)."""
    import docx
    d = docx.Document(caminho_docx)
    transacoes = []
    saldo_inicial = None
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            texto_linha = ' '.join(cells)
            if len(set(c for c in cells if c)) == 1 and len(cells) > 1:
                # linha "toda igual" = nome/CNPJ do favorecido, complementa a
                # transação anterior
                if transacoes and not transacoes[-1].get('cnpj'):
                    nome_compl = cells[0]
                    transacoes[-1]['descricao'] += ' ' + nome_compl
                    transacoes[-1]['cnpj'] = _extrai_cnpj(nome_compl)
                continue
            if 'Saldo Anterior' in texto_linha:
                m = _VALOR_DC_RE.search(texto_linha)
                if m:
                    v = _parse_valor(m.group(1))
                    saldo_inicial = -v if m.group(2) == 'D' else v
                continue
            data = _parse_data(texto_linha)
            valores_achados = _VALOR_DC_RE.findall(texto_linha)
            if not data or not valores_achados:
                continue
            # o PRIMEIRO valor+D/C da linha é o valor da transação; um
            # segundo (quando existe) costuma ser o saldo corrente, ignorado
            # aqui (não uso saldo corrente pra validar nesse banco, dado o
            # tanto de variação de layout — validação fica só por soma total
            # quando fizer sentido no fluxo de conciliação).
            valor_txt, dc = valores_achados[0]
            valor = _parse_valor(valor_txt)
            valor = -valor if dc == 'D' else valor
            # remove o trecho do valor/saldo do texto pra sobrar só a
            # descrição (tira números tipo "150.031" de documento também,
            # mas isso é aceitável, vira parte do texto que o casamento por
            # nome/CNPJ ainda consegue usar)
            descricao = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', texto_linha)
            descricao = _VALOR_DC_RE.sub('', descricao).strip()
            transacoes.append({
                'data': data, 'descricao': descricao, 'valor': valor,
                'cnpj': _extrai_cnpj(texto_linha), 'banco': 'BANCO_DO_BRASIL',
            })
    return transacoes, saldo_inicial


def _prefixos_filhos_possiveis(classificacao):
    """Achado real: filho NÃO fica sempre logo depois do pai na ordem das
    linhas do documento (às vezes aparece bem mais adiante) — então não dá
    pra andar pela ordem. Mas o CÓDIGO de classificação segue um padrão
    confiável: o último segmento do pai ganha zeros à esquerda pros filhos
    (ex.: pai "2.1.30.1" grau 4 → filhos "2.1.30.100.N" grau 5) — só que a
    largura do preenchimento varia por nível (2, 3 ou 4 dígitos, confirmado
    testando vários pares reais). Tenta as larguras mais comuns."""
    partes = classificacao.split('.')
    prefixos = []
    for largura in (2, 3, 4):
        novo = partes[:-1] + [partes[-1].ljust(largura, '0')]
        prefixos.append('.'.join(novo) + '.')
    return prefixos


def parse_plano_contas_fornecedores(caminho_docx):
    """Lê o plano de contas (Word, tabela de 5 colunas: Código/T/Classificação/
    Nome/Grau). Devolve só as contas ANALÍTICAS dentro de alguma seção
    sintética "FORNECEDORES" do Passivo — pode ter MAIS DE UMA seção assim.
    Acha os filhos pelo PADRÃO DO CÓDIGO (ver `_prefixos_filhos_possiveis`),
    não pela ordem das linhas — filhos podem aparecer bem longe do pai no
    documento. Achado real: a coluna T marca sintética com 'S', mas o
    analítica varia por arquivo — no plano de contas original vinha
    explícito 'A', em outro real (Rafael, 2º cliente) vinha só VAZIO. Trata
    "não é S" como analítica em vez de exigir 'A' — cobre os dois casos."""
    import docx
    d = docx.Document(caminho_docx)
    linhas = []
    for t in d.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) >= 5 and cells[0] and cells[0] != 'Código':
                linhas.append({'codigo': cells[0], 'tipo': cells[1], 'classificacao': cells[2],
                                'nome': cells[3], 'grau': int(cells[4]) if cells[4].isdigit() else None})

    cabecalhos_fornecedores = [
        l for l in linhas
        if l['tipo'] == 'S' and l['classificacao'].startswith('2') and 'FORNECEDOR' in l['nome'].upper()
    ]
    # Achado real (2º cliente real, Contas1.docx): o cabeçalho sintético
    # "FORNECEDORES" (2.1.30.1) pode simplesmente NÃO EXISTIR como linha no
    # documento, mesmo com centenas de fornecedores reais logo abaixo dele
    # (classificação 2.1.30.100.X) — confirmado nos 2 arquivos reais que já
    # vi que "2.1.3" é o prefixo padrão de Fornecedores no Passivo. Usa como
    # fallback quando não achou nenhum cabeçalho nomeado — só se existir
    # alguma classificação real começando com "2.1.3" no documento (evita
    # forçar em plano de contas que realmente não usa essa convenção).
    if not any(c['classificacao'] in ('2.1.3', '2.1.30.1') for c in cabecalhos_fornecedores):
        if any(l['classificacao'].startswith('2.1.3') for l in linhas):
            cabecalhos_fornecedores.append({'classificacao': '2.1.3', 'tipo': 'S', 'nome': 'FORNECEDORES (fallback)', 'codigo': None, 'grau': 3})

    fornecedores = []
    vistos = set()
    for cab in cabecalhos_fornecedores:
        prefixos = _prefixos_filhos_possiveis(cab['classificacao'])
        for l in linhas:
            if l['tipo'] == 'S' or l['codigo'] in vistos:
                continue
            if any(l['classificacao'].startswith(p) for p in prefixos):
                vistos.add(l['codigo'])
                fornecedores.append({
                    'codigo': l['codigo'], 'nome': l['nome'],
                    'classificacao': l['classificacao'], 'cnpj': None,
                })
    return fornecedores


def gerar_txt_conciliado(linhas_originais, mapa_transacao_para_codigo):
    """Gera o TXT final pro Domínio, a partir do TXT original (lançamentos
    com placeholder) + o mapa {indice_da_linha_6100: codigo_fornecedor}
    montado pela conciliação. Só troca o CAMPO 3 (débito) de cada linha 6100
    conciliada — todo o resto da linha (data, valor, descrição original do
    banco) fica IDÊNTICO, confirmado com o Rafael. Cheque compensado
    (sem fornecedor identificável) fica como está, sempre."""
    saida = []
    idx_6100 = -1
    for linha in linhas_originais:
        if linha.startswith('|6100|'):
            idx_6100 += 1
            if idx_6100 in mapa_transacao_para_codigo:
                campos = linha.split('|')
                campos[3] = mapa_transacao_para_codigo[idx_6100]
                linha = '|'.join(campos)
        saida.append(linha)
    return '\n'.join(saida)


_PARSERS = {
    'SICOOB': lambda caminho, ano: parse_sicoob(caminho, ano),
    'SISPRIME': lambda caminho, ano: parse_sisprime(caminho),
    'CREDISIS': lambda caminho, ano: parse_credisis(caminho),
    'CRESOL': lambda caminho, ano: parse_cresol(caminho),
    'AMAZONIA': lambda caminho, ano: parse_amazonia(caminho),
    'ITAU': lambda caminho, ano: parse_itau(caminho),
    'CORA': lambda caminho, ano: parse_cora(caminho),
    'CAIXA': lambda caminho, ano: parse_caixa(caminho),
    'BRADESCO': lambda caminho, ano: parse_bradesco(caminho),
    'BANCO_DO_BRASIL': lambda caminho, ano: parse_banco_do_brasil(caminho),
}

if __name__ == "__main__":
    import sys
    import json as _json

    if "--plano-contas" in sys.argv:
        i = sys.argv.index("--plano-contas")
        caminho = sys.argv[i + 1]
        fornecedores = parse_plano_contas_fornecedores(caminho)
        out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
        resultado = {"total": len(fornecedores), "fornecedores": fornecedores}
        if out:
            with open(out, "w", encoding="utf-8") as f:
                _json.dump(resultado, f, ensure_ascii=False, indent=2)
            print("JSON gerado:", out)
        else:
            print(_json.dumps(resultado, ensure_ascii=False, indent=2))
        sys.exit(0)

    if "--gerar-txt" in sys.argv:
        i_orig = sys.argv.index("--original")
        i_mapa = sys.argv.index("--mapa")
        i_saida = sys.argv.index("--saida")
        with open(sys.argv[i_orig + 1], "r", encoding="latin-1") as f:
            linhas_originais = f.read().split("\n")
        with open(sys.argv[i_mapa + 1], "r", encoding="utf-8") as f:
            mapa_bruto = _json.load(f)
        mapa = {int(k): v for k, v in mapa_bruto.items()}
        resultado_txt = gerar_txt_conciliado(linhas_originais, mapa)
        with open(sys.argv[i_saida + 1], "w", encoding="latin-1") as f:
            f.write(resultado_txt)
        print("TXT gerado:", sys.argv[i_saida + 1])
        sys.exit(0)

    if "--conciliar" in sys.argv:
        banco = sys.argv[sys.argv.index("--banco") + 1].upper()
        caminho_extrato = sys.argv[sys.argv.index("--extrato") + 1]
        caminho_fornecedores = sys.argv[sys.argv.index("--fornecedores") + 1]
        ano = int(sys.argv[sys.argv.index("--ano") + 1]) if "--ano" in sys.argv else None
        with open(caminho_fornecedores, "r", encoding="utf-8") as f:
            fornecedores = prepara_fornecedores(_json.load(f))
        parser_fn = _PARSERS.get(banco)
        if not parser_fn:
            print(f"banco não suportado: {banco}")
            sys.exit(1)
        transacoes, _extra = parser_fn(caminho_extrato, ano)
        for t in transacoes:
            forn, score, metodo = encontra_fornecedor(t, fornecedores)
            t['fornecedor_sugerido'] = forn
            t['confianca'] = round(score, 2)
            t['metodo'] = metodo
        precisa_ia, motivo_ia = precisa_reforco_ia(transacoes)
        resultado = {
            "banco": banco, "total_transacoes": len(transacoes), "transacoes": transacoes,
            "precisa_reforco_ia": precisa_ia, "motivo_reforco_ia": motivo_ia,
        }
        out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
        if out:
            with open(out, "w", encoding="utf-8") as f:
                _json.dump(resultado, f, ensure_ascii=False, indent=2)
            print("JSON gerado:", out)
        else:
            print(_json.dumps(resultado, ensure_ascii=False, indent=2))
        sys.exit(0)

    if len(sys.argv) < 3 or sys.argv[1] != "--banco":
        print("uso: extrato_core.py --banco NOME arquivo.docx [--ano AAAA] [--json saida.json]")
        print("  ou: extrato_core.py --plano-contas arquivo.docx [--json saida.json]")
        print("  ou: extrato_core.py --gerar-txt --original ARQ.txt --mapa mapa.json --saida saida.txt")
        sys.exit(1)
    banco = sys.argv[2].upper()
    args = sys.argv[3:]
    if not args:
        print("faltou o caminho do arquivo .docx")
        sys.exit(1)
    caminho = args[0]
    ano = None
    if "--ano" in args:
        ano = int(args[args.index("--ano") + 1])
    parser_fn = _PARSERS.get(banco)
    if not parser_fn:
        print(f"banco não suportado ainda: {banco}. Bancos disponíveis: {', '.join(sorted(_PARSERS))}")
        sys.exit(1)
    transacoes, extra = parser_fn(caminho, ano)
    precisa_ia, motivo_ia = precisa_reforco_ia(transacoes)
    resultado = {
        "banco": banco,
        "total_transacoes": len(transacoes),
        "transacoes": transacoes,
        "precisa_reforco_ia": precisa_ia,
        "motivo_reforco_ia": motivo_ia,
    }
    if "--json" in args:
        out = args[args.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as f:
            _json.dump(resultado, f, ensure_ascii=False, indent=2)
        print("JSON gerado:", out)
    else:
        print(_json.dumps(resultado, ensure_ascii=False, indent=2))
