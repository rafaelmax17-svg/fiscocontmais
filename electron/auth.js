'use strict';
// Login individual (Firebase Authentication · e-mail e senha) e cadastro de usuários pelo Admin.
//
// Cada pessoa tem o próprio login; o perfil (fiscal / contabil / admin) e a situação (ativo / bloqueado) ficam no
// Firestore em usuarios/{uid}. As Regras de Segurança (arquivo firestore.rules na raiz do projeto) garantem que:
//   • só um Admin ativo cadastra, bloqueia ou muda o perfil de alguém;
//   • a pessoa só lê o próprio cadastro;
//   • o primeiro Admin (ADMIN_INICIAL) se cadastra sozinho uma única vez, e só com o e-mail confirmado.
// Nenhuma senha fica no código. Para funcionar sem internet, depois de cada login online fica guardada na máquina
// uma verificação da senha (scrypt, criptografada com o cofre do Windows via safeStorage), válida por 7 dias.
//
// Sem o plano Blaze não há Cloud Functions: o cadastro de um usuário novo cria a conta numa instância separada do
// Firebase (o Admin continua logado) e manda para a pessoa o e-mail de "definir senha".

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const ADMIN_INICIAL = 'rafael.max17@gmail.com';
const PERFIS = ['fiscal', 'contabil', 'admin'];

let _app = null, _auth = null, _db = null, _am = null, _fm = null, _cfg = null;
let _sessao = null;                 // { uid, email, nome, perfil, offline }
let _unsub = null;
let _falhas = 0, _travadoAte = 0;

function _config() {
  if (_cfg !== null) return _cfg;
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(__dirname, 'firebaseWebConfig.json'), 'utf-8'));
    _cfg = raw && raw.apiKey ? raw : false;
  } catch (_) { _cfg = false; }
  return _cfg;
}

function _init() {
  if (_app) return true;
  const c = _config();
  if (!c) return false;
  const { initializeApp, getApps } = require('firebase/app');
  const nome = 'fiscocont-usuario';
  _app = getApps().find((a) => a.name === nome) || initializeApp(c, nome);
  _am = require('firebase/auth');
  _fm = require('firebase/firestore');
  _auth = _am.getAuth(_app);
  _db = _fm.getFirestore(_app);
  return true;
}

function _norm(email) { return String(email || '').trim().toLowerCase(); }

function _msgErro(e) {
  const c = (e && e.code) || '';
  if (c === 'auth/invalid-credential' || c === 'auth/wrong-password' || c === 'auth/user-not-found' || c === 'auth/invalid-email')
    return 'E-mail ou senha incorretos.';
  if (c === 'auth/too-many-requests') return 'Muitas tentativas. Aguarde alguns minutos ou redefina a senha.';
  if (c === 'auth/user-disabled') return 'Usuário desativado.';
  if (c === 'auth/email-already-in-use') return 'Esse e-mail já tem conta.';
  if (c === 'auth/weak-password') return 'A senha precisa ter pelo menos 6 caracteres.';
  if (c === 'permission-denied' || /PERMISSION_DENIED|insufficient permissions/i.test(String(e && e.message)))
    return 'O Firebase recusou o acesso. Confira se as Regras de Segurança novas (firestore.rules) foram publicadas.';
  return String((e && e.message) || e);
}
const _offlineErr = (e) => ((e && e.code) || '') === 'auth/network-request-failed' || /network|ENOTFOUND|ECONN|offline/i.test(String(e && e.message));

