'use strict';
// Baixa de NFS-e em lote (todas as empresas cadastradas).
//
// A lógica do lote fica aqui, separada do main.js, com a baixa e a análise INJETADAS —
// assim dá pra testar o fluxo inteiro (ordem, cancelamento, empresas puladas, nomes de
// pasta) sem precisar de certificado digital nem de acesso à Receita.
const fs = require('fs');
const path = require('path');

function ultimoDiaDoMes(ano, mes) {
  return new Date(Number(ano), Number(mes), 0).getDate();
}

// Subpasta do período dentro de <Empresa>/NFS-e/Relatórios:
//  - mês fechado (1º ao último dia)  -> "2026-08"
//  - qualquer outro intervalo        -> "2026-08-01_a_2026-09-15"
// (mês fechado e intervalo parcial não podem cair na mesma pasta: um sobrescreveria o outro)
function periodoSubpasta(ini, fim) {
  const mi = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ini || '');
  const mf = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fim || '');
  if (mi && mf && mi[1] === mf[1] && mi[2] === mf[2] && mi[3] === '01' && Number(mf[3]) === ultimoDiaDoMes(mf[1], mf[2])) {
    return `${mi[1]}-${mi[2]}`;
  }
  return `${ini}_a_${fim}`;
}

function sanitizar(nome) {
  return String(nome || '').replace(/[<>:"/\\|?*\u0000-\u001f]+/g, '_').trim() || 'empresa';
}

// Salva o painel individual na pasta do cliente. A pasta da empresa segue a MESMA regra
// que a baixa já usa (pastaBase/AAAA-MM/razaoSocial), para ficar ao lado de XML e PDF.
function salvarPainelIndividual(pastaBase, empresa, painelHtml, ini, fim) {
  const sub = periodoSubpasta(ini, fim);
  const d = String(ini || '');
  const mes = d.length >= 7 ? `${d.slice(5, 7)}-${d.slice(0, 4)}` : 'sem-data';   // pasta do mês MM-AAAA (data inicial do lote)
  const dir = path.join(pastaBase, mes, empresa.razaoSocial, 'NFS-e', 'Relatórios', sub);
  fs.mkdirSync(dir, { recursive: true });
  const nome = `Painel-NFSe_${sanitizar(empresa.razaoSocial)}_${sub}.html`;
  const abs = path.join(dir, nome);
  fs.writeFileSync(abs, painelHtml, 'utf-8');
  return { rel: [mes, empresa.razaoSocial, 'NFS-e', 'Relatórios', sub, nome].join('/'), abs, dir };
}

function resultadoVazio(emp) {
  return {
    id: emp.id, nome: emp.razaoSocial, cnpj: emp.cnpj, status: '', motivo: '', aviso: '', salvos: 0, canceladas: 0, prestadas: 0, tomadas: 0,
    valor_prestado: 0, valor_tomado: 0, pdfs_gerados: 0, pdfs_erro: 0, qtd_com_ret: 0, qtd_sem_ret: 0, inconsistencias: 0,
    relatorio_rel: '', duracao_s: 0,
  };
}

// baixarEmpresa(emp)  -> { error, tipo: 'pulada'|'erro' } | { ok, resultado: { salvos, pdfs_gerados, pdfs_erro } }
// analisarEmpresa(emp)-> { error } | { ok, resumo, painelHtml }
// salvarPainel(emp, html) -> { rel }
// Pausa entre uma empresa e outra: consultas seguidas ao ADN, sem intervalo, foram respondidas com 400 "REJEICAO"
// sem motivo (achado real, Rafael, 01/11, no lote). Quem cair nessa recusa ganha uma segunda tentativa no fim do lote.
const PAUSA_ENTRE_EMPRESAS_MS = 4000;
const PAUSA_ANTES_DE_REPETIR_MS = 20000;
const _espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
const _ehRejeicaoSemMotivo = (r) => r.status === 'erro' && /REJEICAO/.test(r.motivo || '') && !r.salvos;

async function executarLote(opcoes) {
  const { empresas, onProgresso = () => {}, cancelado = () => false } = opcoes;
  const resultados = [];
  for (let i = 0; i < empresas.length; i++) {
    if (i > 0 && !cancelado()) await _espera(PAUSA_ENTRE_EMPRESAS_MS);
    resultados.push(await _umaEmpresa(opcoes, empresas[i], i, empresas.length));
  }
  const repetir = resultados.map((r, k) => (_ehRejeicaoSemMotivo(r) ? k : -1)).filter((k) => k >= 0);
  if (repetir.length && !cancelado()) {
    await _espera(PAUSA_ANTES_DE_REPETIR_MS);
    for (let j = 0; j < repetir.length && !cancelado(); j++) {
      const k = repetir[j];
      if (j > 0) await _espera(PAUSA_ENTRE_EMPRESAS_MS);
      onProgresso({ fase: 'repetindo', i: j + 1, total: repetir.length, nome: empresas[k].razaoSocial });
      const novo = await _umaEmpresa(opcoes, empresas[k], k, empresas.length);
      if (!_ehRejeicaoSemMotivo(novo)) novo.aviso = [novo.aviso, 'Baixada na segunda tentativa: a Receita recusou a primeira consulta sem informar o motivo.'].filter(Boolean).join(' ');
      resultados[k] = novo;
    }
  }
  return resultados;
}

async function _umaEmpresa({ baixarEmpresa, analisarEmpresa, salvarPainel, onProgresso = () => {}, cancelado = () => false }, emp, i, total) {
    const r = resultadoVazio(emp);
    if (cancelado()) {
      r.status = 'nao_iniciada';
      r.motivo = 'O lote foi cancelado antes de chegar nesta empresa.';
      return r;
    }
    onProgresso({ fase: 'inicio', i: i + 1, total, nome: emp.razaoSocial });
    const t0 = Date.now();
    try {
      const b = await baixarEmpresa(emp);
      if (b.error) {
        r.status = b.tipo === 'pulada' ? 'pulada' : 'erro';
        r.motivo = b.error;
      } else {
        const dl = b.resultado || {};
        r.salvos = dl.salvos || 0;
        r.pdfs_gerados = dl.pdfs_gerados || 0;
        r.pdfs_erro = dl.pdfs_erro || 0;
        r.pdfs_erros = dl.pdfs_erros || [];
        if (dl.aviso) r.aviso = dl.aviso;
        const a = await analisarEmpresa(emp);
        if (a.error) {
          r.status = 'erro';
          r.motivo = `As notas foram baixadas (${r.salvos}), mas a análise do período falhou: ${a.error}`;
        } else {
          const s = a.resumo || {};
          r.prestadas = s.emitidas || 0;
          r.tomadas = s.recebidas || 0;
          r.canceladas = s.qtd_canceladas || 0;
          r.valor_prestado = s.valor_emitidas || 0;
          r.valor_tomado = s.valor_recebidas || 0;
          r.qtd_com_ret = s.qtd_com_retencao || 0;
          r.qtd_sem_ret = s.qtd_sem_retencao || 0;
          r.inconsistencias = (s.inconsistencias_piscofins || []).length;
          r.pf_com_ret = s.qtd_pf_com_retencao || 0;
          if ((s.total_notas || 0) + (s.qtd_canceladas || 0) === 0) {
            r.status = 'sem_notas';
          } else {
            r.status = 'concluida';
            try {
              r.relatorio_rel = salvarPainel(emp, a.painelHtml).rel;
            } catch (e) {
              r.aviso = [r.aviso, `As notas foram baixadas, mas não consegui salvar o painel individual: ${String((e && e.message) || e)}`].filter(Boolean).join(' ');
            }
          }
        }
      }
    } catch (e) {
      r.status = 'erro';
      r.motivo = String((e && e.message) || e);
    }
    r.duracao_s = Math.round((Date.now() - t0) / 1000);
    onProgresso({ fase: 'fim', i: i + 1, total, nome: emp.razaoSocial, status: r.status, salvos: r.salvos, motivo: r.motivo });
    return r;
}

module.exports = { executarLote, periodoSubpasta, salvarPainelIndividual, sanitizar };
