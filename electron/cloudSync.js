'use strict';
// Sincroniza o balancete importado para o Firestore (Firebase).
//
// IMPORTANTE — por que a sincronização usa o SDK CLIENTE (auth anônima),
// e não mais a credencial de administrador: se a credencial de admin fosse
// embutida em todo instalador (pra não exigir configuração manual em cada
// PC), qualquer cópia do sistema — mesmo não aprovada — teria acesso total
// ao banco, e conseguiria inclusive se autoaprovar no bloqueio remoto por
// máquina. O SDK cliente usa a MESMA config pública já embutida (a mesma do
// bloqueio remoto), e a segurança fica nas Regras do Firestore, não em
// esconder uma senha — por isso já vem pronto em todo instalador, sem
// nenhuma configuração do colaborador, e não pode ser trocado por engano.
//
// A credencial de administrador AINDA é usada, mas só pro painel "Licenças
// de acesso" (Ativar/Bloquear) — isso continua opcional, só em quem
// realmente precisa mudar status de licença por dentro do app.

const path = require('path');
const fs = require('fs');
function saFile(userDataDir) {
  return path.join(userDataDir, 'cloud-service-account.json');
}
function isConfigured() { return isCloudReady(); }
function setup() {
  throw new Error('Não é mais preciso configurar a nuvem: desde a versão 2.1 ela usa o login de cada usuário.');
}
function projectId() { return projectIdPublic(); }

// --------------------------------------------------------------------- conexão sem privilégio (sincronização de balancete)
let _webCfg = null;
function _loadWebConfig() {
  if (_webCfg !== null) return _webCfg;
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(__dirname, 'firebaseWebConfig.json'), 'utf-8'));
    _webCfg = raw && raw.apiKey ? raw : false;
  } catch (_) { _webCfg = false; }
  return _webCfg;
}

function isCloudReady() {
  return !!_loadWebConfig();
}

function projectIdPublic() {
  const c = _loadWebConfig();
  return c ? (c.projectId || '') : '';
}

let _clientDb = null;
let _clientFsMod = null;
// Desde a 2.1 os dados da nuvem só abrem para usuário logado e ativo (Regras do Firestore): usa a sessão do
// login individual (electron/auth.js), e não mais o login anônimo.
async function _initClient() {
  if (!_loadWebConfig()) return false;
  const auth = require('./auth');
  if (!auth.logado()) throw new Error('Entre com o seu usuário (e com internet) para usar a nuvem.');
  _clientDb = auth.db();
  _clientFsMod = auth.fsMod();
  return true;
}

// Chave da API da Claude (Opção 1 combinada com o Rafael) — nunca embutida no
// instalador, nem gravada em disco local. Fica só num documento do Firestore
// (`config/chat_ia`), lido uma vez por sessão via a MESMA autenticação anônima
// já usada pra licença/histórico — igual qualquer outra leitura do cliente,
// mas com a regra de segurança bloqueando ESCRITA por esse caminho (só o
// Admin consegue gravar/trocar essa chave, direto no Console do Firebase).
// Guardada em memória (nunca em arquivo) e SÓ usada aqui no processo principal
// — a renderer nunca recebe o valor da chave.
let _chaveIACache = null;
async function getChaveIA() {
  if (_chaveIACache) return _chaveIACache;
  const ok = await _initClient();
  if (!ok) throw new Error('Nuvem não configurada nesta máquina.');
  const { doc, getDoc } = _clientFsMod;
  const ref = doc(_clientDb, 'config', 'chat_ia');
  const snap = await _withTimeout(getDoc(ref), 10000, 'Busca da chave de IA');
  if (!snap.exists() || !snap.data().anthropic_key) {
    throw new Error('Chave de IA ainda não configurada na nuvem (peça pro Admin configurar no Firebase).');
  }
  _chaveIACache = snap.data().anthropic_key;
  return _chaveIACache;
}

function _slugCnpj(emp) {
  const c = (emp.cnpj || '').replace(/\D/g, '');
  if (c) return c;
  const nome = (emp.empresa || 'sem-nome').toUpperCase().replace(/[^A-Z0-9]+/g, '-').slice(0, 40);
  return 'sem-cnpj-' + nome;
}

function _withTimeout(p, ms, label) {
  return Promise.race([
    p,
    new Promise((_, rej) => setTimeout(() => rej(new Error(label + ' não respondeu em ' + ms + 'ms (rede/firewall?)')), ms)),
  ]);
}

