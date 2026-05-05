// popup.js - 登录/设置弹窗逻辑

document.addEventListener('DOMContentLoaded', async () => {
  const loginView = document.getElementById('loginView');
  const userView = document.getElementById('userView');
  const loginBtn = document.getElementById('loginBtn');
  const logoutBtn = document.getElementById('logoutBtn');
  const loginMsg = document.getElementById('loginMsg');

  // 检查登录状态
  const auth = await sendMessage({ type: 'CHECK_AUTH' });
  if (auth.loggedIn) {
    showUserView(auth.user);
  } else {
    showLoginView();
  }

  // 登录
  loginBtn.addEventListener('click', async () => {
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value.trim();
    const apiBase = document.getElementById('apiBase').value.trim() || 'http://localhost:8000';

    if (!email || !password) {
      showMsg('请输入邮箱和密码', 'error');
      return;
    }

    loginBtn.disabled = true;
    loginBtn.textContent = '登录中...';
    showMsg('');

    const result = await sendMessage({
      type: 'LOGIN',
      data: { email, password, apiBase }
    });

    loginBtn.disabled = false;
    loginBtn.textContent = '登录';

    if (result.success) {
      showUserView(result.user);
    } else {
      showMsg(result.error || '登录失败', 'error');
    }
  });

  // 退出
  logoutBtn.addEventListener('click', async () => {
    await chrome.storage.local.remove(['token', 'user']);
    showLoginView();
  });

  // Enter 键登录
  document.getElementById('password').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loginBtn.click();
  });

  function showLoginView() {
    loginView.style.display = 'block';
    userView.style.display = 'none';
    loginMsg.textContent = '';
  }

  function showUserView(user) {
    loginView.style.display = 'none';
    userView.style.display = 'block';
    document.getElementById('userName').textContent = user?.username || '用户';
    document.getElementById('userEmail').textContent = user?.email || '';
    document.getElementById('userAvatar').textContent = (user?.username || user?.email || '?')[0].toUpperCase();
  }

  function showMsg(text, type) {
    loginMsg.textContent = text;
    loginMsg.className = 'popup-msg ' + (type || '');
  }
});

function sendMessage(msg) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (resp) => {
      resolve(resp || {});
    });
  });
}