// ------------------------------------------------------------------ "Salvar meus dados" (cofre do Windows)
// O e-mail e a senha ficam neste computador criptografados com o cofre do usuário do Windows (safeStorage/DPAPI):
// só abrem na mesma conta do Windows, e a senha nunca é enviada para a tela — o login usa a senha salva aqui mesmo.
// Sai do cofre quando a pessoa desmarca a opção, quando a senha salva deixa de funcionar ou quando o usuário é
// bloqueado. Desde a 2.1 o sistema não entra sem internet (não existe mais login offline).
let _safe = null;
function _safeStorage() {
  if (_safe !== null) return _safe;
  try { const { safeStorage } = require('electron'); _safe = safeStorage.isEncryptionAvailable() ? safeStorage : false; }
  catch (_) { _safe = false; }
  return _safe;
}
function _arqSalvo(userDataDir) { return path.join(userDataDir, 'login-salvo.dat'); }
function salvoLer(userDataDir) {
  const s = _safeStorage();
  if (!s) return null;
  try { const d = JSON.parse(s.decryptString(fs.readFileSync(_arqSalvo(userDataDir)))); return d && d.email && d.senha ? d : null; }
  catch (_) { return null; }
}
function salvoPublico(userDataDir) {
  const d = salvoLer(userDataDir);
  return { disponivel: !!_safeStorage(), email: d ? d.email : '', temSenha: !!(d && d.senha) };
}
function _salvoGravar(userDataDir, email, senha) {
  const s = _safeStorage();
  if (!s) return;
  try { fs.writeFileSync(_arqSalvo(userDataDir), s.encryptString(JSON.stringify({ email, senha, ts: Date.now() }))); } catch (_) {}
}
function salvoApagar(userDataDir) { try { fs.unlinkSync(_arqSalvo(userDataDir)); } catch (_) {} }
// limpa a verificação offline da 2.1 de teste (sessoes.dat), que não é mais usada
function limpaOfflineAntigo(userDataDir) { try { fs.unlinkSync(path.join(userDataDir, 'sessoes.dat')); } catch (_) {} }

// Conexão com a internet: o sistema só abre conectado (licença, login e bloqueio em tempo real dependem dela).
async function conectado() {
  const urls = ['https://firestore.googleapis.com/', 'https://www.googleapis.com/', 'https://www.google.com/generate_204'];
  let net = null;
  try { net = require('electron').net; } catch (_) {}
  for (const u of urls) {
    try {
      const r = await (net && net.fetch ? net.fetch(u, { method: 'HEAD', signal: AbortSignal.timeout(6000) })
                                        : fetch(u, { method: 'HEAD', signal: AbortSignal.timeout(6000) }));
      if (r && r.status > 0) return true;
    } catch (_) { /* tenta o próximo */ }
  }
  return false;
}

// ------------------------------------------------------------------ login
async function _cadastroDoUsuario(u) {
  const { doc, getDoc, setDoc, serverTimestamp } = _fm;
  const ref = doc(_db, 'usuarios', u.uid);
  let snap = await getDoc(ref);
  if (snap.exists()) return snap.data();
  const email = _norm(u.email);
  // convite feito pelo Admin (cadastro de usuário novo)
  const conv = await getDoc(doc(_db, 'convites', email)).catch(() => null);
  if (conv && conv.exists()) {
    const c = conv.data();
    await setDoc(ref, { nome: c.nome || email, email, perfil: c.perfil, ativo: true, criadoEm: serverTimestamp(), criadoPor: c.criadoPor || '' });
    snap = await getDoc(ref);
    return snap.data();
  }
  // primeiro Admin do sistema
  if (email === ADMIN_INICIAL) {
    if (!u.emailVerified) {
      try { await _am.sendEmailVerification(u); } catch (_) {}
      throw Object.assign(new Error('Confirme o seu e-mail: enviamos um link para ' + email + '. Depois de clicar nele, entre de novo.'), { code: 'fc/verificar' });
    }
    await setDoc(ref, { nome: 'Rafael', email, perfil: 'admin', ativo: true, criadoEm: serverTimestamp(), criadoPor: 'inicial' });
    snap = await getDoc(ref);
    return snap.data();
  }
  return null;
}

