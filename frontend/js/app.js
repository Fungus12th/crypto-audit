/* Merkle Root frontend — dependency-free page controllers */
(function () {
  'use strict';

  const $ = (s, scope = document) => scope.querySelector(s);
  const $$ = (s, scope = document) => [...scope.querySelectorAll(s)];

  // ─── Toast Notifications ──────────────────────────────────────────
  function showToast(message, type = 'success') {
    const c = $('#toast-container');
    if (!c) return;
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = message;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4200);
  }

  // ─── Formatting helpers ───────────────────────────────────────────
  function formatHash(hash, len = 16) {
    if (!hash) return '—';
    return hash.length > len ? hash.slice(0, len) + '…' + hash.slice(-6) : hash;
  }
  function formatAddress(addr, len = 10) { return formatHash(addr, len); }

  // ─── Fetch wrapper ────────────────────────────────────────────────
  async function request(url, options = {}) {
    const session = getSession();
    if (session && session.token) {
      options.headers = options.headers || {};
      options.headers['Authorization'] = 'Bearer ' + session.token;
    }
    let response;
    try {
      response = await fetch(url, options);
    } catch (e) {
      throw new Error('Audit server is unreachable.');
    }
    let body = {};
    try { body = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    return body;
  }

  // ─── Loading button helper ────────────────────────────────────────
  async function withLoading(button, work) {
    const original = button.innerHTML;
    const label = button.dataset.loadingLabel || 'Processing…';
    button.disabled = true;
    button.innerHTML = label;
    try { return await work(); }
    finally { button.disabled = false; button.innerHTML = original; }
  }

  // ─── Auth Session helpers ─────────────────────────────────────────
  function getSession() {
    try { return JSON.parse(localStorage.getItem('merkle_session')); }
    catch (_) { return null; }
  }
  function setSession(data) {
    localStorage.setItem('merkle_session', JSON.stringify(data));
  }
  function clearSession() {
    localStorage.removeItem('merkle_session');
  }
  function requireAuth(role) {
    const s = getSession();
    if (!s || !s.token || s.role !== role) {
      clearSession();
      window.location.href = 'index.html';
      return false;
    }
    return true;
  }
  function populateUserInfo() {
    const s = getSession();
    if (!s) return;
    $$('[data-user-name]').forEach(el => el.textContent = s.name);
    $$('[data-user-id]').forEach(el => el.textContent = s.id);
    $$('[data-login-time]').forEach(el => el.textContent = s.login_time || 'Active Session');
  }

  // ─── Dropzone setup ───────────────────────────────────────────────
  function setFileLabel(dropzone, files) {
    const label = $('[data-file-label]', dropzone);
    if (!label) return;
    if (!files || files.length === 0) { label.textContent = 'No file selected'; return; }
    label.textContent = files.length === 1 ? files[0].name : files.length + ' files selected';
  }
  function setupDropzone(dropzone, input, onFiles) {
    if (!dropzone || !input) return;
    dropzone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => onFiles(input.files));
    dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
    dropzone.addEventListener('drop', e => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      onFiles(e.dataTransfer.files);
    });
  }

  // ─── Copy to clipboard ────────────────────────────────────────────
  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(
      () => showToast('Copied to clipboard'),
      () => showToast('Copy failed', 'error')
    );
  }
  window.copyToClipboard = copyToClipboard;

  // ─── Health check (shared across pages) ───────────────────────────
  async function checkHealth() {
    try {
      const data = await request('/api/health');
      $$('[data-health-status]').forEach(el => {
        const dot = $('.status-dot', el);
        const txt = el.lastElementChild;
        if (data.blockchain) {
          if (dot) dot.style.background = '#4ade80';
          if (txt) txt.textContent = 'Connected';
        } else {
          if (dot) dot.style.background = '#f87171';
          if (txt) txt.textContent = 'Disconnected';
        }
      });
      $$('[data-block-number]').forEach(el => el.textContent = data.block_number ?? '—');
      $$('[data-record-count]').forEach(el => el.textContent = data.record_count ?? '0');
      $$('[data-contract-addr]').forEach(el => el.textContent = formatAddress(data.contract_address, 14));
      $$('[data-chain-dot]').forEach(el => el.style.background = data.blockchain ? '#4ade80' : '#f87171');
      $$('[data-chain-status]').forEach(el => el.textContent = data.blockchain ? 'Connected' : 'Disconnected');

      try {
        const ipfs = await request('/api/ipfs-status');
        $$('[data-ipfs-badge]').forEach(el => {
          el.className = `ipfs-badge ${ipfs.mode === 'live_pinata' ? 'live' : 'sim'}`;
          el.textContent = ipfs.mode === 'live_pinata' ? 'IPFS: Pinata Cloud' : 'IPFS: Simulation';
          el.title = ipfs.message;
        });
        const statIpfs = $('#stat-ipfs');
        if (statIpfs) {
          statIpfs.textContent = ipfs.mode === 'live_pinata' ? 'Live (Pinata IPFS)' : 'Simulated IPFS';
          statIpfs.title = ipfs.message;
        }
      } catch (_) {}

      return data;
    } catch (_) { return null; }
  }

  // ─── IPFS Pill / Link Formatter ────────────────────────────────────
  function renderIpfsCell(r, isPublic = false) {
    const fileCount = r.file_count || (r.files ? r.files.length : 0);
    const stopProp = isPublic ? 'event.stopPropagation(); ' : '';
    if (fileCount > 1) {
      return `<button type="button" class="ipfs-pill" style="cursor:pointer;" onclick="${stopProp}window.viewDatasetFiles('${r.root}')" title="View all ${fileCount} dataset files on IPFS">📁 ${fileCount} Files ▾</button>`;
    }
    if (r.files && r.files.length === 1 && r.files[0].ipfs_url) {
      return `<a href="${r.files[0].ipfs_url}" target="_blank" class="ipfs-pill" ${isPublic ? 'onclick="event.stopPropagation()"' : ''} title="Open file on IPFS"><code>${formatHash(r.ipfs_cid || r.root, 11)}</code> ↗</a>`;
    }
    if (r.ipfs_cid) {
      return `<a href="${r.ipfs_gateway || ('https://gateway.pinata.cloud/ipfs/' + r.ipfs_cid)}" target="_blank" class="ipfs-pill" ${isPublic ? 'onclick="event.stopPropagation()"' : ''} title="View dataset on IPFS"><code>${formatHash(r.ipfs_cid, 11)}</code> ↗</a>`;
    }
    return '<span style="color:var(--muted)">—</span>';
  }

  // ─── Records table helper ─────────────────────────────────────────
  async function loadRecords(limit) {
    const tbody = $('#records-body');
    if (!tbody) return;
    try {
      const data = await request('/api/records');
      const table = tbody.closest('table');
      const thList = [...table.querySelectorAll('th')];
      const headers = thList.map(th => th.textContent.trim().toLowerCase());
      const hasIpfsCol = headers.some(h => h.includes('ipfs'));
      const hasSubmitterCol = headers.some(h => h.includes('submit') || h.includes('address'));
      const colCount = thList.length || 5;

      if (!data.records || data.records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${colCount}" class="table-empty">No on-chain audit records found.</td></tr>`;
        return;
      }
      let records = data.records;
      if (limit) records = records.slice(-limit).reverse();
      tbody.innerHTML = records.map(r => {
        const ipfsCell = hasIpfsCol ? `<td>${renderIpfsCell(r, false)}</td>` : '';
        const submitterCell = hasSubmitterCol ? `<td><code>${formatAddress(r.submitted_by)}</code></td>` : '';
        return `<tr>
          <td>${r.id}</td>
          <td><code>${formatHash(r.root)}</code></td>
          ${ipfsCell}
          <td>${r.version}</td>
          <td>${r.creator}</td>
          ${submitterCell}
          <td>${r.timestamp}</td>
        </tr>`;
      }).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" class="table-empty">${e.message}</td></tr>`;
    }
  }

  // ─── Page 1: Login (index.html) ───────────────────────────────────
  function initLogin() {
    const s = getSession();
    if (s && s.token) {
      window.location.href = s.role === 'company' ? 'company-home.html' : 'user-home.html';
      return;
    }

    function bindLoginForm(form, role) {
      if (!form) return;
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = $('button[type="submit"]', form);
        const username = $('input[name="username"]', form).value.trim();
        const password = $('input[name="password"]', form).value.trim();
        if (!username || !password) {
          showToast('Please provide both username and password', 'error');
          return;
        }
        await withLoading(btn, async () => {
          try {
            const data = await request('/api/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ username, password, role }),
            });
            setSession({
              token: data.token,
              id: data.id,
              name: data.name,
              role: data.role,
              login_time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            });
            showToast(`Signed in as ${data.name}`);
            setTimeout(() => {
              window.location.href = role === 'company' ? 'company-home.html' : 'user-home.html';
            }, 500);
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    }

    bindLoginForm($('#user-login-form'), 'user');
    bindLoginForm($('#company-login-form'), 'company');
  }

  // ─── Page 2: User Dashboard (user-home.html) ──────────────────────
  function initUserHome() {
    if (!requireAuth('user')) return;
    populateUserInfo();
    checkHealth();
    loadRecords(5);
  }

  // ─── Page 3: User Verification (user-verify.html) ─────────────────
  function initUserVerify() {
    if (!requireAuth('user')) return;
    populateUserInfo();
    checkHealth();

    const dropzone = $('[data-dropzone]');
    const input = $('#verify-file');
    const hashInput = $('#verify-hash-input');
    const dropzoneContainer = $('#dropzone-container');
    const hashInputContainer = $('#hash-input-container');
    const tabs = $$('[data-verify-tab]');

    let currentMode = 'file';
    let selectedFile = null;

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentMode = tab.dataset.verifyTab;
        if (currentMode === 'file') {
          if (dropzoneContainer) dropzoneContainer.hidden = false;
          if (hashInputContainer) hashInputContainer.hidden = true;
        } else {
          if (dropzoneContainer) dropzoneContainer.hidden = true;
          if (hashInputContainer) hashInputContainer.hidden = false;
          if (hashInput) hashInput.focus();
        }
      });
    });

    const useFiles = (files) => {
      selectedFile = files && files[0] ? files[0] : null;
      setFileLabel(dropzone, selectedFile ? [selectedFile] : []);
    };
    setupDropzone(dropzone, input, useFiles);

    const form = $('#verify-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = $('button[type="submit"]', form);
      const resultDiv = $('#verify-result');

      let fetchOptions;
      if (currentMode === 'file') {
        if (!selectedFile) {
          showToast('Please choose or drop a confidential file to verify.', 'error');
          return;
        }
        const fd = new FormData();
        fd.append('file', selectedFile);
        fetchOptions = { method: 'POST', body: fd };
      } else {
        const rawHash = (hashInput ? hashInput.value : '').trim();
        if (!rawHash) {
          showToast('Please enter a 64-character SHA-256 hash.', 'error');
          return;
        }
        let cleanHash = rawHash.toLowerCase();
        if (cleanHash.startsWith('0x')) cleanHash = cleanHash.slice(2);
        if (cleanHash.length !== 64 || !/^[0-9a-f]{64}$/.test(cleanHash)) {
          showToast('Invalid SHA-256 format (must be 64 hexadecimal characters).', 'error');
          return;
        }
        fetchOptions = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hash: cleanHash })
        };
      }

      await withLoading(btn, async () => {
        try {
          const data = await request('/api/verify', fetchOptions);
          resultDiv.hidden = false;

          if (data.verified && data.on_chain) {
            resultDiv.className = 'result-panel success';
            let proofHtml = '';
            if (data.proof && data.proof.length) {
              proofHtml = `<div class="hash-line"><strong>Merkle Proof Path:</strong></div>
                <div style="margin:6px 0 0 36px;font-size:11px;font-family:JetBrains Mono,monospace;">
                  ${data.proof.map((p, idx) => `<div>Step ${idx + 1}: ${p.direction.toUpperCase()} Sibling → <code>${formatHash(p.hash, 16)}</code></div>`).join('')}
                </div>`;
            }

            const unlockedStorageBox = data.ipfs_url ? `
              <div style="background:var(--sage);padding:14px;border-radius:8px;margin:14px 0;border:1px solid rgba(26,77,46,.18);">
                <div style="font-weight:600;font-size:12px;color:var(--forest);margin-bottom:6px;display:flex;align-items:center;gap:6px;">
                  <span>🔓</span> CONFIDENTIAL DECENTRALIZED STORAGE UNLOCKED
                </div>
                <p style="font-size:11px;color:var(--charcoal);margin:0 0 10px;line-height:1.4;">
                  Because you proved cryptographic possession of this record, your private IPFS file access has been unlocked.
                </p>
                <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                  <a href="${data.ipfs_url}" target="_blank" class="unlocked-pill">Open Verified File on IPFS ↗</a>
                  ${data.manifest_cid ? `<a href="https://violet-solid-ape-52.mypinata.cloud/ipfs/${data.manifest_cid}" target="_blank" class="btn-sm-outline" style="padding:5px 10px;font-size:11px;">View Merkle Manifest JSON ↗</a>` : ''}
                </div>
              </div>
            ` : '';

            resultDiv.innerHTML = `
              <div class="result-head"><span class="result-icon">✓</span> Verified & Anchored on Blockchain!</div>
              <p class="result-message">${data.message}</p>
              <div class="hash-line">Record Name: <strong>${data.matched_name || data.file_name}</strong></div>
              <div class="hash-line">File Hash (SHA-256): <code>${data.file_hash}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${data.file_hash}')">⧉</button></div>
              <div class="hash-line">Merkle Root: <code>${data.root}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${data.root}')">⧉</button></div>
              <div class="hash-line">Audited Dataset: <strong>${data.dataset_version}</strong> by <strong>${data.dataset_creator}</strong></div>
              ${unlockedStorageBox}
              <div class="hash-line">Proof Steps: ${data.proof_steps} cryptographic steps</div>
              ${data.record ? `<div class="hash-line">On-Chain Timestamp: ${data.record.timestamp} (Block mined)</div>` : ''}
              ${proofHtml}
              <div class="hash-line" style="margin-top:14px;"><a href="public.html" class="text-link">Inspect dataset tree in Public Explorer →</a></div>
            `;
            showToast('Record verified against public blockchain!', 'success');
          } else if (data.verified) {
            resultDiv.className = 'result-panel warning';
            resultDiv.innerHTML = `
              <div class="result-head"><span class="result-icon" style="background:#f59e0b">✓</span> Verified in Local Dataset (Pending Blockchain Anchor)</div>
              <p class="result-message">${data.message}</p>
              <div class="hash-line">Record SHA-256: <code>${data.file_hash}</code></div>
              <div class="hash-line">Root: <code>${data.root}</code></div>
            `;
            showToast('Found in local dataset.', 'info');
          } else {
            resultDiv.className = 'result-panel failure';
            resultDiv.innerHTML = `
              <div class="result-head"><span class="result-icon">✗</span> Record Not Found in Any Audited Dataset</div>
              <p class="result-message">${data.message}</p>
              <div class="hash-line">Fingerprint: <code>${data.file_hash}</code></div>
              <div class="hash-line">This record is not part of any dataset registered on the ledger.</div>
            `;
            showToast('Verification failed: Record not in registry.', 'error');
          }
        } catch (err) {
          resultDiv.hidden = false;
          resultDiv.className = 'result-panel error';
          resultDiv.innerHTML = `<div class="result-head"><span class="result-icon">✗</span> Error</div><p class="result-message">${err.message}</p>`;
          showToast(err.message, 'error');
        }
      });
    });
  }

  // ─── Page 4: Company Dashboard (company-home.html) ────────────────
  function initCompanyHome() {
    if (!requireAuth('company')) return;
    populateUserInfo();
    checkHealth();
    loadRecords();
    const refreshBtn = $('#refresh-records');
    if (refreshBtn) refreshBtn.addEventListener('click', () => loadRecords());
  }

  // ─── Page 5: Company Upload (company-upload.html) ─────────────────
  function initCompanyUpload() {
    if (!requireAuth('company')) return;
    populateUserInfo();
    checkHealth();

    let currentRoot = null;
    let currentIpfsCid = null;
    let currentIpfsGateway = null;
    const dropzone = $('[data-dropzone]');
    const input = $('#dataset-files');
    let selectedFiles = null;

    const useFiles = (files) => {
      selectedFiles = files && files.length > 0 ? files : null;
      setFileLabel(dropzone, selectedFiles ? [...selectedFiles] : []);
    };
    setupDropzone(dropzone, input, useFiles);

    const processUpload = async () => {
      if (!selectedFiles || selectedFiles.length === 0) return;
      const fd = new FormData();
      for (const f of selectedFiles) fd.append('files', f);
      try {
        const data = await request('/api/hash-dataset', { method: 'POST', body: fd });
        currentRoot = data.root;
        currentIpfsCid = data.ipfs_cid;
        currentIpfsGateway = data.ipfs_gateway;
        const rootCode = $('#submit-root-value');
        if (rootCode) rootCode.textContent = formatHash(data.root, 22);
        const ipfsCode = $('#submit-ipfs-value');
        if (ipfsCode) ipfsCode.textContent = formatHash(data.ipfs_cid, 22);

        const resultDiv = $('#dataset-result');
        if (resultDiv) {
          resultDiv.hidden = false;
          resultDiv.innerHTML = `
            <div class="dataset-summary">
              <div class="root-display">
                <span>MERKLE ROOT</span>
                <code>${data.root}</code>
                <button class="copy-button" type="button" onclick="copyToClipboard('${data.root}')">⧉</button>
              </div>
              <div class="metric"><span>TOTAL FILES</span><strong>${data.file_count}</strong></div>
              <div class="metric"><span>TREE LEVELS</span><strong>${data.tree_levels}</strong></div>
              <div class="metric"><span>ALGORITHM</span><strong>SHA-256</strong></div>
            </div>

            <div class="ipfs-card">
              <div class="ipfs-card-head">
                <strong><span style="color:var(--forest)">◈</span> HYBRID DECENTRALIZED STORAGE (IPFS)</strong>
                <span class="ipfs-badge ${data.ipfs_mode === 'live_pinata' ? 'live' : 'sim'}">${data.ipfs_mode === 'live_pinata' ? 'Live Pinata Pinned' : 'Simulated IPFS Mode'}</span>
              </div>
              <div class="ipfs-grid">
                <div class="ipfs-item">
                  <span>Dataset Directory CID</span>
                  <code>${data.ipfs_cid || '—'}</code>
                </div>
                <div class="ipfs-item">
                  <span>Merkle Audit Manifest CID</span>
                  <code>${data.manifest_cid || '—'}</code>
                </div>
              </div>
              <div class="ipfs-actions">
                ${data.ipfs_gateway ? `<a href="${data.ipfs_gateway}" target="_blank" class="btn-sm-outline">Open Dataset on IPFS Gateway ↗</a>` : ''}
                ${data.manifest_gateway ? `<a href="${data.manifest_gateway}" target="_blank" class="btn-sm-outline">View Merkle Manifest JSON ↗</a>` : ''}
              </div>
            </div>

            ${data.tree ? `
              <div class="tree-wrap">
                <div class="tree-title"><span>MERKLE TREE PREVIEW</span><span>${data.tree_levels} LEVELS</span></div>
                <div class="merkle-tree">
                  ${data.tree.slice().reverse().map(level => `
                    <div class="tree-level">
                      ${level.nodes.map(n => `<div class="tree-node"><code>${n}</code></div>`).join('')}
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}
            <div class="file-list">
              <div class="file-list-header"><span>DATASET FILES INGESTED</span><span>${data.file_count} files</span></div>
              <ul>
                ${data.files.map(f => `
                  <li>
                    <span>${f.name}</span>
                    <div style="display:flex;align-items:center;gap:8px;">
                      <code>${f.hash}</code>
                      ${f.ipfs_url ? `<a href="${f.ipfs_url}" target="_blank" class="ipfs-pill" style="font-size:10px;">Open on IPFS ↗</a>` : ''}
                    </div>
                  </li>
                `).join('')}
              </ul>
            </div>
          `;
        }
        showToast(`Dataset hashed & pinned to IPFS (${data.file_count} files)`);
      } catch (err) {
        showToast(err.message, 'error');
      }
    };

    input.addEventListener('change', processUpload);
    dropzone.addEventListener('drop', () => setTimeout(processUpload, 100));

    // Submit to blockchain
    const submitForm = $('#submit-form');
    if (submitForm) {
      submitForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!currentRoot) {
          showToast('Please upload and hash a dataset before anchoring.', 'error');
          return;
        }
        const btn = $('button[type="submit"]', submitForm);
        const version = $('input[name="version"]', submitForm).value.trim() || 'v1.0';
        const creator = $('input[name="creator"]', submitForm).value.trim() || getSession()?.name || 'Acme AI Labs';

        await withLoading(btn, async () => {
          try {
            const data = await request('/api/submit-root', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                root: currentRoot,
                version,
                creator,
                ipfs_cid: currentIpfsCid,
                ipfs_gateway: currentIpfsGateway,
              }),
            });
            const resultDiv = $('#submit-result');
            if (resultDiv) {
              resultDiv.hidden = false;
              resultDiv.className = 'result-panel success';
              resultDiv.innerHTML = `
                <div class="result-head"><span class="result-icon">✓</span> Successfully Anchored On-Chain!</div>
                <p class="result-message">The Merkle root and off-chain IPFS storage hash are permanently anchored.</p>
                <div class="hash-line">Transaction Hash: <code>${data.tx_hash}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${data.tx_hash}')">⧉</button></div>
                <div class="hash-line">Block Number: <strong>${data.block_number}</strong></div>
                <div class="hash-line">Dataset Version: <strong>${data.version}</strong> by <strong>${data.creator}</strong></div>
                ${data.ipfs_cid ? `<div class="hash-line">IPFS Decentralized Storage: <a href="${data.ipfs_gateway || ('https://gateway.pinata.cloud/ipfs/' + data.ipfs_cid)}" target="_blank" class="ipfs-pill"><code>${formatHash(data.ipfs_cid, 20)}</code> ↗ (Pinned on IPFS)</a></div>` : ''}
              `;
            }
            showToast('Root anchored on Ethereum blockchain!');
            loadRecords();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    }

    loadRecords();
    const refreshBtn = $('#refresh-records');
    if (refreshBtn) refreshBtn.addEventListener('click', () => loadRecords());
  }

  // ─── Page 6: Public Explorer (public.html) ────────────────────────
  function initPublic() {
    checkHealth();
    loadPublicOverview();
    const refreshBtn = $('#refresh-public');
    if (refreshBtn) refreshBtn.addEventListener('click', loadPublicOverview);
  }

  async function loadPublicOverview() {
    try {
      const data = await request('/api/public-overview');

      // Update stat cards
      const statAudits = $('#stat-audits');
      if (statAudits) statAudits.textContent = data.record_count ?? '0';

      const statAddress = $('#stat-address');
      if (statAddress) {
        statAddress.textContent = data.contract_address ? formatAddress(data.contract_address, 14) : 'Not deployed';
        if (data.contract_address) {
          statAddress.onclick = () => copyToClipboard(data.contract_address);
        }
      }

      const statBlock = $('#stat-block');
      if (statBlock) statBlock.textContent = data.block_number ?? '0';

      const statIpfs = $('#stat-ipfs');
      if (statIpfs) {
        statIpfs.textContent = 'Confidential (Pinata IPFS)';
      }

      // Populate dataset selector
      const selector = $('#dataset-selector');
      if (selector && data.records) {
        selector.innerHTML = data.records.map(r =>
          `<option value="${r.root}">Record #${r.id} — ${r.version} (${r.creator})</option>`
        ).join('') || '<option value="">No datasets registered yet</option>';

        selector.onchange = async () => {
          if (!selector.value) return;
          try {
            const treeData = await request(`/api/tree/${selector.value}`);
            renderPublicTree(treeData);
          } catch (_) {}
        };
      }

      // Render latest tree
      if (data.latest_tree) {
        renderPublicTree({
          root: data.latest_root,
          version: data.records && data.records.length ? data.records[data.records.length - 1].version : 'v1.0',
          file_count: data.latest_files ? data.latest_files.length : 0,
          tree: data.latest_tree,
        });
      } else {
        const treeDetail = $('#tree-detail');
        if (treeDetail) treeDetail.innerHTML = '<div class="table-empty">No active Merkle trees recorded on-chain yet.</div>';
      }

      // Populate public records ledger
      const tbody = $('#public-records-body');
      if (tbody && data.records) {
        if (data.records.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" class="table-empty">No records on-chain.</td></tr>';
        } else {
          tbody.innerHTML = data.records.map(r => `
            <tr style="cursor:pointer;" onclick="document.querySelector('#dataset-selector').value='${r.root}'; document.querySelector('#dataset-selector').dispatchEvent(new Event('change'));">
              <td><strong>#${r.id}</strong></td>
              <td><code>${formatHash(r.root)}</code></td>
              <td><span class="privacy-pill">🔒 Private Off-Chain</span></td>
              <td>${r.version}</td>
              <td>${r.creator}</td>
              <td><code>${formatAddress(r.submitted_by)}</code></td>
              <td>${r.timestamp}</td>
            </tr>
          `).join('');
        }
      }
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  function renderPublicTree(treeObj) {
    const treeDetail = $('#tree-detail');
    if (!treeDetail || !treeObj || !treeObj.tree) return;

    treeDetail.innerHTML = `
      <div class="tree-wrap" style="border-top:none;padding-top:0;">
        <div class="tree-title" style="margin-bottom:12px;">
          <span>Root: <code>${formatHash(treeObj.root, 24)}</code></span>
          <span>${treeObj.tree.length} Cryptographic Levels</span>
        </div>
        <div class="merkle-tree">
          ${treeObj.tree.slice().reverse().map((level, idx) => `
            <div class="tree-level">
              ${level.nodes.map(n => `<div class="tree-node" title="Click to copy full node hash" onclick="copyToClipboard('${n}')"><code>${n}</code></div>`).join('')}
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // ─── Interactive Dataset Files Modal ──────────────────────────────
  window.closeDatasetModal = function() {
    const m = document.getElementById('dataset-files-modal');
    if (m) m.classList.remove('open');
  };

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') window.closeDatasetModal();
  });

  window.viewDatasetFiles = async function(rootHex) {
    let modal = document.getElementById('dataset-files-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'dataset-files-modal';
      modal.className = 'modal-backdrop';
      modal.innerHTML = `
        <div class="modal-box">
          <div class="modal-head">
            <strong id="modal-dataset-title">Dataset Files (IPFS)</strong>
            <button type="button" class="copy-button" onclick="window.closeDatasetModal()" style="font-size:16px;cursor:pointer;padding:4px 8px;">✕</button>
          </div>
          <div class="modal-body" id="modal-dataset-body">
            <div class="table-empty">Loading dataset files...</div>
          </div>
        </div>
      `;
      modal.addEventListener('click', (e) => {
        if (e.target === modal) window.closeDatasetModal();
      });
      document.body.appendChild(modal);
    }

    const titleEl = document.getElementById('modal-dataset-title');
    const bodyEl = document.getElementById('modal-dataset-body');
    if (titleEl) titleEl.textContent = 'Dataset Files (IPFS)';
    if (bodyEl) bodyEl.innerHTML = '<div class="table-empty">Loading dataset files from IPFS registry...</div>';
    modal.classList.add('open');

    try {
      const data = await request(`/api/tree/${rootHex}`);
      const files = data.files || [];
      if (titleEl) {
        titleEl.innerHTML = `<span>Dataset Files</span> <span style="font-size:12px;font-weight:normal;color:var(--forest);background:var(--sage);padding:2px 8px;border-radius:4px;margin-left:8px;">${data.version || 'v1.0'} (${files.length} files)</span>`;
      }

      let ipfsInfoHtml = '';
      if (data.ipfs_cid) {
        ipfsInfoHtml = `
          <div style="background:var(--sage);padding:10px 14px;border-radius:6px;margin-bottom:14px;display:flex;flex-direction:column;gap:6px;font-size:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
              <span style="color:var(--muted);font-family:'JetBrains Mono',monospace;">IPFS FOLDER CID:</span>
              <code>${formatHash(data.ipfs_cid, 22)}</code>
            </div>
            ${data.manifest_cid ? `
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
              <span style="color:var(--muted);font-family:'JetBrains Mono',monospace;">MERKLE MANIFEST:</span>
              <a href="https://violet-solid-ape-52.mypinata.cloud/ipfs/${data.manifest_cid}" target="_blank" class="ipfs-pill" style="font-size:11px;">View Manifest JSON ↗</a>
            </div>` : ''}
          </div>
        `;
      }

      if (files.length === 0) {
        bodyEl.innerHTML = `${ipfsInfoHtml}<div class="table-empty">No individual files recorded in this dataset registry.</div>`;
        return;
      }

      bodyEl.innerHTML = `
        ${ipfsInfoHtml}
        <div style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em;">
          Files Ingested & Cryptographically Anchored (${files.length})
        </div>
        <ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px;">
          ${files.map((f, idx) => `
            <li style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--sage);border-radius:6px;border:1px solid rgba(26,77,46,0.12);gap:12px;flex-wrap:wrap;">
              <div style="min-width:0;flex:1;">
                <div style="font-weight:600;font-size:13px;color:var(--charcoal);word-break:break-all;">${f.name}</div>
                <div style="font-size:10px;font-family:'JetBrains Mono',monospace;color:var(--muted);margin-top:2px;">
                  SHA-256: <code>${f.full_hash ? formatHash(f.full_hash, 16) : (f.hash || '—')}</code>
                  <button type="button" class="copy-button" style="padding:1px 4px;font-size:10px;" onclick="copyToClipboard('${f.full_hash || f.hash}')">⧉</button>
                </div>
              </div>
              <div>
                ${f.ipfs_url ? `<a href="${f.ipfs_url}" target="_blank" class="btn-sm-outline" style="padding:4px 10px;font-size:11px;white-space:nowrap;">Open on IPFS ↗</a>` : ''}
              </div>
            </li>
          `).join('')}
        </ul>
      `;
    } catch (err) {
      bodyEl.innerHTML = `<div class="table-empty" style="color:var(--error);">${err.message || 'Error loading files'}</div>`;
    }
  };

  // ─── Setup Logout Button ──────────────────────────────────────────
  function setupLogout() {
    window.logout = function () {
      clearSession();
      window.location.href = 'index.html';
    };
    $$('#logout-btn, .logout-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        try { await request('/api/logout', { method: 'POST' }); } catch (_) {}
        clearSession();
        showToast('Logged out');
        setTimeout(() => { window.location.href = 'index.html'; }, 200);
      });
    });
  }

  // ─── Main Router ──────────────────────────────────────────────────
  function init() {
    const body = document.body;
    setupLogout();

    if (body.classList.contains('login-page')) {
      initLogin();
    } else if (body.dataset.requireAuth) {
      const path = window.location.pathname;
      if (path.includes('user-home')) initUserHome();
      else if (path.includes('user-verify')) initUserVerify();
      else if (path.includes('company-home')) initCompanyHome();
      else if (path.includes('company-upload')) initCompanyUpload();
      else {
        // Fallback check by body classes
        if (body.classList.contains('user-page')) initUserHome();
        else if (body.classList.contains('company-page')) initCompanyHome();
      }
    } else if (body.classList.contains('public-page')) {
      initPublic();
    } else {
      checkHealth();
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
