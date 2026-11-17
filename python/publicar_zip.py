# -*- coding: utf-8 -*-
"""Zips do mês na pasta do cliente (pedido do Rafael, 17/11/2026).

Para cada tipo de documento, um zip de XML e outro de PDF na pasta  <Empresa>\\Relatórios\\<AAAA>\\<mês>:
    "NFe Entradas 102026 - XML.zip", "NFe Entradas 102026 - PDF.zip", "NFC-e Saidas 102026 - XML.zip"…
Se o zip já existe, junta: o que já estava continua, o que é novo entra (mesmo nome com tamanho diferente é trocado;
nota que virou ".CANCELADA" tira a versão normal). Grava num arquivo temporário e troca no fim, para o zip nunca
ficar pela metade no drive.

    python fiscal_core.py publicar-zip --entrada lista.json --json r.json
    lista.json = [{"origem": "<pasta>", "zip": "<arquivo.zip>"}, {"copiar": "<arquivo>", "para": "<arquivo>"}]
"""
import json
import os
import shutil
import zipfile


def _arquivos(origem):
    out = {}
    for raiz, _dirs, nomes in os.walk(origem):
        for n in nomes:
            if n.startswith('~$') or n.lower().endswith(('.tmp', '.part')):
                continue
            c = os.path.join(raiz, n)
            out[os.path.relpath(c, origem).replace(os.sep, '/')] = c
    return out


def publicar(origem, destino_zip):
    novos = _arquivos(origem)
    if not novos:
        return {'zip': destino_zip, 'qtd': 0, 'novos': 0, 'pulado': True}
    antigos = {}
    if os.path.exists(destino_zip):
        try:
            with zipfile.ZipFile(destino_zip) as z:
                antigos = {i.filename: i.file_size for i in z.infolist() if not i.is_dir()}
        except zipfile.BadZipFile:
            antigos = {}
    # nota cancelada depois: sai a versão normal
    tirar = set()
    for rel in novos:
        if rel.endswith('.CANCELADA.xml'):
            tirar.add(rel[:-len('.CANCELADA.xml')] + '.xml')
    entra = {rel: c for rel, c in novos.items() if rel not in antigos or antigos[rel] != os.path.getsize(c)}
    if not entra and not (tirar & set(antigos)):
        return {'zip': destino_zip, 'qtd': len(antigos), 'novos': 0}
    os.makedirs(os.path.dirname(destino_zip), exist_ok=True)
    tmp = destino_zip + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zn:
        if antigos:
            with zipfile.ZipFile(destino_zip) as zv:
                for info in zv.infolist():
                    if info.is_dir() or info.filename in entra or info.filename in tirar:
                        continue
                    zn.writestr(info, zv.read(info.filename))
        for rel, c in sorted(entra.items()):
            zn.write(c, rel)
    os.replace(tmp, destino_zip)
    total = len((set(antigos) - tirar) | set(novos))
    return {'zip': destino_zip, 'qtd': total, 'novos': len([r for r in entra if r not in antigos])}


def hidratar(zip_path, destino):
    """Traz para a cópia de trabalho deste computador o que está no zip da pasta do cliente e ainda não está aqui
    (outro computador baixou): o painel e o relatório enxergam tudo o que já foi baixado."""
    if not os.path.exists(zip_path):
        return 0
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir() or '..' in info.filename.split('/') or info.filename.startswith('/'):
                continue
            alvo = os.path.join(destino, *info.filename.split('/'))
            if os.path.exists(alvo) and os.path.getsize(alvo) == info.file_size:
                continue
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with open(alvo, 'wb') as fh:
                fh.write(z.read(info.filename))
            n += 1
    return n


def processar(lista):
    feitos, erros = [], []
    for item in lista:
        try:
            if item.get('hidratar'):
                feitos.append({'hidratar': item['hidratar'], 'novos': hidratar(item['hidratar'], item['destino'])})
            elif item.get('copiar'):
                os.makedirs(os.path.dirname(item['para']), exist_ok=True)
                shutil.copyfile(item['copiar'], item['para'] + '.tmp')
                os.replace(item['para'] + '.tmp', item['para'])
                feitos.append({'arquivo': item['para']})
            else:
                feitos.append(publicar(item['origem'], item['zip']))
        except Exception as e:      # um zip com problema não para os outros
            erros.append(f"{os.path.basename(item.get('zip') or item.get('para') or '')}: {str(e)[:160]}")
    return {'ok': True, 'feitos': feitos, 'erros': erros}


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    try:
        with open(opt('--entrada'), encoding='utf-8') as fh:
            r = processar(json.load(fh))
    except Exception as e:
        r = {'erro': str(e)[:300]}
    with open(opt('--json'), 'w', encoding='utf-8') as fh:
        json.dump(r, fh, ensure_ascii=False)
    return 0
