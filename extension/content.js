// content.js - 微信读书截图素材助手

console.log('[素材助手] 已加载');

(function () {
  'use strict';

  let panelEl = null;
  let imageData = null; // base64

  // ========== 注入页面脚本（绕过 CSP） ==========
  try {
    const s = document.createElement('script');
    s.textContent = `
      document.addEventListener('paste', (e) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        for (const item of items) {
          if (item.type.startsWith('image/')) {
            const blob = item.getAsFile();
            const reader = new FileReader();
            reader.onload = () => {
              window.dispatchEvent(new CustomEvent('__weread_saver_paste_image__', {
                detail: { dataUrl: reader.result }
              }));
            };
            reader.readAsDataURL(blob);
            break;
          }
        }
      });
    `;
    document.head.appendChild(s);
  } catch (e) {
    console.log('[素材助手] 页面脚本注入失败:', e.message);
  }

  // ========== 常驻浮动按钮 ==========
  const fab = document.createElement('div');
  fab.className = 'weread-saver-fab';
  fab.innerHTML = `
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
      <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
    </svg>
  `;
  fab.title = '记录素材';
  document.body.appendChild(fab);

  fab.addEventListener('click', () => {
    openPanel();
  });

  // 监听页面级粘贴事件
  window.addEventListener('__weread_saver_paste_image__', (e) => {
    const dataUrl = e.detail?.dataUrl;
    if (dataUrl) {
      console.log('[素材助手] 收到粘贴图片');
      if (!panelEl) openPanel();
      setTimeout(() => handleImageData(dataUrl), 100);
    }
  });

  // 监听面板内的粘贴
  document.addEventListener('paste', (e) => {
    if (!panelEl) return;
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const blob = item.getAsFile();
        const reader = new FileReader();
        reader.onload = () => handleImageData(reader.result);
        reader.readAsDataURL(blob);
        break;
      }
    }
  });

  // ========== 保存面板 ==========
  function openPanel() {
    if (panelEl) return;
    imageData = null;
    const { bookTitle, chapterTitle, author } = getBookInfo();

    panelEl = document.createElement('div');
    panelEl.className = 'weread-saver-panel';
    panelEl.innerHTML = `
      <div class="weread-saver-panel-header">
        <span class="weread-saver-panel-title">记录素材</span>
        <button class="weread-saver-panel-close">&times;</button>
      </div>
      <div class="weread-saver-panel-body">
        <div class="weread-saver-field">
          <label>截图（可选）</label>
          <div class="weread-saver-dropzone" id="wsDropzone">
            <div class="weread-saver-dropzone-hint">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#999" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <path d="M21 15l-5-5L5 21"/>
              </svg>
              <p>按 <kbd>Ctrl+V</kbd> 粘贴截图，或点击/拖拽上传</p>
            </div>
            <img class="weread-saver-preview" id="wsPreview" style="display:none" />
            <input type="file" id="wsFileInput" accept="image/*" style="display:none" />
          </div>
        </div>
        <div class="weread-saver-field">
          <label>原文内容 <span class="required">*</span></label>
          <textarea class="weread-saver-textarea" id="wsSelectedText" placeholder="粘贴或输入书中原文..." rows="3"></textarea>
        </div>
        <div class="weread-saver-field">
          <label>我的感悟（可选）</label>
          <textarea class="weread-saver-textarea" id="wsContent" placeholder="记录你的想法和感悟..." rows="2"></textarea>
        </div>
        <div class="weread-saver-field">
          <label>精选评论（可选）</label>
          <textarea class="weread-saver-textarea" id="wsComment" placeholder="复制评论区的优质内容..." rows="2"></textarea>
        </div>
        <div class="weread-saver-field">
          <label>书名</label>
          <input class="weread-saver-input" id="wsBookTitle" value="${escapeAttr(bookTitle)}" placeholder="自动识别" />
        </div>
        <div class="weread-saver-field">
          <label>作者</label>
          <input class="weread-saver-input" id="wsAuthor" value="${escapeAttr(author)}" placeholder="自动识别或手动输入" />
        </div>
        <div class="weread-saver-field">
          <label>章节</label>
          <input class="weread-saver-input" id="wsChapterTitle" value="${escapeAttr(chapterTitle)}" placeholder="自动识别或自动匹配" />
        </div>
      </div>
      <div class="weread-saver-panel-footer">
        <div class="weread-saver-status" id="wsStatus"></div>
        <button class="weread-saver-save-btn" id="wsSaveBtn">保存素材</button>
      </div>
    `;
    document.body.appendChild(panelEl);

    // 事件
    panelEl.querySelector('.weread-saver-panel-close').addEventListener('click', closePanel);
    panelEl.querySelector('#wsSaveBtn').addEventListener('click', handleSave);

    // 面板拖拽
    const header = panelEl.querySelector('.weread-saver-panel-header');
    let isDragging = false, dragOffsetX = 0, dragOffsetY = 0;
    header.style.cursor = 'move';
    header.addEventListener('mousedown', (e) => {
      if (e.target.closest('.weread-saver-panel-close')) return;
      isDragging = true;
      const rect = panelEl.getBoundingClientRect();
      dragOffsetX = e.clientX - rect.left;
      dragOffsetY = e.clientY - rect.top;
      panelEl.style.transition = 'none';
    });
    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      let x = e.clientX - dragOffsetX;
      let y = e.clientY - dragOffsetY;
      x = Math.max(0, Math.min(x, window.innerWidth - panelEl.offsetWidth));
      y = Math.max(0, Math.min(y, window.innerHeight - panelEl.offsetHeight));
      panelEl.style.left = x + 'px';
      panelEl.style.top = y + 'px';
      panelEl.style.right = 'auto';
      panelEl.style.transform = 'none';
    });
    document.addEventListener('mouseup', () => { isDragging = false; });

    const dropzone = panelEl.querySelector('#wsDropzone');
    const fileInput = panelEl.querySelector('#wsFileInput');

    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files[0]) {
        const reader = new FileReader();
        reader.onload = () => handleImageData(reader.result);
        reader.readAsDataURL(e.target.files[0]);
      }
    });

    // 拖拽上传
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = () => handleImageData(reader.result);
        reader.readAsDataURL(file);
      }
    });

    // 阻止键盘事件冒泡
    panelEl.addEventListener('keydown', (e) => e.stopPropagation());
  }

  function closePanel() {
    if (panelEl) { panelEl.remove(); panelEl = null; }
    imageData = null;
  }

  function handleImageData(dataUrl) {
    imageData = dataUrl;
    const preview = panelEl?.querySelector('#wsPreview');
    const hint = panelEl?.querySelector('.weread-saver-dropzone-hint');
    if (preview && hint) {
      preview.src = dataUrl;
      preview.style.display = 'block';
      hint.style.display = 'none';
    }
    showStatus('截图已加载', 'success');
  }

  async function handleSave() {
    // 检查登录状态
    const auth = await sendMessage({ type: 'CHECK_AUTH' });
    if (!auth.loggedIn) {
      showStatus('请先点击浏览器工具栏上的插件图标登录', 'error');
      return;
    }

    const selectedText = panelEl.querySelector('#wsSelectedText').value.trim();
    const content = panelEl.querySelector('#wsContent').value.trim();
    const comment = panelEl.querySelector('#wsComment').value.trim();
    const bookTitle = panelEl.querySelector('#wsBookTitle').value.trim();
    const author = panelEl.querySelector('#wsAuthor').value.trim();
    const chapterTitle = panelEl.querySelector('#wsChapterTitle').value.trim();

    // 原文必填
    if (!selectedText) {
      showStatus('请输入原文内容', 'error');
      return;
    }

    const btn = panelEl.querySelector('#wsSaveBtn');
    btn.disabled = true;
    btn.textContent = '保存中...';
    showStatus('');

    // content: 感悟为空时，用原文前100字回退
    let materialContent = content;
    if (!materialContent) {
      materialContent = selectedText.length > 100
        ? selectedText.substring(0, 100) + '...'
        : selectedText;
    }

    // note: 拼接评论和作者信息
    let noteParts = [];
    if (comment) noteParts.push('[精选评论] ' + comment);
    if (author) noteParts.push('作者: ' + author);
    let note = noteParts.join('\n') || undefined;

    // 构建 locator_text
    let locatorText = bookTitle || '';
    if (chapterTitle) locatorText += ' / ' + chapterTitle;

    // 匹配 book_id 和 chapter_order
    let bookId = null;
    let chapterOrder = null;
    if (bookTitle) {
      try {
        const resp = await sendMessage({ type: 'GET_BOOKS' });
        if (resp.success) {
          const matched = resp.books.find(b =>
            b.title === bookTitle || b.title.includes(bookTitle) || bookTitle.includes(b.title)
          );
          if (matched) {
            bookId = matched.id;
            // 尝试匹配章节
            if (chapterTitle && matched.chapters) {
              const ch = matched.chapters.find(c =>
                c.title === chapterTitle || c.title.includes(chapterTitle) || chapterTitle.includes(c.title)
              );
              if (ch) chapterOrder = ch.chapter_order;
            }
          }
        }
      } catch (e) {}
    }

    const result = await sendMessage({
      type: 'SAVE_MATERIAL',
      data: {
        content: materialContent,
        selected_text: selectedText,
        note: note,
        book_id: bookId,
        chapter_order: chapterOrder,
        locator_text: locatorText || undefined,
        image_data: imageData || undefined
      }
    });

    btn.disabled = false;
    btn.textContent = '保存素材';

    if (result.success) {
      showStatus('保存成功！', 'success');
      setTimeout(closePanel, 1200);
    } else {
      showStatus('保存失败: ' + (result.error || '未知错误'), 'error');
    }
  }

  function getBookInfo() {
    let bookTitle = '';
    let chapterTitle = '';
    let author = '';

    // 尝试从页面 DOM 获取书名和作者
    // 微信读书页面结构：书名和作者通常在顶部导航栏
    const titleEl = document.querySelector('.readerBookInfo_title, .readerTopBar_title, [class*="bookTitle"], [class*="bookInfo"] [class*="title"]');
    const authorEl = document.querySelector('.readerBookInfo_author, .readerTopBar_author, [class*="bookAuthor"], [class*="bookInfo"] [class*="author"]');

    if (titleEl) bookTitle = titleEl.textContent.trim();
    if (authorEl) author = authorEl.textContent.trim();

    // 尝试从目录获取当前章节
    const activeChapterEl = document.querySelector('.readerCatalog_active, .readerCatalog_item.active, [class*="chapterItem"][class*="active"], [class*="catalog"] [class*="active"]');
    if (activeChapterEl) chapterTitle = activeChapterEl.textContent.trim();

    // 回退：从 document.title 获取
    // 格式可能是: "书名 - 作者 - 微信读书" 或 "章节名 - 书名 - 微信读书"
    if (!bookTitle) {
      const parts = document.title.split(/[-–—]/);
      const clean = parts.filter(p => !p.trim().includes('微信读书')).map(p => p.trim()).filter(Boolean);
      if (clean.length >= 2) {
        // 第一个可能是章节也可能是书名，第二个可能是书名也可能是作者
        // 用启发式判断：如果第一个包含"第"或"章"，则是章节
        const first = clean[0];
        const second = clean[1];
        if (/第.*[章节回]|chapter|序|前言|附录|后记/i.test(first)) {
          chapterTitle = first;
          bookTitle = second;
        } else {
          bookTitle = first;
          if (!author) author = second;
        }
      } else if (clean.length === 1) {
        bookTitle = clean[0];
      }
    }

    return { bookTitle, chapterTitle, author };
  }

  function showStatus(text, type) {
    const el = panelEl?.querySelector('#wsStatus');
    if (!el) return;
    el.textContent = text;
    el.className = 'weread-saver-status ' + (type || '');
  }

  function sendMessage(msg) {
    return new Promise(resolve => {
      try {
        chrome.runtime.sendMessage(msg, resp => {
          if (chrome.runtime.lastError) {
            resolve({ success: false, error: '插件已更新，请刷新页面后重试' });
          } else {
            resolve(resp || { success: false, error: '无响应' });
          }
        });
      } catch (e) {
        resolve({ success: false, error: '插件已更新，请刷新页面后重试' });
      }
    });
  }

  function escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

})();