async function login(userDataDir, email, senha, onBloqueado, opcoes = {}) {
  email = _norm(email);
  const salvo = salvoLer(userDataDir);
  const usouSalva = !!(opcoes.usarSalva && salvo && salvo.email === email);
  if (usouSalva) senha = salvo.senha;
  if (!email || !senha) return { ok: false, erro: 'Informe o e-mail e a senha.' };
  if (Date.now() < _travadoAte) {
    return { ok: false, erro: `Muitas tentativas erradas. Tente de novo em ${Math.ceil((_travadoAte - Date.now()) / 1000)} s.` };
  }
  if (!_init()) return { ok: false, erro: 'Configuração do Firebase ausente neste instalador.' };
  try {
    const cred = await _am.signInWithEmailAndPassword(_auth, email, senha);
    const cad = await _cadastroDoUsuario(cred.user);
    if (!cad) { await _am.signOut(_auth); return _falhou('Este e-mail não está cadastrado no FiscoCont+. Peça ao Admin para cadastrar você.'); }
    if (cad.ativo !== true) { await _am.signOut(_auth); if (salvo && salvo.email === email) salvoApagar(userDataDir); return _falhou('Usuário bloqueado pelo Admin.'); }
    if (!PERFIS.includes(cad.perfil)) { await _am.signOut(_auth); return _falhou('Perfil do usuário inválido. Peça ao Admin para corrigir.'); }
    _falhas = 0;
    _sessao = { uid: cred.user.uid, email, nome: cad.nome || email, perfil: cad.perfil, offline: false,
                modulos: Array.isArray(cad.modulos) ? cad.modulos : null, trocarSenha: cad.trocarSenha === true };
    if (opcoes.salvar) _salvoGravar(userDataDir, email, senha);
    else if (opcoes.salvar === false && salvo && salvo.email === email) salvoApagar(userDataDir);
    _vigia(userDataDir, onBloqueado);
    return { ok: true, ..._sessao };
  } catch (e) {
    if (e && e.code === 'fc/verificar') { try { await _am.signOut(_auth); } catch (_) {} return { ok: false, erro: e.message }; }
    if (_offlineErr(e)) return { ok: false, erro: 'Sem conexão com a internet. O FiscoCont+ só funciona conectado.', semInternet: true };
    // Primeiro acesso do Admin inicial, sem nada na tela: se a conta dele ainda não existe, o próprio "Entrar" cria a
    // conta e manda o e-mail de confirmação. Se a conta já existe, a tentativa de criar falha e vale "senha incorreta".
    if (email === ADMIN_INICIAL && !usouSalva && /invalid-credential|user-not-found/.test((e && e.code) || '')) {
      const r = await criarAdminInicial(email, senha);
      if (r.ok) return { ok: false, info: true, erro: r.msg };
      if (!/já tem conta/.test(r.erro || '')) return { ok: false, erro: r.erro };
    }
    // a senha salva deixou de funcionar (trocada ou redefinida): sai do cofre
    if (usouSalva && /invalid-credential|wrong-password|user-not-found/.test((e && e.code) || '')) {
      salvoApagar(userDataDir);
      return _falhou('A senha salva neste computador não vale mais (foi trocada?). Digite a senha atual.');
    }
    return _falhou(_msgErro(e));
  }
}
function _falhou(msg) {
  _falhas += 1;
  if (_falhas >= 5) _travadoAte = Date.now() + Math.min(15 * 60, 30 * 2 ** (_falhas - 5)) * 1000;
  return { ok: false, erro: msg };
}

// Bloqueio, exclusão ou troca de perfil feitos pelo Admin chegam em segundos.
function _vigia(userDataDir, onBloqueado) {
  if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; }
  if (!_sessao || _sessao.offline) return;
  const { doc, onSnapshot } = _fm;
  _unsub = onSnapshot(doc(_db, 'usuarios', _sessao.uid), (snap) => {
    if (!_sessao) return;
    const d = snap.exists() ? snap.data() : null;
    if (!d || d.ativo !== true) {
      const sv = salvoLer(userDataDir);
      if (sv && sv.email === _sessao.email) salvoApagar(userDataDir);
      logout();
      if (onBloqueado) onBloqueado({ motivo: 'bloqueado' });
    } else {
      const mods = Array.isArray(d.modulos) ? d.modulos : null;
      const mudouPerfil = d.perfil !== _sessao.perfil && PERFIS.includes(d.perfil);
      const mudouMods = JSON.stringify(mods) !== JSON.stringify(_sessao.modulos);
      if (mudouPerfil || mudouMods) {
        if (mudouPerfil) _sessao.perfil = d.perfil;
        _sessao.modulos = mods;
        if (onBloqueado) onBloqueado({ motivo: 'perfil', perfil: _sessao.perfil, modulos: mods });
      }
    }
  }, () => {});
}

async function confereSenha(_userDataDir, senha) {
  if (!_sessao || !_init() || !_auth.currentUser) return { ok: false, erro: 'Sessão encerrada. Entre de novo.' };
  try {
    const cred = _am.EmailAuthProvider.credential(_sessao.email, senha);
    await _am.reauthenticateWithCredential(_auth.currentUser, cred);
    return { ok: true };
  } catch (e) {
    if (_offlineErr(e)) return { ok: false, erro: 'Sem conexão com a internet. Reconecte para continuar.' };
    return { ok: false, erro: 'Senha incorreta.' };
  }
}

function logout() {
  if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; }
  _sessao = null;
  if (_auth) _am.signOut(_auth).catch(() => {});
}