async function syncBalancete(_userDataDirUnused, data, arquivo) {
  if (!(await _initClient())) throw new Error('Nuvem não configurada neste instalador (config pública ausente).');
  const { doc, setDoc, serverTimestamp } = _clientFsMod;
  const emp = data.empresa || {};
  const dre = data.dre || {};
  const res = data.resultado || {};
  const cnpj = _slugCnpj(emp);
  const comp = (emp.periodo || 'sem-periodo').replace(/[\/\\:]/g, '-').replace(/\s+/g, '');

  const resumo = {
    empresa: emp.empresa || arquivo || '(sem nome)',
    cnpj: emp.cnpj || '',
    periodo: emp.periodo || '',
    resultadoTipo: res.tipo || '',
    resultadoValor: res.valor || 0,
    receitaLiquida: dre.receita_liquida || 0,
    despesaTotal: dre.despesa_total || 0,
    margemLiquida: dre.margem_liquida || 0,
    invertidas: Array.isArray(data.invertidas) ? data.invertidas.length : 0,
    arquivo: arquivo || '',
    atualizadoEm: serverTimestamp(),
  };
  // O balancete completo vai como STRING (evita o limite de índices/1MiB do Firestore
  // ao indexar arrays grandes de contas). O app faz JSON.parse ao ler.
  const payloadJson = JSON.stringify(data);

  const empRef = doc(_clientDb, 'empresas', cnpj);
  await _withTimeout(setDoc(empRef, { ...resumo, payloadJson }, { merge: true }), 20000, 'Firestore (empresa)');
  await _withTimeout(setDoc(doc(_clientDb, 'empresas', cnpj, 'historico', comp), { ...resumo, payloadJson }), 20000, 'Firestore (histórico)');

  return { cnpj, empresa: resumo.empresa, periodo: resumo.periodo, bytes: payloadJson.length };
}

// --------------------------------------------------------------------- histórico de balancetes
// Cada import já grava em empresas/{cnpj}/historico/{competência} desde sempre — essas funções
// só LEEM o que já está lá, pra listar e reabrir um balancete antigo dentro do app.
function _tsToIso(ts) {
  try { return ts && ts.toDate ? ts.toDate().toISOString() : ''; } catch (_) { return ''; }
}

async function listEmpresas() {
  if (!(await _initClient())) return [];
  const { collection, getDocs } = _clientFsMod;
  const snap = await getDocs(collection(_clientDb, 'empresas'));
  const out = [];
  snap.forEach((d) => {
    const v = d.data() || {};
    out.push({ cnpj: d.id, empresa: v.empresa || '(sem nome)', periodo: v.periodo || '', atualizadoEm: _tsToIso(v.atualizadoEm) });
  });
  out.sort((a, b) => a.empresa.localeCompare(b.empresa, 'pt-BR'));
  return out;
}

async function listHistorico(cnpj) {
  if (!(await _initClient())) return [];
  const { collection, getDocs } = _clientFsMod;
  const snap = await getDocs(collection(_clientDb, 'empresas', cnpj, 'historico'));
  const out = [];
  snap.forEach((d) => {
    const v = d.data() || {};
    out.push({
      id: d.id,
      periodo: v.periodo || d.id,
      resultadoTipo: v.resultadoTipo || '',
      resultadoValor: v.resultadoValor || 0,
      margemLiquida: v.margemLiquida || 0,
      receitaLiquida: v.receitaLiquida || 0,
      arquivo: v.arquivo || '',
      atualizadoEm: _tsToIso(v.atualizadoEm),
    });
  });
  out.sort((a, b) => (b.atualizadoEm || '').localeCompare(a.atualizadoEm || '') || (b.periodo || '').localeCompare(a.periodo || ''));
  return out;
}

async function getHistoricoItem(cnpj, id) {
  if (!(await _initClient())) throw new Error('Nuvem não configurada neste instalador.');
  const { doc, getDoc } = _clientFsMod;
  const snap = await getDoc(doc(_clientDb, 'empresas', cnpj, 'historico', id));
  if (!snap.exists()) throw new Error('Registro não encontrado na nuvem.');
  const v = snap.data() || {};
  if (!v.payloadJson) throw new Error('Esse registro não tem o balancete completo salvo (versão antiga).');
  return JSON.parse(v.payloadJson);
}

async function deleteHistoricoItem(cnpj, id) {
  if (!(await _initClient())) throw new Error('Nuvem não configurada neste instalador.');
  const { doc, deleteDoc } = _clientFsMod;
  await deleteDoc(doc(_clientDb, 'empresas', cnpj, 'historico', id));
  return { ok: true };
}

module.exports = { removerCredencialAntiga, isConfigured, setup, syncBalancete, saFile, projectId, isCloudReady, projectIdPublic, listLicenses, setLicenseStatus, listEmpresas, listHistorico, getHistoricoItem, deleteHistoricoItem, getChaveIA };

// --------------------------------------------------------------------- painel de licenças (admin)
// Desde a 2.1 o painel usa o login do Admin (Regras do Firestore), sem a credencial de administrador (conta de
// serviço) — ela não fica mais em nenhuma máquina. Ver removerCredencialAntiga().
async function listLicenses() { return require('./auth').listarLicencas(); }
async function setLicenseStatus(_userDataDir, codigo, status) { return require('./auth').statusLicenca(codigo, status); }

// A credencial de administrador antiga dava poder total sobre o banco: apaga a cópia desta máquina.
function removerCredencialAntiga(userDataDir) {
  try { if (fs.existsSync(saFile(userDataDir))) { fs.unlinkSync(saFile(userDataDir)); return true; } } catch (_) {}
  return false;
}
