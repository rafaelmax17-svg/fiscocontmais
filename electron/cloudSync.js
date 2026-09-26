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
let admin = null;
let db = null;

function saFile(userDataDir) {
  return path.join(userDataDir, 'cloud-service-account.json');
}

function isConfigured(userDataDir) {
  return fs.existsSync(saFile(userDataDir));
}

function _init(userDataDir) {
  if (db) return true;
  const p = saFile(userDataDir);
  if (!fs.existsSync(p)) return false;
  if (!admin) {
    try { admin = require('firebase-admin'); }
    catch (e) {
      throw new Error("Dependência 'firebase-admin' não instalada. Feche o app e rode o instalar.bat (ou run-dev.bat) de novo para instalá-la.");
    }
  }
  const sa = JSON.parse(fs.readFileSync(p, 'utf-8'));
  const appName = 'fiscocont-sync';
  const existing = admin.apps.find((a) => a && a.name === appName);
  const fbApp = existing || admin.initializeApp({ credential: admin.credential.cert(sa) }, appName);
  db = admin.firestore(fbApp);
  return true;
}

// Copia o arquivo de credencial para a pasta do app (valida antes). Só
// necessário pra habilitar o painel Admin de licenças nesta máquina — a
// sincronização normal de balancete não depende mais disso.
function setup(userDataDir, pickedPath) {
  const sa = JSON.parse(fs.readFileSync(pickedPath, 'utf-8'));
  if (!sa.project_id || !sa.private_key || !sa.client_email) {
    throw new Error('Este arquivo não parece uma credencial de conta de serviço do Firebase (faltam project_id/private_key/client_email).');
  }
  fs.copyFileSync(pickedPath, saFile(userDataDir));
  db = null; // força reinicialização com a nova credencial
  return { projectId: sa.project_id };
}

function projectId(userDataDir) {
  try { return JSON.parse(fs.readFileSync(saFile(userDataDir), 'utf-8')).project_id || ''; }
  catch (_) { return ''; }
}

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
async function _initClient() {
  if (_clientDb) return true;
  const c = _loadWebConfig();
  if (!c) return false;
  const { initializeApp, getApps } = require('firebase/app');
  const { getAuth, signInAnonymously } = require('firebase/auth');
  const { getFirestore } = require('firebase/firestore');
  const appName = 'fiscocont-sync-client';
  let app = getApps().find((a) => a.name === appName);
  if (!app) app = initializeApp(c, appName);
  await signInAnonymously(getAuth(app));
  _clientFsMod = require('firebase/firestore');
  _clientDb = getFirestore(app);
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

module.exports = { isConfigured, setup, syncBalancete, saFile, projectId, isCloudReady, projectIdPublic, listLicenses, setLicenseStatus, listEmpresas, listHistorico, getHistoricoItem, deleteHistoricoItem, getChaveIA };

// --------------------------------------------------------------------- painel de licenças (admin)
// Usa a MESMA credencial privilegiada da nuvem (Admin SDK) — por isso só
// funciona nas máquinas onde a nuvem já foi configurada (☁). É a única forma
// autorizada de mudar o status de uma licença; o app "comum" (electron/license.js)
// só consegue LER e criar a si mesmo como "pendente".
async function listLicenses(userDataDir) {
  if (!_init(userDataDir)) throw new Error('Nuvem não configurada nesta máquina.');
  // Busca TUDO sem orderBy do Firestore de propósito — orderBy em campo tipo
  // timestamp pode excluir silenciosamente (ou até dar erro de índice) doc
  // que tenha esse campo ausente/de tipo diferente. Ordena em memória depois,
  // que não tem esse risco.
  const snap = await db.collection('licencas').get();
  const conv = (v) => (v && typeof v.toDate === 'function') ? v.toDate().toISOString() : null;
  const itens = snap.docs.map((d) => {
    const data = d.data();
    return {
      codigo: d.id,
      status: data.status || 'pendente',
      hostname: data.hostname || '',
      plataforma: data.plataforma || '',
      primeiroAcesso: conv(data.primeiroAcesso),
      ultimoAcesso: conv(data.ultimoAcesso),
    };
  });
  itens.sort((a, b) => new Date(b.ultimoAcesso || 0) - new Date(a.ultimoAcesso || 0));
  return itens;
}

async function setLicenseStatus(userDataDir, codigo, status) {
  if (!_init(userDataDir)) throw new Error('Nuvem não configurada nesta máquina.');
  if (!['ativo', 'bloqueado', 'pendente'].includes(status)) throw new Error('Status inválido.');
  await db.collection('licencas').doc(codigo).set({
    status,
    atualizadoPor: 'painel-admin',
    atualizadoEm: admin.firestore.FieldValue.serverTimestamp(),
  }, { merge: true });
  return { ok: true };
}