async function redefinirSenha(email) {
  if (!_init()) return { ok: false, erro: 'Configuração do Firebase ausente.' };
  try { await _am.sendPasswordResetEmail(_auth, _norm(email)); return { ok: true }; }
  catch (e) { return { ok: false, erro: _msgErro(e) }; }
}

// Primeiro acesso do Admin inicial: cria a conta e manda o e-mail de confirmação.
async function criarAdminInicial(email, senha) {
  email = _norm(email);
  if (email !== ADMIN_INICIAL) return { ok: false, erro: 'O primeiro acesso é só para o Admin do sistema. Os demais usuários são cadastrados pelo Admin.' };
  if (!_init()) return { ok: false, erro: 'Configuração do Firebase ausente.' };
  try {
    const cred = await _am.createUserWithEmailAndPassword(_auth, email, senha);
    await _am.sendEmailVerification(cred.user);
    await _am.signOut(_auth);
    return { ok: true, msg: 'Conta criada. Enviamos um link de confirmação para ' + email + '. Clique nele e depois entre com o e-mail e a senha.' };
  } catch (e) { return { ok: false, erro: _msgErro(e) }; }
}

function sessao() { return _sessao ? { ..._sessao } : null; }

// ------------------------------------------------------------------ funções no servidor do Google (Cloud Functions)
let _fn = null;
function _chamar(nome, dados) {
  if (!_fn) {
    const { getFunctions } = require('firebase/functions');
    _fn = getFunctions(_app, 'southamerica-east1');
  }
  const { httpsCallable } = require('firebase/functions');
  return httpsCallable(_fn, nome, { timeout: 130000 })(dados).then((r) => r.data).catch((e) => {
    const m = String((e && e.message) || e);
    if (/not-found|NOT_FOUND/.test((e && e.code) || '') && !/Usuário/.test(m))
      throw new Error('As funções do sistema ainda não foram publicadas no Firebase (rode "Publicar funções e regras" no GitHub).');
    throw new Error(m.replace(/^FirebaseError:\s*/, ''));
  });
}

// Primeiro acesso / senha provisória: a pessoa cria a própria senha (o Admin nunca fica sabendo a definitiva).
async function trocarSenha(userDataDir, nova, salvar) {
  if (!logado()) return { ok: false, erro: 'Sessão encerrada. Entre de novo.' };
  nova = String(nova || '');
  if (nova.length < 8 || !/[A-Za-z]/.test(nova) || !/[0-9]/.test(nova))
    return { ok: false, erro: 'A senha precisa ter pelo menos 8 caracteres, com letras e números.' };
  try {
    await _am.updatePassword(_auth.currentUser, nova);
    const { doc, updateDoc, serverTimestamp } = _fm;
    await updateDoc(doc(_db, 'usuarios', _sessao.uid), { trocarSenha: false, senhaTrocadaEm: serverTimestamp() });
    _sessao.trocarSenha = false;
    if (salvar) _salvoGravar(userDataDir, _sessao.email, nova);
    else { const sv = salvoLer(userDataDir); if (sv && sv.email === _sessao.email) salvoApagar(userDataDir); }
    return { ok: true };
  } catch (e) {
    if (((e && e.code) || '') === 'auth/requires-recent-login') return { ok: false, erro: 'Por segurança, saia e entre de novo com a senha provisória.' };
    return { ok: false, erro: _msgErro(e) };
  }
}

async function chatIA(mensagem, historico) {
  if (!logado()) throw new Error('Entre com o seu usuário (e com internet) para usar o chat.');
  return _chamar('chatIA', { mensagem, historico });
}
function logado() { return !!(_sessao && !_sessao.offline && _auth && _auth.currentUser); }
function db() { return logado() ? _db : null; }
function fsMod() { return _fm; }

// ------------------------------------------------------------------ Admin: usuários
function _exigeAdmin() {
  if (!_sessao || _sessao.perfil !== 'admin') throw new Error('Acesso restrito ao Admin.');
  if (!logado()) throw new Error('Sem internet: o cadastro de usuários precisa de conexão.');
}
const _iso = (v) => (v && typeof v.toDate === 'function' ? v.toDate().toISOString() : null);

