const API_BASE = '/api';

let currentView = 'search';
let documents = [];
let collections = [];
let searchResults = [];
let selectedResultIndex = -1;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateStr) {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}

function getFileIcon(fileType) {
  const icons = {
    pdf: '◈',
    md: '◇',
    txt: '○',
    html: '◆',
    rst: '□',
    docx: '▣',
    url: '◎'
  };
  return icons[fileType] || '○';
}

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showToast(message, type = 'success') {
  const container = $('#toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 200);
  }, 4000);
}

function showLoading(text = 'PROCESSING') {
  $('#loading-text').textContent = text.toUpperCase();
  $('#loading-overlay').classList.remove('hidden');
}

function hideLoading() {
  $('#loading-overlay').classList.add('hidden');
}

async function apiRequest(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

async function checkHealth() {
  try {
    const data = await apiRequest('/health');
    const dot = $('#status-dot');
    const text = $('#status-text');

    if (data.database === 'healthy') {
      dot.classList.remove('error');
      dot.classList.add('connected');
      text.textContent = 'online';
    } else {
      dot.classList.add('error');
      text.textContent = 'degraded';
    }
  } catch (e) {
    $('#status-dot').classList.add('error');
    $('#status-text').textContent = 'offline';
  }
}

async function loadDocuments() {
  try {
    const data = await apiRequest('/documents');
    documents = data.documents;
    renderDocuments();
    renderStats();
    loadCollections(); 
  } catch (e) {
    showToast('Failed to load documents', 'error');
  }
}

async function loadCollections() {
  try {
    const data = await apiRequest('/collections');
    collections = data;
    renderCollectionsDropdowns(data);
  } catch (e) {
    console.error('Failed to load collections:', e);
  }
}

function renderCollectionsDropdowns(colList) {
  const selectors = ['#search-collection', '#upload-collection', '#url-collection', '#site-collection'];

  selectors.forEach(sel => {
    const el = $(sel);
    if (!el) return;

    const currentVal = el.value;
    const isSearch = sel === '#search-collection';

    let html = isSearch ? '<option value="">all collections</option>' : '';

    const uniqueCols = [...new Set(['default', ...colList])].sort();

    uniqueCols.forEach(c => {
      html += `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`;
    });

    el.innerHTML = html;
    if (currentVal && uniqueCols.includes(currentVal)) {
      el.value = currentVal;
    } else if (!isSearch) {
      el.value = 'default';
    }
  });
}

window.addNewCollection = function (selectId) {
  const name = prompt('Enter new collection name:');
  if (name && name.trim()) {
    const cleanName = name.trim().toLowerCase();
    if (!collections.includes(cleanName)) {
      collections.push(cleanName);
      renderCollectionsDropdowns(collections);
    }
    const select = $(`#${selectId}`) || $(selectId);
    if (select) select.value = cleanName;
  }
};

async function deleteDocument(id) {
  if (!confirm('DELETE THIS DOCUMENT?')) return;

  try {
    await fetch(`${API_BASE}/documents/${id}`, { method: 'DELETE' });
    showToast('Document deleted');
    loadDocuments();
  } catch (e) {
    showToast('Delete failed', 'error');
  }
}

async function searchDocuments(query, collection) {
  showLoading('SEARCHING');
  try {
    const body = { query, k: 10 };
    if (collection) body.collection = collection;

    const data = await apiRequest('/search', {
      method: 'POST',
      body: JSON.stringify(body)
    });

    searchResults = data.results;
    renderSearchResults(data);
    selectedResultIndex = -1;
  } catch (e) {
    showToast('Search failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function uploadFile(file, collection = 'default') {
  showLoading(`UPLOADING ${file.name.toUpperCase()}`);
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/documents?collection=${encodeURIComponent(collection)}`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail);
    }

    const doc = await response.json();
    if (doc.chunk_count === 0 && doc.id) {
      showToast('File skipped (unchanged)', 'success');
    } else {
      showToast(`Uploaded: ${file.name}`);
    }
    loadDocuments();
  } catch (e) {
    showToast('Upload failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function ingestUrl(url, collection = 'default') {
  showLoading('FETCHING URL');
  try {
    await apiRequest('/ingest/url', {
      method: 'POST',
      body: JSON.stringify({ url, collection })
    });
    showToast('URL imported');
    loadDocuments();
  } catch (e) {
    showToast('Import failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function crawlSite(options) {
  showLoading('CRAWLING SITE');
  try {
    const data = await apiRequest('/ingest/site', {
      method: 'POST',
      body: JSON.stringify(options)
    });
    showToast(`Crawled ${data.documents_created} pages`);
    loadDocuments();
  } catch (e) {
    showToast('Crawl failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

function renderStats() {
  const totalDocs = documents.length;
  const totalChunks = documents.reduce((sum, d) => sum + (d.chunk_count || 0), 0);
  const totalSize = documents.reduce((sum, d) => sum + (d.file_size || 0), 0);

  const stats = $('#doc-stats');
  if (stats) {
    stats.innerHTML = `
      <div class="stat-card">
        <div class="stat-label">documents</div>
        <div class="stat-value">${totalDocs}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">chunks</div>
        <div class="stat-value">${totalChunks}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">size</div>
        <div class="stat-value">${formatBytes(totalSize)}</div>
      </div>
    `;
  }
}

function renderDocuments() {
  const container = $('#documents-list');
  if (!container) return;

  if (documents.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">∅</div>
        <div class="empty-state-title">no documents</div>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="doc-list">
      ${documents.map((doc, i) => `
        <div class="doc-item" data-id="${doc.id}" tabindex="0">
          <div class="doc-icon">${getFileIcon(doc.file_type)}</div>
          <div class="doc-info">
            <div class="doc-name-row" style="display: flex; align-items: center; gap: 8px;">
              <div class="doc-name">${escapeHtml(doc.name)}</div>
              <span class="badge" style="border-style: dashed; color: var(--accent); opacity: 0.8;">${escapeHtml(doc.collection)}</span>
            </div>
            <div class="doc-meta">
              <span class="badge">${doc.file_type.toUpperCase()}</span>
              <span>${doc.chunk_count} chunks</span>
              <span>${formatBytes(doc.file_size)}</span>
              <span>${formatDate(doc.created_at)}</span>
            </div>
          </div>
          <div class="doc-actions">
            <button class="btn btn-danger" onclick="deleteDocument('${doc.id}')" title="Delete">DEL</button>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderSearchResults(data) {
  const container = $('#search-results');
  if (!container) return;

  container.innerHTML = '';

  if (data.results.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">?</div>
        <div class="empty-state-title">no results</div>
      </div>
    `;
    return;
  }

  const resultCountDiv = document.createElement('div');
  resultCountDiv.className = 'result-count';
  resultCountDiv.textContent = `${data.results.length} RESULTS FOR "${escapeHtml(data.query)}"`;
  container.appendChild(resultCountDiv);

  data.results.forEach((res, i) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.setAttribute('tabindex', '0');
    item.dataset.index = i;

    item.addEventListener('click', () => showChunkDetail(res));

    item.innerHTML = `
      <div class="result-header">
        <span class="result-source">${escapeHtml(res.document_name)}${res.page_number ? ` (Page ${res.page_number})` : ''}</span>
        <span class="result-score">${(res.score * 100).toFixed(1)}%</span>
      </div>
      <div class="result-content" style="max-height: initial; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">${escapeHtml(res.content)}</div>
    `;
    container.appendChild(item);
  });
}

function showChunkDetail(chunk) {
  $('#modal-title').textContent = chunk.document_name;
  $('#modal-body').textContent = chunk.content;
  $('#modal-meta').innerHTML = `
    <span>Score: ${(chunk.score * 100).toFixed(2)}%</span> &bull; 
    <span>Chunk: ${chunk.chunk_index}</span>
    ${chunk.page_number ? `&bull; <span>Page: ${chunk.page_number}</span>` : ''}
  `;
  $('#chunk-modal').classList.remove('hidden');
}

function closeChunkModal() {
  $('#chunk-modal').classList.add('hidden');
}

function switchView(view) {
  currentView = view;

  $$('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === view);
  });

  $$('.view').forEach(v => {
    v.classList.toggle('hidden', v.id !== `view-${view}`);
  });

  if (view === 'documents') {
    loadDocuments();
  }
  if (view === 'search') {
    setTimeout(() => $('#search-query')?.focus(), 100);
  }
}

function initKeyboardNav() {
  document.addEventListener('keydown', (e) => {
    const isModalOpen = !($('#chunk-modal').classList.contains('hidden'));
    const inInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);

    if (e.key === 'Escape') {
      if (isModalOpen) {
        e.preventDefault();
        closeChunkModal();
        return;
      }
      if (inInput) {
        document.activeElement.blur();
      }
      selectedResultIndex = -1;
      updateResultSelection();
      return;
    }

    if (isModalOpen) return;

    if (!inInput && e.key >= '1' && e.key <= '4') {
      const navItems = $$('.nav-item');
      const index = parseInt(e.key) - 1;
      if (navItems[index]) {
        e.preventDefault();
        navItems[index].click();
      }
      return;
    }

    if (e.key === '/' && !inInput) {
      e.preventDefault();
      switchView('search');
      $('#search-query')?.focus();
      return;
    }

    if (!inInput && currentView === 'search') {
      const results = $$('.result-item');
      if (results.length === 0) return;

      if (e.key === 'ArrowDown' || e.key === 'j') {
        e.preventDefault();
        selectedResultIndex = Math.min(selectedResultIndex + 1, results.length - 1);
        updateResultSelection();
      } else if (e.key === 'ArrowUp' || e.key === 'k') {
        e.preventDefault();
        selectedResultIndex = Math.max(selectedResultIndex - 1, 0);
        updateResultSelection();
      } else if (e.key === 'Enter' && selectedResultIndex >= 0) {
        e.preventDefault();
        showChunkDetail(searchResults[selectedResultIndex]);
      }
    }
  });
}

function updateResultSelection() {
  $$('.result-item').forEach((item, i) => {
    item.classList.toggle('selected', i === selectedResultIndex);
    if (i === selectedResultIndex) {
      item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
}

function initEventListeners() {
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchView(item.dataset.view));
  });

  $$('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const tabId = tab.dataset.tab;
      $('#tab-single').classList.toggle('hidden', tabId !== 'single');
      $('#tab-site').classList.toggle('hidden', tabId !== 'site');
    });
  });

  $('#search-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const query = $('#search-query').value.trim();
    const collection = $('#search-collection').value.trim();
    if (query) {
      searchDocuments(query, collection);
    }
  });

  $('#export-btn').addEventListener('click', async () => {
    showLoading('EXPORTING');
    try {
      const collection = $('#search-collection').value.trim();
      const url_params = collection ? `?collection=${encodeURIComponent(collection)}` : '';
      const data = await apiRequest(`/documents/export${url_params}`);

      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `mnemos_export_${collection || 'all'}_${new Date().getTime()}.json`;
      a.click();

      showToast('Export complete');
    } catch (e) {
      showToast('Export failed: ' + e.message, 'error');
    } finally {
      hideLoading();
    }
  });

  const uploadZone = $('#upload-zone');
  const fileInput = $('#file-input');

  uploadZone?.addEventListener('click', () => fileInput.click());

  uploadZone?.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
  });

  uploadZone?.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
  });

  uploadZone?.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const collection = $('#upload-collection').value.trim() || 'default';
      uploadFile(files[0], collection);
    }
  });

  fileInput?.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      const collection = $('#upload-collection').value.trim() || 'default';
      uploadFile(fileInput.files[0], collection);
    }
  });

  $('#url-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const url = $('#url-input').value.trim();
    const collection = $('#url-collection').value.trim() || 'default';
    if (url) {
      ingestUrl(url, collection);
      $('#url-input').value = '';
    }
  });

  $('#site-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const options = {
      url: $('#site-url').value.trim(),
      path_filter: $('#site-path').value.trim() || null,
      collection: $('#site-collection').value.trim() || 'default',
      max_pages: parseInt($('#site-max-pages').value) || 50,
      max_depth: parseInt($('#site-max-depth').value) || 3
    };
    if (options.url) {
      crawlSite(options);
    }
  });

  $('#modal-close')?.addEventListener('click', closeChunkModal);
  $('#modal-close-btn')?.addEventListener('click', closeChunkModal);
  $('#chunk-modal')?.addEventListener('click', (e) => {
    if (e.target === $('#chunk-modal')) closeChunkModal();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  initKeyboardNav();
  checkHealth();
  loadDocuments(); 
  loadCollections(); 

  setTimeout(() => $('#search-query')?.focus(), 100);
  setInterval(checkHealth, 30000);
});