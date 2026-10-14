/* Merkle Root frontend. Dependency-free page controllers for the Flask API. */
(function () {
  'use strict';

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const escapeHtml = (value) => { const node = document.createElement('span'); node.textContent = String(value ?? ''); return node.innerHTML; };
  const formatHash = (value, length = 16) => !value ? '—' : value.length > length ? `${value.slice(0, length)}…${value.slice(-6)}` : value;

  async function request(url, options = {}) {
    let response;
    try { response = await fetch(url, options); } catch (_) { throw new Error('The audit server could not be reached.'); }
    let body = {};
    try { body = await response.json(); } catch (_) { /* non-JSON error */ }
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    return body;
  }

  function toast(message, type = 'success') {
    const container = $('#toast-container'); if (!container) return;
    const item = document.createElement('div'); item.className = `toast ${type}`; item.textContent = message; container.appendChild(item);
    setTimeout(() => item.remove(), 4200);
  }

  async function loading(button, task) {
    const original = button.innerHTML; button.disabled = true; button.innerHTML = `<span class="button-spinner">◌</span> ${button.dataset.loadingLabel || 'Working...'}`;
    try { return await task(); } finally { button.disabled = false; button.innerHTML = original; }
  }

  function setHealth(health) {
    $$('[data-health-status]').forEach((element) => {
      const connected = Boolean(health.blockchain); element.classList.toggle('connected', connected); element.classList.toggle('disconnected', !connected);
      const label = $('span:last-child', element); if (label) label.textContent = connected ? 'Blockchain connected' : 'Blockchain disconnected';
    });
  }

  async function checkHealth() { try { setHealth(await request('/api/health')); } catch (_) { setHealth({ blockchain: false }); } }

  function setupDropzone(dropzone, input, onFiles) {
    if (!dropzone || !input) return;
    dropzone.addEventListener('click', () => input.click());
    dropzone.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); } });
    ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add('drag-over'); }));
    ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove('drag-over'); }));
    dropzone.addEventListener('drop', (event) => onFiles(event.dataTransfer.files)); input.addEventListener('change', () => onFiles(input.files));
  }

  function setFileLabel(dropzone, files, multiple = false) {
    const label = $('[data-file-label]', dropzone); if (!label) return;
    label.textContent = files?.length ? (multiple ? `${files.length} file${files.length === 1 ? '' : 's'} selected` : files[0].name) : (multiple ? 'Select multiple files to build your tree' : 'No file selected');
  }

  function renderProof(result) {
    if (!result.verified) return '';
    const steps = [`<li><span class="proof-pill">LEAF</span><code>${escapeHtml(formatHash(result.file_hash, 20))}</code></li>`];
    (result.proof || []).forEach((step) => { steps.push(`<li><span class="proof-pill">SIBLING / ${escapeHtml(step.direction)}</span><code>${escapeHtml(formatHash(step.hash, 20))}</code></li>`); steps.push('<li><span class="proof-pill">PARENT</span><code>recomputed hash</code></li>'); });
    steps.push(`<li><span class="proof-pill final">ROOT</span><code>${escapeHtml(formatHash(result.root, 20))}</code></li>`);
    return `<div class="proof-block"><div class="subheading">Merkle proof path</div><ol class="proof-steps">${steps.join('')}</ol></div>`;
  }

  function renderVerify(result) {
    const panel = $('#verify-result'); if (!panel) return;
    const verified = result.verified === true; const onChain = result.on_chain === true; const status = verified ? (onChain ? 'success' : 'warning') : 'failure';
    const title = verified ? (onChain ? 'File verified on-chain' : 'File verified locally') : 'File not found';
    const record = result.record;
    panel.hidden = false; panel.className = `result-panel ${status}`;
    panel.innerHTML = `<div class="result-head"><span class="result-icon">${verified ? '✓' : '×'}</span><span>${title}</span></div><p class="result-message">${escapeHtml(result.message || 'Verification complete.')}</p><div class="hash-line"><span>File name</span><code>${escapeHtml(result.file_name || '—')}</code></div><div class="hash-line"><span>SHA-256</span><code>${escapeHtml(result.file_hash || '—')}</code></div>${verified ? `<div class="verification-record"><span>Dataset version</span><strong>${escapeHtml(result.dataset_version || '—')}</strong><span>Creator</span><strong>${escapeHtml(result.dataset_creator || '—')}</strong><span>On-chain timestamp</span><strong>${escapeHtml(record?.timestamp || 'Pending local anchor')}</strong></div>${renderProof(result)}<a class="tree-link" href="public.html${result.root ? `?root=${encodeURIComponent(result.root)}` : ''}">View dataset tree in Public Explorer <span>→</span></a>` : ''}`;
  }

  function initUser() {
    const dropzone = $('[data-dropzone]'); const input = $('#verify-file'); let selectedFile;
    setupDropzone(dropzone, input, (files) => { selectedFile = files?.[0]; setFileLabel(dropzone, selectedFile ? [selectedFile] : []); });
    $('#verify-form').addEventListener('submit', async (event) => {
      event.preventDefault(); if (!selectedFile) { toast('Select a file to verify.', 'error'); return; }
      const button = $('button[type="submit"]', event.currentTarget); const body = new FormData(); body.append('file', selectedFile);
      try { renderVerify(await loading(button, () => request('/api/verify', { method: 'POST', body }))); } catch (error) { renderVerify({ verified: false, file_name: selectedFile.name, message: error.message }); toast(error.message, 'error'); }
    });
  }

  function renderTree(target, dataset) {
    if (!target || !dataset) return;
    const levels = dataset.tree || []; const files = dataset.files || [];
    const rendered = levels.slice().reverse().map((level, levelIndex) => {
      const isLeaf = levelIndex === levels.length - 1;
      return `<div class="tree-level ${isLeaf ? 'leaf-level' : ''}">${(level.nodes || []).map((hash, nodeIndex) => {
        const file = isLeaf ? files[nodeIndex] : null; const fullHash = file?.full_hash || (level.full_nodes ? level.full_nodes[nodeIndex] : hash);
        return `<button class="tree-node ${isLeaf ? 'leaf-node' : ''}" type="button" data-full-hash="${escapeHtml(fullHash || hash)}" title="${escapeHtml(fullHash || hash)}">${file ? `<strong>${escapeHtml(file.name)}</strong>` : ''}<code>${escapeHtml(file?.hash || hash)}</code></button>`;
      }).join('')}</div>`;
    }).join('');
    target.innerHTML = `<div class="tree-meta"><span><small>ROOT</small><code>${escapeHtml(dataset.root || '—')}</code></span><span><small>VERSION</small><strong>${escapeHtml(dataset.version || '—')}</strong></span><span><small>FILES</small><strong>${escapeHtml(dataset.files?.length ?? dataset.file_count ?? '—')}</strong></span></div><div class="tree-legend"><span>Root</span><span>Intermediate hashes</span><span>Leaf files</span></div><div class="merkle-tree explorer-tree">${rendered || '<div class="table-empty">No tree data available.</div>'}</div><div id="node-detail" class="node-detail">Select a node to inspect its full hash.</div>`;
    $$('.tree-node', target).forEach((node) => node.addEventListener('click', () => { const detail = $('#node-detail', target); detail.innerHTML = `<span>${node.classList.contains('leaf-node') ? 'File hash' : 'Node hash'}</span><code>${escapeHtml(node.dataset.fullHash)}</code>`; $$('.tree-node', target).forEach((item) => item.classList.remove('selected')); node.classList.add('selected'); }));
  }

  function recordRow(record, clickable = false) { return `<tr ${clickable ? `data-root="${escapeHtml(record.root)}" tabindex="0"` : ''}><td>${escapeHtml(record.id)}</td><td><code title="${escapeHtml(record.root)}">${escapeHtml(formatHash(record.root, 18))}</code></td><td>${escapeHtml(record.version)}</td><td>${escapeHtml(record.creator)}</td><td><code title="${escapeHtml(record.submitted_by)}">${escapeHtml(formatHash(record.submitted_by, 12))}</code></td><td>${escapeHtml(record.timestamp)}</td></tr>`; }

  function initPublic() {
    const treeTarget = $('#tree-detail'); let overview;
    const select = $('#dataset-selector');
    function selectRoot(root) {
      const record = overview?.records?.find((item) => item.root === root); const registryTree = overview?.latest_root === root ? { root, version: record?.version, files: overview.latest_files, tree: overview.latest_tree } : null;
      if (registryTree?.tree) { renderTree(treeTarget, registryTree); return; }
      request(`/api/tree/${encodeURIComponent(root)}`).then((data) => renderTree(treeTarget, data)).catch((error) => { treeTarget.innerHTML = `<div class="table-empty">${escapeHtml(error.message)}</div>`; });
    }
    async function load() {
      try {
        overview = await request('/api/public-overview'); $('#stat-audits').textContent = overview.record_count ?? 0; $('#stat-block').textContent = overview.block_number ?? 0; $('#stat-address').textContent = overview.contract_address ? formatHash(overview.contract_address, 12) : 'Not deployed'; $('#stat-address').dataset.copy = overview.contract_address || '';
        const records = overview.records || []; select.innerHTML = records.length ? records.map((record) => `<option value="${escapeHtml(record.root)}">${escapeHtml(record.version)} · ${escapeHtml(formatHash(record.root, 14))}</option>`).join('') : '<option value="">No datasets recorded</option>';
        const body = $('#public-records-body'); body.innerHTML = records.length ? records.map((record) => recordRow(record, true)).join('') : '<tr><td colspan="6" class="table-empty">No audit records found on-chain.</td></tr>';
        $$('#public-records-body tr[data-root]').forEach((row) => { const choose = () => { select.value = row.dataset.root; selectRoot(row.dataset.root); }; row.addEventListener('click', choose); row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') choose(); }); });
        select.onchange = () => selectRoot(select.value); const initial = new URLSearchParams(location.search).get('root') || records[records.length - 1]?.root || overview.latest_root; if (initial) { select.value = initial; selectRoot(initial); } else if (overview.latest_tree) renderTree(treeTarget, { root: overview.latest_root, files: overview.latest_files, tree: overview.latest_tree });
      } catch (error) { treeTarget.innerHTML = `<div class="table-empty">${escapeHtml(error.message)}</div>`; }
    }
    $('#refresh-public').addEventListener('click', load); $('#stat-address').addEventListener('click', () => { if ($('#stat-address').dataset.copy) navigator.clipboard?.writeText($('#stat-address').dataset.copy).then(() => toast('Contract address copied.')); }); load();
  }

  function renderDataset(result) {
    const container = $('#dataset-result'); container.hidden = false; container.innerHTML = `<div class="dataset-summary"><div class="root-display"><span>MERKLE ROOT</span><code>${escapeHtml(result.root)}</code><button class="copy-button" type="button">Copy</button></div><div class="metric"><span>Files hashed</span><strong>${escapeHtml(result.file_count)}</strong></div><div class="metric"><span>Tree levels</span><strong>${escapeHtml(result.tree_levels)}</strong></div></div><div class="tree-wrap"><div class="tree-title"><span>Merkle tree structure</span><span>Root / leaves</span></div><div class="merkle-tree">${(result.tree || []).slice().reverse().map((level) => `<div class="tree-level">${level.nodes.map((hash) => `<div class="tree-node"><code>${escapeHtml(hash)}</code></div>`).join('')}</div>`).join('')}</div></div><div class="file-list"><div class="file-list-header"><span>Dataset files</span><span>${escapeHtml(result.file_count)} items</span></div><ul>${(result.files || []).map((file) => `<li><span>${escapeHtml(file.name)}</span><code>${escapeHtml(file.hash)}</code></li>`).join('')}</ul></div>`; $('#submit-root-value').textContent = result.root; $('#submit-form').dataset.root = result.root; $('.copy-button', container).addEventListener('click', () => navigator.clipboard?.writeText(result.root).then(() => toast('Root hash copied.'))); toast('Dataset hashed and Merkle tree generated.');
  }

  async function loadRecords() { const body = $('#records-body'); try { const result = await request('/api/records'); body.innerHTML = result.records?.length ? result.records.map((record) => recordRow(record)).join('') : '<tr><td colspan="6" class="table-empty">No audit records found on-chain.</td></tr>'; } catch (error) { body.innerHTML = `<tr><td colspan="6" class="table-empty">${escapeHtml(error.message)}</td></tr>`; } }

  function initCompany() {
    const dropzone = $('[data-dropzone]'); const input = $('#dataset-files'); let files = [];
    async function upload() { if (!files.length) return; const result = $('#dataset-result'); result.hidden = false; result.innerHTML = '<div class="table-empty">Hashing dataset and building tree...</div>'; const body = new FormData(); files.forEach((file) => body.append('files', file)); try { renderDataset(await request('/api/hash-dataset', { method: 'POST', body })); } catch (error) { result.innerHTML = `<div class="result-panel failure"><p>${escapeHtml(error.message)}</p></div>`; toast(error.message, 'error'); } }
    setupDropzone(dropzone, input, (selected) => { files = [...(selected || [])]; setFileLabel(dropzone, files, true); upload(); });
    $('#submit-form').addEventListener('submit', async (event) => { event.preventDefault(); const form = event.currentTarget; if (!form.dataset.root) { toast('Hash a dataset before submitting a root.', 'error'); return; } const panel = $('#submit-result'); try { const result = await loading($('button[type="submit"]', form), () => request('/api/submit-root', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root: form.dataset.root, version: form.version.value.trim(), creator: form.creator.value.trim() }) })); panel.hidden = false; panel.className = 'result-panel success'; panel.innerHTML = `<div class="result-head"><span class="result-icon">✓</span><span>Root anchored on-chain</span></div><p class="result-message">Block #${escapeHtml(result.block_number)} · Transaction ${escapeHtml(formatHash(result.tx_hash, 20))}</p>`; toast('Merkle root submitted successfully.'); loadRecords(); checkHealth(); } catch (error) { panel.hidden = false; panel.className = 'result-panel failure'; panel.innerHTML = `<div class="result-head"><span class="result-icon">×</span><span>Submission failed</span></div><p>${escapeHtml(error.message)}</p>`; toast(error.message, 'error'); } });
    $('#refresh-records').addEventListener('click', loadRecords); loadRecords();
  }

  document.addEventListener('DOMContentLoaded', () => { checkHealth(); if ($('.user-page')) initUser(); if ($('.public-page')) initPublic(); if ($('.company-page')) initCompany(); });
}());