async function listarUsuarios() {
  _exigeAdmin();
  const { collection, getDocs } = _fm;
  const out = [];
  (await getDocs(collection(_db, 'usuarios'))).forEach((d) => {
    const v = d.data() || {};
    out.push({ uid: d.id, nome: v.nome || '', email: v.email || '', perfil: v.perfil || '', ativo: v.ativo === true,
               modulos: Array.isArray(v.modulos) ? v.modulos : null, trocarSenha: v.trocarSenha === true,
               criadoEm: _iso(v.criadoEm), voce: d.id === _sessao.uid });
  });
  const conv = [];
  (await getDocs(collection(_db, 'convites'))).forEach((d) => {
    const v = d.data() || {};
    if (!out.some((u) => u.email === d.id)) conv.push({ email: d.id, nome: v.nome || '', perfil: v.perfil || '', criadoEm: _iso(v.criadoEm) });
  });
  out.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
  return { usuarios: out, convites: conv };
}

async function cadastrarUsuario({ nome, email, perfil, modulos }) {
  _exigeAdmin();
  email = _norm(email);
  nome = String(nome || '').trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new Error('E-mail inválido.');
  if (!nome) throw new Error('Informe o nome.');
  if (!PERFIS.includes(perfil)) throw new Error('Perfil inválido.');
  const r = await _chamar('criarUsuario', { nome, email, perfil, modulos: Array.isArray(modulos) ? modulos : null });
  return { ok: true, uid: r.uid, senha: r.senha, email, nome };
}

async function novaSenhaProvisoria(uid) {
  _exigeAdmin();
  const r = await _chamar('novaSenhaProvisoria', { uid });
  return { ok: true, senha: r.senha };
}

async function alterarUsuario(uid, { ativo, perfil, nome, modulos }) {
  _exigeAdmin();
  if (uid === _sessao.uid && (ativo === false || (perfil && perfil !== 'admin')))
    throw new Error('Você não pode bloquear nem tirar o perfil Admin de você mesmo.');
  const mud = {};
  if (typeof ativo === 'boolean') mud.ativo = ativo;
  if (perfil) { if (!PERFIS.includes(perfil)) throw new Error('Perfil inválido.'); mud.perfil = perfil; }
  if (nome) mud.nome = String(nome).trim();
  if (modulos === null) mud.modulos = _fm.deleteField();
  else if (Array.isArray(modulos)) mud.modulos = [...new Set(modulos.filter((m) => typeof m === 'string' && /^[a-z0-9-]{2,40}$/.test(m)))];
  const { doc, updateDoc, serverTimestamp } = _fm;
  await updateDoc(doc(_db, 'usuarios', uid), { ...mud, alteradoEm: serverTimestamp(), alteradoPor: _sessao.email });
  return { ok: true };
}

async function cancelarConvite(email) {
  _exigeAdmin();
  const { doc, deleteDoc } = _fm;
  await deleteDoc(doc(_db, 'convites', _norm(email)));
  return { ok: true };
}

// ------------------------------------------------------------------ Admin: licenças (sem credencial de administrador)
async function listarLicencas() {
  _exigeAdmin();
  const { collection, getDocs } = _fm;
  const itens = [];
  (await getDocs(collection(_db, 'licencas'))).forEach((d) => {
    const v = d.data() || {};
    itens.push({ codigo: d.id, status: v.status || 'pendente', hostname: v.hostname || '', plataforma: v.plataforma || '',
                 versao: v.versao || '', usuario: v.usuario || '',
                 primeiroAcesso: _iso(v.primeiroAcesso), ultimoAcesso: _iso(v.ultimoAcesso) });
  });
  itens.sort((a, b) => new Date(b.ultimoAcesso || 0) - new Date(a.ultimoAcesso || 0));
  return itens;
}
async function statusLicenca(codigo, status) {
  _exigeAdmin();
  if (!['ativo', 'bloqueado', 'pendente'].includes(status)) throw new Error('Status inválido.');
  const { doc, setDoc, serverTimestamp } = _fm;
  await setDoc(doc(_db, 'licencas', codigo), { status, atualizadoPor: _sessao.email, atualizadoEm: serverTimestamp() }, { merge: true });
  return { ok: true };
}

module.exports = {
  ADMIN_INICIAL, conectado, salvoPublico, salvoApagar, limpaOfflineAntigo, login, logout, confereSenha, redefinirSenha, criarAdminInicial, sessao, logado, db, fsMod,
  listarUsuarios, cadastrarUsuario, novaSenhaProvisoria, alterarUsuario, cancelarConvite, trocarSenha, chatIA, listarLicencas, statusLicenca,
};
