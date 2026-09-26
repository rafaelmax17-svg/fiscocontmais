'use strict';
// Tela de "Novidades desta versão".
//
// Não duplica conteúdo: busca o corpo (texto) da release correspondente
// direto no GitHub — o mesmo texto que já escrevo na hora de criar cada
// release (repo público, leitura não precisa de token). Compara a versão
// atual do app com a última que o usuário já viu (guardada num arquivo
// simples em userData) e só mostra quando muda.

const fs = require('fs');
const path = require('path');

const OWNER = 'rafaelmax17-svg';
const REPO = 'fiscocontmais';

function _arquivoVisto(userDataDir) {
  return path.join(userDataDir, 'changelog-visto.json');
}

function _lerVisto(userDataDir) {
  try { return JSON.parse(fs.readFileSync(_arquivoVisto(userDataDir), 'utf-8')).versao ?? null; }
  catch (_) { return null; }
}

function marcarComoVisto(userDataDir, versao) {
  try { fs.writeFileSync(_arquivoVisto(userDataDir), JSON.stringify({ versao })); } catch (_) {}
}

async function _buscarNotas(versao) {
  const url = `https://api.github.com/repos/${OWNER}/${REPO}/releases/tags/v${versao}`;
  const res = await fetch(url, { headers: { Accept: 'application/vnd.github+json' } });
  if (!res.ok) return null;
  const data = await res.json();
  return (data && typeof data.body === 'string' && data.body.trim()) ? data.body.trim() : null;
}

// Devolve { versao, notas } se tiver novidade pra mostrar, ou null.
// IMPORTANTE: só marca como "visto" depois que o chamador confirmar que
// mostrou (marcarComoVisto, chamado à parte) — assim, se o GitHub estiver
// fora do ar agora, tenta de novo na próxima abertura em vez de perder essa
// versão pra sempre. Exceção: primeira vez que esse arquivo é criado (app
// nunca rodou esse recurso antes) — aí só grava a versão atual como marco
// inicial, sem mostrar nada (evita mostrar "novidade" de uma versão que já
// é a que a pessoa tem instalada há tempos).
async function checarNovidades(versaoAtual, userDataDir) {
  const vista = _lerVisto(userDataDir);
  if (vista === null) {
    marcarComoVisto(userDataDir, versaoAtual);
    return null;
  }
  if (vista === versaoAtual) return null;
  try {
    const notas = await _buscarNotas(versaoAtual);
    if (!notas) { marcarComoVisto(userDataDir, versaoAtual); return null; }
    return { versao: versaoAtual, notas };
  } catch (_) {
    return null;
  }
}

module.exports = { checarNovidades, marcarComoVisto };
