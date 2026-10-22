'use strict';
// Funções do FiscoCont+ no servidor do Google (Cloud Functions, 2ª geração, região São Paulo).
//
// Aqui fica o que NÃO pode ficar nos computadores do escritório:
//   • a credencial de administrador do Firebase (a função já roda com ela — nenhuma máquina precisa dela);
//   • a chave da API da Anthropic (lida do Firestore config/chat_ia, que nenhum computador consegue mais ler).
// Toda função confere quem chamou: login individual (e-mail e senha) e cadastro ativo em usuarios/{uid}; as de
// administração exigem perfil Admin.

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { setGlobalOptions } = require('firebase-functions/v2');
const { initializeApp } = require('firebase-admin/app');
const { getFirestore, FieldValue } = require('firebase-admin/firestore');
const { getAuth } = require('firebase-admin/auth');
const crypto = require('crypto');
const { SISTEMA_CHAT_IA } = require('./chatPrompt');

initializeApp();
setGlobalOptions({ region: 'southamerica-east1', maxInstances: 5 });

const db = getFirestore();
const PERFIS = ['fiscal', 'contabil', 'admin'];
const ADMIN_PRINCIPAL = 'rafael.max17@gmail.com';     // dono do sistema: ninguém altera perfil, situação ou senha dele

async function quemChamou(req, exigirAdmin) {
  const a = req.auth;
  if (!a || !a.token || a.token.firebase?.sign_in_provider !== 'password') {
    throw new HttpsError('unauthenticated', 'Entre com o seu usuário para continuar.');
  }
  const snap = await db.doc(`usuarios/${a.uid}`).get();
  const cad = snap.exists ? snap.data() : null;
  if (!cad || cad.ativo !== true) throw new HttpsError('permission-denied', 'Usuário sem acesso.');
  if (exigirAdmin && cad.perfil !== 'admin') throw new HttpsError('permission-denied', 'Acesso restrito ao Admin.');
  return { uid: a.uid, email: (a.token.email || '').toLowerCase(), ...cad };
}

// Senha provisória legível: 3 blocos (sem letras/números que se confundem: 0/O, 1/l/I).
function senhaProvisoria() {
  const L = 'ABCDEFGHJKMNPQRSTUVWXYZ', l = 'abcdefghjkmnpqrstuvwxyz', N = '23456789';
  const pega = (s, n) => Array.from({ length: n }, () => s[crypto.randomInt(s.length)]).join('');
  return `${pega(L, 1)}${pega(l, 2)}${pega(N, 1)}-${pega(L, 1)}${pega(l, 1)}${pega(N, 2)}-${pega(l, 2)}${pega(N, 1)}`;
}

function modulosValidos(m) {
  if (m === undefined || m === null) return null;
  if (!Array.isArray(m) || m.length > 200) throw new HttpsError('invalid-argument', 'Lista de módulos inválida.');
  return [...new Set(m.filter((x) => typeof x === 'string' && /^[a-z0-9-]{2,40}$/.test(x)))];
}

// ------------------------------------------------------------------ cadastro de usuário (Admin)
exports.criarUsuario = onCall(async (req) => {
  const adm = await quemChamou(req, true);
  const email = String(req.data?.email || '').trim().toLowerCase();
  const nome = String(req.data?.nome || '').trim();
  const perfil = String(req.data?.perfil || '');
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new HttpsError('invalid-argument', 'E-mail inválido.');
  if (!nome) throw new HttpsError('invalid-argument', 'Informe o nome.');
  if (!PERFIS.includes(perfil)) throw new HttpsError('invalid-argument', 'Perfil inválido.');
  const modulos = modulosValidos(req.data?.modulos);
  const senha = senhaProvisoria();
  let user;
  try {
    user = await getAuth().createUser({ email, password: senha, displayName: nome, emailVerified: true });
  } catch (e) {
    if (e.code === 'auth/email-already-exists') {
      user = await getAuth().getUserByEmail(email);
      const ja = await db.doc(`usuarios/${user.uid}`).get();
      if (ja.exists) throw new HttpsError('already-exists', 'Esse e-mail já está cadastrado. Use "Gerar nova senha" na lista.');
      await getAuth().updateUser(user.uid, { password: senha, displayName: nome, disabled: false });
    } else {
      throw new HttpsError('internal', 'Não foi possível criar o usuário: ' + e.message);
    }
  }
  await db.doc(`usuarios/${user.uid}`).set({
    nome, email, perfil, ativo: true, trocarSenha: true, ...(modulos ? { modulos } : {}),
    criadoEm: FieldValue.serverTimestamp(), criadoPor: adm.email,
  });
  await db.doc(`convites/${email}`).delete().catch(() => {});
  return { uid: user.uid, senha };
});

// ------------------------------------------------------------------ nova senha provisória (Admin)
exports.novaSenhaProvisoria = onCall(async (req) => {
  const adm = await quemChamou(req, true);
  const uid = String(req.data?.uid || '');
  const ref = db.doc(`usuarios/${uid}`);
  const snap = await ref.get();
  if (!uid || !snap.exists) throw new HttpsError('not-found', 'Usuário não encontrado.');
  if (String(snap.data().email || '').toLowerCase() === ADMIN_PRINCIPAL)
    throw new HttpsError('permission-denied', 'A senha do Admin principal não pode ser trocada por aqui.');
  const senha = senhaProvisoria();
  await getAuth().updateUser(uid, { password: senha });
  await getAuth().revokeRefreshTokens(uid);          // derruba sessões abertas com a senha antiga
  await ref.update({ trocarSenha: true, alteradoEm: FieldValue.serverTimestamp(), alteradoPor: adm.email });
  return { senha };
});

// ------------------------------------------------------------------ chat de ajuda tributária
exports.chatIA = onCall({ timeoutSeconds: 120, memory: '256MiB' }, async (req) => {
  await quemChamou(req, false);
  const mensagem = String(req.data?.mensagem || '').slice(0, 8000);
  const historico = Array.isArray(req.data?.historico) ? req.data.historico.slice(-30) : [];
  if (!mensagem.trim()) throw new HttpsError('invalid-argument', 'Mensagem vazia.');
  const cfg = await db.doc('config/chat_ia').get();
  const chave = cfg.exists ? cfg.data().anthropic_key : null;
  if (!chave) throw new HttpsError('failed-precondition', 'Chave de IA ainda não configurada na nuvem (config/chat_ia).');
  const resp = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'x-api-key': chave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6', max_tokens: 1500, system: SISTEMA_CHAT_IA,
      messages: [...historico, { role: 'user', content: mensagem }],
      tools: [{ type: 'web_search_20250305', name: 'web_search' }],
    }),
  });
  if (!resp.ok) {
    const t = await resp.text().catch(() => '');
    throw new HttpsError('internal', `Erro na API (${resp.status}): ${t.slice(0, 200)}`);
  }
  const data = await resp.json();
  const texto = (data.content || []).filter((b) => b.type === 'text').map((b) => b.text).join('\n');
  return { texto, resposta: { role: 'assistant', content: data.content } };
});
