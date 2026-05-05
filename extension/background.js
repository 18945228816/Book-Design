// background.js - Service Worker: handles API calls from content script

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'LOGIN') {
    handleLogin(msg.data).then(sendResponse);
    return true;
  }
  if (msg.type === 'SAVE_MATERIAL') {
    handleSaveMaterial(msg.data).then(sendResponse);
    return true;
  }
  if (msg.type === 'GET_BOOKS') {
    handleGetBooks().then(sendResponse);
    return true;
  }
  if (msg.type === 'CHECK_AUTH') {
    checkAuth().then(sendResponse);
    return true;
  }
});

async function getApiBase() {
  const { apiBase } = await chrome.storage.local.get('apiBase');
  return apiBase || 'http://localhost:8000';
}

async function getToken() {
  const { token } = await chrome.storage.local.get('token');
  return token;
}

async function handleLogin({ email, password, apiBase }) {
  if (apiBase) {
    await chrome.storage.local.set({ apiBase });
  }
  const base = apiBase || await getApiBase();
  try {
    const resp = await fetch(`${base}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      return { success: false, error: err.detail || '登录失败' };
    }
    const data = await resp.json();
    await chrome.storage.local.set({
      token: data.token,
      user: { id: data.user_id, email: data.email, username: data.username }
    });
    return { success: true, user: { email: data.email, username: data.username } };
  } catch (e) {
    return { success: false, error: '无法连接到服务器: ' + e.message };
  }
}

async function handleSaveMaterial(data) {
  const base = await getApiBase();
  const token = await getToken();
  if (!token) return { success: false, error: '未登录' };

  try {
    const resp = await fetch(`${base}/api/v1/materials`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        content: data.content,
        source_type: '微信读书',
        selected_text: data.selected_text || undefined,
        note: data.note || undefined,
        book_id: data.book_id || undefined,
        chapter_order: data.chapter_order || undefined,
        locator_text: data.locator_text || undefined,
        image_data: data.image_data || undefined,
        status: 'completed',
        entry_mode: 'weread_extension'
      })
    });
    console.log('[素材助手] API 响应:', resp.status);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      console.log('[素材助手] API 错误:', err);
      if (resp.status === 401) {
        await chrome.storage.local.remove(['token', 'user']);
        return { success: false, error: '登录已过期，请重新登录' };
      }
      return { success: false, error: err.detail || `保存失败 (${resp.status})` };
    }
    const result = await resp.json();
    return { success: true, material: result };
  } catch (e) {
    return { success: false, error: '网络错误: ' + e.message };
  }
}

async function handleGetBooks() {
  const base = await getApiBase();
  const token = await getToken();
  if (!token) return { success: false, error: '未登录' };

  try {
    const resp = await fetch(`${base}/api/v1/books`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!resp.ok) return { success: false, error: '获取书籍列表失败' };
    const data = await resp.json();
    return { success: true, books: data.items || [] };
  } catch (e) {
    return { success: false, error: '网络错误: ' + e.message };
  }
}

async function checkAuth() {
  const { token, user, apiBase } = await chrome.storage.local.get(['token', 'user', 'apiBase']);
  if (!token) return { loggedIn: false };
  return { loggedIn: true, user, apiBase: apiBase || 'http://localhost:8000' };
}
