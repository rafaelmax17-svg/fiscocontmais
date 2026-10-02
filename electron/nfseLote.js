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
// que a baixa já usa (pastaBase/razaoSocial), para ficar ao lado de XML e PDF.
function salvarPainelIndividual(pastaBase, empresa, painelHtml, ini, fim) {
  const sub = periodoSubpasta(ini, fim);
  const dir = path.join(pastaBase, empresa.razaoSocial, 'NFS-e', 'Relatórios', sub);
  fs.mkdirSync(dir, { recursive: true });
  const nome = `Painel-NFSe_${sanitizar(empresa.razaoSocial)}_${sub}.html`;
  const abs = path.join(dir, nome);
  fs.writeFileSync(abs, painelHtml, 'utf-8');
  return { rel: [empresa.razaoSocial, 'NFS-e', 'Relatórios', sub, nome].join('/'), abs, dir };
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
async function executarLote({ empresas, baixarEmpresa, analisarEmpresa, salvarPainel, onProgresso = () => {}, cancelado = () => false }) {
  const resultados = [];
  const total = empresas.length;
  for (let i = 0; i < total; i++) {
    const emp = empresas[i];
    const r = resultadoVazio(emp);
    if (cancelado()) {
      r.status = 'nao_iniciada';
      r.motivo = 'O lote foi cancelado antes de chegar nesta empresa.';
      resultados.push(r);
      continue;
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
          if ((s.total_notas || 0) + (s.qtd_canceladas || 0) === 0) {
            r.status = 'sem_notas';
          } else {
            r.status = 'concluida';
            try {
              r.relatorio_rel = salvarPainel(emp, a.painelHtml).rel;
            } catch (e) {
              r.aviso = `As notas foram baixadas, mas não consegui salvar o painel individual: ${String((e && e.message) || e)}`;
            }
          }
        }
      }
    } catch (e) {
      r.status = 'erro';
      r.motivo = String((e && e.message) || e);
    }
    r.duracao_s = Math.round((Date.now() - t0) / 1000);
    resultados.push(r);
    onProgresso({ fase: 'fim', i: i + 1, total, nome: emp.razaoSocial, status: r.status, salvos: r.salvos, motivo: r.motivo });
  }
  return resultados;
}

module.exports = { executarLote, periodoSubpasta, salvarPainelIndividual, sanitizar };
