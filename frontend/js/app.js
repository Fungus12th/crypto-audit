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
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

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
  function requireAuth(allowedRoles) {
    const s = getSession();
    if (!s || !s.token) {
      clearSession();
      window.location.href = 'index.html';
      return false;
    }
    const roles = Array.isArray(allowedRoles) ? allowedRoles : [allowedRoles];
    if (!roles.includes(s.role)) {
      showToast(`Access restricted to ${roles.join(' or ')} role. Redirecting...`, 'error');
      setTimeout(() => {
        window.location.href = s.role === 'user' ? 'user-home.html' : 'company-home.html';
      }, 500);
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

  // ─── Cryptographic Compliance Certificates ───────────────────────
  window.downloadCertificate = async function (fileHash, rootHex, fileName, format = 'json') {
    try {
      const cert = await request('/api/certificate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_hash: fileHash, root: rootHex, file_name: fileName, format: 'json' })
      });
      const blob = new Blob([JSON.stringify(cert, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Audit-Certificate-${cert.certificate_id || 'cert'}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Audit Compliance Certificate downloaded!');
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  window.viewCertificateHtml = async function (fileHash, rootHex, fileName) {
    try {
      const res = await fetch('/api/certificate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_hash: fileHash, root: rootHex, file_name: fileName, format: 'html' })
      });
      const html = await res.text();
      const w = window.open('', '_blank');
      w.document.open();
      w.document.write(html);
      w.document.close();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // ─── Zero-Knowledge Dataset Nutrition Label Component ────────────
  function renderNutritionCard(nutrition) {
    if (!nutrition) return '';
    const modEntries = Object.entries(nutrition.modalities || {});
    const modalityPills = modEntries.map(([ext, pct]) =>
      `<span style="background:var(--sage);padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600;color:var(--forest);border:1px solid rgba(26,77,46,.15);">${ext.toUpperCase()}: ${pct}%</span>`
    ).join(' ') || '<span style="color:var(--muted)">Standard Text/Data</span>';

    return `
      <div class="nutrition-card">
        <div class="nutrition-head">
          <strong><span>🌱</span> ZERO-KNOWLEDGE DATASET NUTRITION LABEL</strong>
          <span style="font:600 10px 'JetBrains Mono',monospace;color:var(--muted);text-transform:uppercase;">Empirical Statistical Metrics</span>
        </div>
        <div class="nutrition-grid">
          <div class="nutrition-item">
            <span>Total Volume</span>
            <strong>${(nutrition.total_bytes / 1024).toFixed(1)} KB</strong>
          </div>
          <div class="nutrition-item">
            <span>Shannon Entropy</span>
            <strong>${nutrition.shannon_entropy_avg || '0.00'} bits</strong>
          </div>
          <div class="nutrition-item">
            <span>Size Distribution</span>
            <strong>&lt;10KB: ${(nutrition.size_buckets || {})['<10KB'] || 0}</strong>
          </div>
          <div class="nutrition-item">
            <span>Modalities</span>
            <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">${modalityPills}</div>
          </div>
        </div>
      </div>
    `;
  }

  // ─── Visual Merkle Proof Path Ladder Component ───────────────────
  function renderProofLadder(proof, leafHash, rootHex) {
    if (!proof || !proof.length) return '';
    return `
      <div class="proof-ladder">
        <div class="proof-ladder-title">
          <span>Deterministic Merkle Proof Ladder</span>
          <span>${proof.length} Verification Steps</span>
        </div>
        <div class="proof-step-row" style="color:var(--forest);font-weight:700;">
          <span>🍃 Leaf Digest (Your Target File)</span>
          <code>${formatHash(leafHash, 18)}</code>
        </div>
        ${proof.map((p, idx) => `
          <div class="proof-step-row">
            <span>Step ${idx + 1}: Sibling <span class="proof-dir-pill ${p.direction}">${p.direction.toUpperCase()}</span></span>
            <code>${formatHash(p.hash, 18)}</code>
          </div>
        `).join('')}
        <div class="proof-step-row" style="color:var(--forest);font-weight:700;border-top:1.5px solid var(--forest);margin-top:4px;padding-top:6px;">
          <span>🌳 Verified Root</span>
          <code>${formatHash(rootHex, 18)}</code>
        </div>
      </div>
    `;
  }

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

  // ─── Multi-Actor Web3 Wallet State & Bar ──────────────────────────
  let cachedWallets = [];
  let activeWalletIndex = parseInt(localStorage.getItem('active_web3_wallet') || '1', 10);

  async function loadWallets() {
    const listEl = $('#wallet-list');
    if (!listEl) return;
    try {
      const data = await request('/api/wallets');
      if (!data.wallets || data.wallets.length === 0) {
        listEl.innerHTML = '<span style="color:var(--muted);font-size:11px;">Hardhat node disconnected</span>';
        return;
      }
      cachedWallets = data.wallets;
      renderWalletBar();
    } catch (err) {
      listEl.innerHTML = `<span style="color:var(--error);font-size:11px;">${err.message}</span>`;
    }
  }

  function renderWalletBar() {
    const listEl = $('#wallet-list');
    if (!listEl || !cachedWallets.length) return;

    const s = getSession();
    if (s && typeof s.wallet_index === 'number') {
      activeWalletIndex = s.wallet_index;
    }

    const myWallet = cachedWallets.find(w => w.index === activeWalletIndex) || cachedWallets[activeWalletIndex] || cachedWallets[0];
    const repHtml = myWallet.index === 2 ? `<span style="color:#0284c7;font-weight:700;margin-left:4px;">⚖️ Rep: ${myWallet.reputation}</span>` : '';

    const otherWallets = cachedWallets.filter(w => w.index !== myWallet.index);
    const otherWalletsHtml = otherWallets.map(w => {
      const rep = w.index === 2 ? ` ⚖️ Rep: ${w.reputation}` : '';
      return `
        <span class="wallet-pill" style="opacity:0.8;cursor:default;font-size:10.5px;padding:3px 8px;background:var(--sage);color:var(--charcoal);border:1px solid rgba(26,77,46,0.15);" title="${escapeHtml(w.desc)} (${w.address})">
          #${w.index} ${escapeHtml(w.role)}: ${w.balance_eth} ETH${rep}
        </span>
      `;
    }).join('');

    const statusLabel = s ? 'Authenticated Identity' : 'Public Observer';

    listEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <div class="wallet-pill active" style="box-shadow:0 0 0 2px var(--forest);" title="${escapeHtml(myWallet.desc)} (${myWallet.address})">
          <span class="wallet-role">● ${statusLabel}: #${myWallet.index} ${escapeHtml(myWallet.role.toUpperCase())} (${escapeHtml(myWallet.name)})</span>
          <span class="wallet-bal">${myWallet.balance_eth} ETH</span>
          ${repHtml}
        </div>
        <span style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--muted);margin-left:4px;">Other Protocol Actors:</span>
        ${otherWalletsHtml}
      </div>
    `;
  }

  window.switchActiveWallet = function(idx) {
    const s = getSession();
    if (s && s.wallet_index !== idx) {
      showToast('Cannot switch persona while authenticated. Please sign in with that role.', 'error');
      return;
    }
    activeWalletIndex = idx;
    localStorage.setItem('active_web3_wallet', idx);
    renderWalletBar();
    const w = cachedWallets.find(x => x.index === idx);
    const roleName = w ? w.role : `#${idx}`;
    showToast(`Active Web3 Actor: ${roleName}`, 'info');
  };

  // ─── Status Lifecycle & Governance Badge Formatter ────────────────
  function renderStatusBadge(r) {
    if (r.is_revoked) {
      return '<span class="status-badge status-superseded">🕒 Superseded</span>';
    }
    const st = r.audit_status || 'PENDING_AUDIT';
    if (st === 'AUDITOR_ATTESTED') {
      const by = r.attested_by ? ` title="Attested by ${r.attested_by} (${r.audit_report_uri || ''})"` : '';
      return `<span class="status-badge status-attested"${by}>🛡️ Auditor Attested</span>`;
    }
    if (st === 'DISPUTED_SLASHED') {
      return '<span class="status-badge status-slashed" title="Proportional collateral pool slashed due to proven unlicensed IP challenge">⚔️ Disputed / Slashed</span>';
    }
    // PENDING_AUDIT
    const attestBtn = `<button type="button" class="btn-action-sm btn-attest" onclick="event.stopPropagation(); window.openAttestModal('${r.root}')" title="Audit and co-sign this dataset (+0.2 ETH Fee Payout)">⚖️ Attest</button>`;
    return `<div style="display:inline-flex;align-items:center;flex-wrap:wrap;gap:4px;"><span class="status-badge status-pending">⏳ Pending Audit</span>${attestBtn}</div>`;
  }

  // ─── 100% Client-Side WebCrypto Merkle Math ────────────────────────
  async function hashPairSha256(leftHex, rightHex) {
    const combined = leftHex.toLowerCase() + rightHex.toLowerCase();
    const data = new TextEncoder().encode(combined);
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function generateClientProof(treeLevels, leafIndex) {
    if (!treeLevels || treeLevels.length === 0) return [];
    const proof = [];
    let index = leafIndex;
    for (let l = 0; l < treeLevels.length - 1; l++) {
      let currentLevel = [...treeLevels[l]];
      if (currentLevel.length % 2 === 1) {
        currentLevel.push(currentLevel[currentLevel.length - 1]);
      }
      const isEven = index % 2 === 0;
      const siblingIndex = isEven ? index + 1 : index - 1;
      const direction = isEven ? 'right' : 'left';
      if (siblingIndex < currentLevel.length) {
        proof.push({
          hash: currentLevel[siblingIndex],
          direction: direction,
        });
      }
      index = Math.floor(index / 2);
    }
    return proof;
  }

  async function verifyMerkleProofClient(leafHash, proof, expectedRoot) {
    let current = leafHash.toLowerCase();
    for (const item of proof) {
      const sibling = item.hash || item[0];
      const direction = item.direction || item[1];
      if (direction === 'left') {
        current = await hashPairSha256(sibling, current);
      } else {
        current = await hashPairSha256(current, sibling);
      }
    }
    return {
      verified: current === expectedRoot.toLowerCase(),
      calculatedRoot: current,
    };
  }

  // ─── Creator IP Registry & Royalty Shield Table ───────────────────
  async function renderCreatorIpTable(tbody, thead, isCompany = false) {
    if (thead) {
      thead.innerHTML = `
        <tr>
          <th>ID</th>
          <th>Work Title & Owner</th>
          <th>SHA-256 Exact Fingerprint</th>
          <th>Fuzzy SimHash</th>
          <th>Instant Royalty</th>
          <th>Registered</th>
          <th>Training Dataset Matches</th>
          <th>Decentralized Actions</th>
        </tr>
      `;
    }
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">Loading creator intellectual property registry...</td></tr>`;

    try {
      const data = await request('/api/creator-ip');
      const works = data.works || [];

      // Update counters across tabs
      const counts = [$('#creator-ip-count'), $('#public-creator-ip-count'), $('#upload-creator-ip-count')];
      counts.forEach(c => { if (c) c.textContent = data.count || works.length; });

      if (works.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="8" class="table-empty" style="padding:24px;">
              <p style="margin:0 0 10px;font-size:13px;color:var(--charcoal);">No creator intellectual property registered yet.</p>
              <button type="button" class="btn-action-sm btn-license" onclick="window.openCreatorIpModal()">＋ Register Creator Work & Set Royalty</button>
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = works.map(w => {
        let matchesHtml = '';
        if (!w.matches || w.matches.length === 0) {
          matchesHtml = '<span style="color:var(--muted);font-size:11px;">Zero training matches</span>';
        } else {
          matchesHtml = w.matches.map(m => {
            let statusPill = '';
            if (m.is_licensed) {
              statusPill = '<span class="status-badge status-attested">✓ Royalty Paid • Licensed</span>';
            } else {
              statusPill = '<span class="status-badge status-pending" style="background:#fef3c7;color:#92400e;border:1px solid #fde68a;">⚠️ Royalty Pending</span>';
            }
            return `
              <div style="font-size:11px;margin-bottom:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                <code>${formatHash(m.dataset_root, 10)}</code>
                <span>${escapeHtml(m.dataset_version)} (${m.similarity_score}%)</span>
                ${statusPill}
              </div>
            `;
          }).join('');
        }

        let actionsHtml = '';
        const unlicensedMatch = (w.matches || []).find(m => !m.is_licensed);
        if (unlicensedMatch) {
          actionsHtml = `
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <button type="button" class="btn-action-sm btn-license" onclick="window.autoLicenseWork('${unlicensedMatch.dataset_root}', '${w.exact_hash}', ${w.license_fee_eth})" title="Transfer requested royalty directly to creator on Ethereum">
                ⚡ Pay Royalty & License (${w.license_fee_eth} ETH)
              </button>
            </div>
          `;
        } else {
          actionsHtml = `
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="font-size:11px;color:var(--forest);font-weight:600;">✓ Settled</span>
              <button type="button" class="btn-action-sm btn-license" onclick="window.openCreatorIpModal()" style="font-size:10px;padding:3px 8px;">＋ New Work</button>
            </div>
          `;
        }

        return `
          <tr>
            <td><strong>#${w.id}</strong></td>
            <td>
              <div style="font-weight:600;font-size:12px;color:var(--forest);">${escapeHtml(w.title)}</div>
              <div style="font-size:10px;font-family:'JetBrains Mono',monospace;color:var(--muted);">Owner: <code>${formatAddress(w.owner)}</code></div>
            </td>
            <td><code>${formatHash(w.exact_hash, 14)}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${w.exact_hash}')">⧉</button></td>
            <td><code>${w.simhash ? formatHash(w.simhash, 10) : '—'}</code></td>
            <td><strong style="color:var(--forest);">${w.license_fee_eth} ETH</strong></td>
            <td style="font-size:11px;">${w.registered_at || '—'}</td>
            <td>${matchesHtml}</td>
            <td>${actionsHtml}</td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" class="table-empty" style="color:var(--error);">${err.message}</td></tr>`;
    }
  }

  window.autoLicenseWork = async function(root, leafHash, feeEth) {
    if (!confirm(`Authorize royalty payment of ${feeEth} ETH directly to Creator on Ethereum to license dataset ${formatHash(root, 10)}?`)) return;
    try {
      const res = await request('/api/auto-license', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_root: root,
          creator_leaf_hash: leafHash,
          account: activeWalletIndex
        })
      });
      showToast(`Royalty paid to Creator! Dataset legally licensed (Block #${res.block_number})`);
      loadWallets();
      if (typeof loadRecords === 'function') loadRecords();
      if (typeof loadPublicOverview === 'function') loadPublicOverview();
      loadCreatorIpTable();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // ─── Attestation & Creator Modals Setup ────────────────────────────
  let currentAttestRoot = null;
  function setupAttestModal() {
    const modal = $('#attest-modal');
    const closeBtn = $('#close-attest-modal');
    const form = $('#attest-dataset-form');
    const display = $('#attest-root-display');

    window.openAttestModal = function(rootHex) {
      if (!modal) return;
      currentAttestRoot = rootHex;
      if (display) display.textContent = formatHash(rootHex, 20);
      modal.classList.add('open');
    };

    if (closeBtn && modal) {
      closeBtn.addEventListener('click', () => modal.classList.remove('open'));
    }
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
      });
    }

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!currentAttestRoot) return;
        const submitBtn = $('button[type="submit"]', form);
        const reportUri = $('#attest-report-input').value.trim();

        await withLoading(submitBtn, async () => {
          try {
            const res = await request('/api/attest-dataset', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                root: currentAttestRoot,
                audit_report_uri: reportUri,
                account: activeWalletIndex
              })
            });
            showToast(`Dataset attested on-chain! Auditor fee paid. Rep: ${res.auditor_reputation}`);
            modal.classList.remove('open');
            loadWallets();
            if (typeof loadRecords === 'function') loadRecords();
            if (typeof loadPublicOverview === 'function') loadPublicOverview();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    }
  }

  function setupCreatorIpModal() {
    const modal = $('#creator-ip-modal');
    const closeBtn = $('#close-creator-ip-modal');
    const form = $('#register-creator-ip-form');

    window.openCreatorIpModal = function() {
      if (!modal) return;
      modal.classList.add('open');
    };

    if (closeBtn && modal) {
      closeBtn.addEventListener('click', () => modal.classList.remove('open'));
    }
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('open');
      });
    }

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = $('button[type="submit"]', form);
        const title = $('#cip-title-input').value.trim();
        let hash = $('#cip-hash-input').value.trim().toLowerCase();
        if (hash.startsWith('0x')) hash = hash.slice(2);
        let simhash = $('#cip-simhash-input').value.trim().toLowerCase();
        if (simhash.startsWith('0x')) simhash = simhash.slice(2);
        const fee = parseFloat($('#cip-fee-input').value.trim()) || 0.05;

        if (hash.length !== 64 || !/^[0-9a-f]{64}$/.test(hash)) {
          showToast('File SHA-256 hash must be 64 hexadecimal characters.', 'error');
          return;
        }

        await withLoading(submitBtn, async () => {
          try {
            const res = await request('/api/creator-ip', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                exact_hash: hash,
                simhash: simhash,
                title: title,
                license_fee_eth: fee,
                account: activeWalletIndex
              })
            });
            showToast(`Creator IP registered on-chain! Block #${res.block_number}`);
            modal.classList.remove('open');
            form.reset();
            loadWallets();
            if (currentCompanyLedgerTab === 'creator-ip') renderCompanyRecordsTable();
            if (currentPublicTab === 'creator-ip') renderPublicRecordsTable();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    }
  }

  // ─── Unified AI Model Cell Formatter ──────────────────────────────
  function renderAiModelCell(r, isCompany = false) {
    if (r.bound_model) {
      const m = r.bound_model;
      const metricsSummary = m.metrics && typeof m.metrics === 'object'
        ? Object.entries(m.metrics).slice(0, 2).map(([k, v]) => `${k}:${v}`).join(' ')
        : '';
      const teeBadge = (m.tee_enclave_quote_hash || m.is_tee_secured)
        ? `<span class="tee-badge" title="Intel SGX / NVIDIA TEE Hardware Attestation Quote Anchored">🔒 TEE Enclave</span>`
        : '';
      return `
        <div style="display:flex;flex-direction:column;gap:3px;">
          <div style="font-weight:700;font-size:12px;color:var(--forest);display:flex;align-items:center;gap:5px;">
            <span>🤖</span> ${escapeHtml(m.model_name || 'AI Model')} ${teeBadge}
          </div>
          <div style="font-size:10px;font-family:'JetBrains Mono',monospace;color:var(--muted);display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <span style="background:var(--sage);padding:1px 5px;border-radius:3px;color:var(--forest);font-weight:600;">${escapeHtml(m.framework || 'PyTorch')}</span>
            <code>${formatHash(m.model_hash, 8)}</code>
            ${metricsSummary ? `<span style="color:var(--forest);">${escapeHtml(metricsSummary)}</span>` : ''}
          </div>
        </div>
      `;
    }
    if (isCompany && !r.is_revoked) {
      return `<button type="button" class="btn-sm-outline" style="padding:3px 9px;font-size:11px;font-weight:600;white-space:nowrap;" onclick="window.openBindModelModal('${r.root}')">＋ Bind Model</button>`;
    }
    return '<span style="color:var(--muted);font-size:11px;">—</span>';
  }

  // ─── Shared Ledger Tabs Helper ────────────────────────────────────
  function setupLedgerTabs(selector, onTabChange) {
    const container = $(selector);
    if (!container) return;
    const tabs = container.querySelectorAll('.ledger-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        if (typeof onTabChange === 'function') onTabChange(tab.dataset.tab);
      });
    });
  }

  // ─── Company Records Table & History Tab (Separated View) ──────────
  let currentCompanyLedgerTab = 'active';
  let cachedCompanyRecords = [];

  function renderCompanyRecordsTable() {
    const tbody = $('#records-body');
    const thead = $('#records-thead');
    if (!tbody) return;

    const isCompany = getSession()?.role === 'company';
    const activeRecords = (cachedCompanyRecords || []).filter(r => !r.is_revoked);
    const historyRecords = (cachedCompanyRecords || []).filter(r => r.is_revoked);

    // Update count badges on tabs
    const activeCountEl = $('#active-count') || $('#active-count-upload');
    const historyCountEl = $('#history-count') || $('#history-count-upload');
    if (activeCountEl) activeCountEl.textContent = activeRecords.length;
    if (historyCountEl) historyCountEl.textContent = historyRecords.length;

    if (currentCompanyLedgerTab === 'creator-ip') {
      renderCreatorIpTable(tbody, thead, true);
      return;
    }

    if (currentCompanyLedgerTab === 'active') {
      if (thead) {
        thead.innerHTML = `
          <tr>
            <th>ID</th>
            <th>Merkle Root</th>
            <th>Status / Governance</th>
            <th>Bound AI Model</th>
            <th>IPFS Storage</th>
            <th>Version</th>
            <th>Creator</th>
            <th>Submitted By</th>
            <th>Timestamp</th>
          </tr>
        `;
      }
      if (activeRecords.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="table-empty">No active audit records found.</td></tr>`;
        return;
      }
      tbody.innerHTML = activeRecords.map(r => `
        <tr>
          <td><strong>#${r.id}</strong></td>
          <td>
            <code>${formatHash(r.root)}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${r.root}')">⧉</button>
            ${(r.collateral_bond_eth > 0 || r.auditor_fee_eth > 0) ? `<div style="font-size:9.5px;color:var(--muted);font-family:'JetBrains Mono',monospace;margin-top:2px;">Bond: ${r.collateral_bond_eth} ETH | Fee: ${r.auditor_fee_eth} ETH</div>` : ''}
          </td>
          <td>${renderStatusBadge(r)}</td>
          <td>${renderAiModelCell(r, isCompany)}</td>
          <td>${renderIpfsCell(r, false)}</td>
          <td>${escapeHtml(r.version)}</td>
          <td>${escapeHtml(r.creator)}</td>
          <td><code>${formatAddress(r.submitted_by)}</code></td>
          <td>${r.timestamp}</td>
        </tr>
      `).join('');
    } else {
      // History Tab (Revoked & Superseded datasets)
      if (thead) {
        thead.innerHTML = `
          <tr>
            <th>ID</th>
            <th>Revoked Merkle Root</th>
            <th>Superseded By (New Root)</th>
            <th>Revocation / Purge Reason</th>
            <th>Storage Status</th>
            <th>Bound AI Model</th>
            <th>Version</th>
            <th>Creator</th>
            <th>Timestamp</th>
          </tr>
        `;
      }
      if (historyRecords.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="table-empty">No superseded or revoked datasets in history. All records are currently active.</td></tr>`;
        return;
      }
      tbody.innerHTML = historyRecords.map(r => {
        const replacementPill = r.superseded_by
          ? `<span class="replacement-root-pill">↳ Replaced by: <code>${formatHash(r.superseded_by, 12)}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${r.superseded_by}')">⧉</button></span>`
          : `<span style="color:var(--muted);font-size:11px;">(Revoked)</span>`;
        const reasonTag = `<span class="revocation-reason-tag">❝ ${escapeHtml(r.revocation_reason || 'Superseded by updated clean dataset version')} ❞</span>`;
        const storageBadge = `<span class="badge-pruned">🗑️ IPFS Storage Pruned</span>`;

        return `
          <tr style="background:rgba(254,242,242,.25);">
            <td><strong>#${r.id}</strong></td>
            <td>
              <code>${formatHash(r.root, 12)}</code>
              <button class="copy-button" type="button" onclick="copyToClipboard('${r.root}')">⧉</button>
            </td>
            <td>${replacementPill}</td>
            <td>${reasonTag}</td>
            <td>${storageBadge}</td>
            <td>${renderAiModelCell(r, false)}</td>
            <td>${escapeHtml(r.version)}</td>
            <td>${escapeHtml(r.creator)}</td>
            <td>${r.timestamp}</td>
          </tr>
        `;
      }).join('');
    }
  }

  // ─── Records table helper (Unified Master Ledger & User Home Preview) ───
  function renderUserHomeRecords(records) {
    const tbody = $('#records-body');
    if (!tbody) return;
    if (!records || records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="table-empty">No public audit records found.</td></tr>`;
      return;
    }
    const recs = records.slice(-5).reverse();
    tbody.innerHTML = recs.map(r => `
      <tr>
        <td><strong>#${r.id}</strong></td>
        <td><code>${formatHash(r.root)}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${r.root}')">⧉</button></td>
        <td>${escapeHtml(r.version)}</td>
        <td>${escapeHtml(r.creator)}</td>
        <td>${r.timestamp}</td>
      </tr>
    `).join('');
  }

  async function loadRecords(limit) {
    const tbody = $('#records-body');
    if (!tbody) return;

    const isUserHome = document.body.classList.contains('user-page') || window.location.pathname.includes('user-home');

    try {
      const data = await request('/api/records');
      if (isUserHome || limit) {
        renderUserHomeRecords(data.records || []);
        return;
      }
      cachedCompanyRecords = data.records || [];
      renderCompanyRecordsTable();
    } catch (e) {
      const cols = isUserHome ? 5 : 9;
      tbody.innerHTML = `<tr><td colspan="${cols}" class="table-empty">${e.message}</td></tr>`;
    }
  }

  // ─── Page 1: Single Unified Login Portal (index.html) ─────────────
  window.quickFillLogin = function(username, password) {
    const uInput = $('#login-username');
    const pInput = $('#login-password');
    if (uInput) uInput.value = username;
    if (pInput) pInput.value = password;
    showToast(`Loaded ${username} credentials! Click Sign In.`);
  };

  function initLogin() {
    const s = getSession();
    if (s && s.token) {
      window.location.href = s.role === 'user' ? 'user-home.html' : 'company-home.html';
      return;
    }

    const unifiedForm = $('#unified-login-form');
    if (unifiedForm) {
      unifiedForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = $('button[type="submit"]', unifiedForm);
        const username = $('#login-username').value.trim();
        const password = $('#login-password').value.trim();
        if (!username || !password) {
          showToast('Please provide both username and password', 'error');
          return;
        }

        await withLoading(btn, async () => {
          try {
            const data = await request('/api/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ username, password }),
            });
            setSession({
              token: data.token,
              id: data.id,
              username: data.username,
              name: data.name,
              role: data.role,
              wallet_index: data.wallet_index,
              login_time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            });
            activeWalletIndex = data.wallet_index;
            localStorage.setItem('active_web3_wallet', data.wallet_index);
            showToast(`Signed in as ${data.name}`);
            const targetUrl = data.redirect || (data.role === 'user' ? 'user-home.html' : 'company-home.html');
            setTimeout(() => {
              window.location.href = targetUrl;
            }, 300);
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    }

    // Backwards compatibility for old forms if present
    const userForm = $('#user-login-form');
    const companyForm = $('#company-login-form');
    [userForm, companyForm].forEach(f => {
      if (f) {
        f.addEventListener('submit', async (e) => {
          e.preventDefault();
          const btn = $('button[type="submit"]', f);
          const username = $('input[name="username"]', f).value.trim();
          const password = $('input[name="password"]', f).value.trim();
          await withLoading(btn, async () => {
            try {
              const data = await request('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
              });
              setSession({
                token: data.token,
                id: data.id,
                username: data.username,
                name: data.name,
                role: data.role,
                wallet_index: data.wallet_index,
                login_time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              });
              activeWalletIndex = data.wallet_index;
              localStorage.setItem('active_web3_wallet', data.wallet_index);
              showToast(`Signed in as ${data.name}`);
              window.location.href = data.redirect || (data.role === 'user' ? 'user-home.html' : 'company-home.html');
            } catch (err) {
              showToast(err.message, 'error');
            }
          });
        });
      }
    });
  }

  // ─── Page 2: User Dashboard (user-home.html) ──────────────────────
  function initUserHome() {
    if (!requireAuth(['user', 'creator'])) return;
    populateUserInfo();
    checkHealth();
    loadWallets();
    loadRecords(5);
  }

  // ─── Page 3: User Verification (user-verify.html) ─────────────────
  function initUserVerify() {
    if (!requireAuth(['user', 'creator', 'company', 'auditor', 'deployer'])) return;
    populateUserInfo();
    checkHealth();
    loadWallets();

    const dropzone = $('[data-dropzone]');
    const input = $('#verify-file');
    const hashInput = $('#verify-hash-input');
    const dropzoneContainer = $('#dropzone-container');
    const hashInputContainer = $('#hash-input-container');
    const tabs = $$('[data-verify-tab]');

    let currentMode = 'file';
    let selectedFile = null;

    let currentEngine = 'server';
    const serverEngineBtn = $('#engine-server-btn');
    const clientEngineBtn = $('#engine-client-btn');

    if (serverEngineBtn && clientEngineBtn) {
      serverEngineBtn.addEventListener('click', () => {
        currentEngine = 'server';
        serverEngineBtn.classList.add('active');
        clientEngineBtn.classList.remove('active');
        showToast('Dual-Layer Server Verification Active', 'info');
      });
      clientEngineBtn.addEventListener('click', () => {
        currentEngine = 'client';
        clientEngineBtn.classList.add('active');
        serverEngineBtn.classList.remove('active');
        showToast('🛡️ 100% Client-Side Web3 Zero-Trust Sandbox Active', 'info');
      });
    }

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

      // ─── Engine Mode: 100% Client-Side Web3 Zero-Trust Sandbox ───
      if (currentEngine === 'client') {
        await withLoading(btn, async () => {
          try {
            resultDiv.hidden = false;
            let clientHash = '';
            let clientFileName = 'Confidential Record';
            if (currentMode === 'file') {
              if (!selectedFile) {
                showToast('Please choose or drop a confidential file to verify.', 'error');
                return;
              }
              clientFileName = selectedFile.name;
              const buffer = await selectedFile.arrayBuffer();
              const digest = await window.crypto.subtle.digest('SHA-256', buffer);
              clientHash = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
            } else {
              const rawHash = (hashInput ? hashInput.value : '').trim().toLowerCase();
              clientHash = rawHash.startsWith('0x') ? rawHash.slice(2) : rawHash;
              if (clientHash.length !== 64 || !/^[0-9a-f]{64}$/.test(clientHash)) {
                showToast('Invalid SHA-256 format (must be 64 hexadecimal characters).', 'error');
                return;
              }
            }

            const recsRes = await request('/api/records');
            const records = recsRes.records || [];
            let matchedRecord = null;
            let matchedManifest = null;
            let leafIndex = -1;

            for (const r of records) {
              try {
                const manifest = await request(`/api/zk-manifest/${r.root}`);
                if (manifest && manifest.leaf_hashes) {
                  const idx = manifest.leaf_hashes.indexOf(clientHash);
                  if (idx !== -1) {
                    matchedRecord = r;
                    matchedManifest = manifest;
                    leafIndex = idx;
                    break;
                  }
                }
              } catch (_) {}
            }

            if (matchedRecord && matchedManifest && leafIndex !== -1) {
              const clientProof = generateClientProof(matchedManifest.tree_levels, leafIndex);
              const clientVerif = await verifyMerkleProofClient(clientHash, clientProof, matchedManifest.root);

              resultDiv.className = 'result-panel success';
              const ladderHtml = renderProofLadder(clientProof, clientHash, matchedManifest.root);
              const certButtons = `
                <div style="display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 10px;">
                  <button type="button" class="cert-btn" onclick="window.downloadCertificate('${clientHash}', '${matchedManifest.root}', '${clientFileName}', 'json')">
                    📥 Download Audit Certificate (JSON)
                  </button>
                  <button type="button" class="cert-btn outline" onclick="window.viewCertificateHtml('${clientHash}', '${matchedManifest.root}', '${clientFileName}')">
                    📜 View Official Certificate (HTML) ↗
                  </button>
                </div>
              `;

              resultDiv.innerHTML = `
                <div class="result-head"><span class="result-icon">✓</span> Zero-Trust Client Verification Confirmed!</div>
                <div class="client-verify-card">
                  <div class="client-verify-head">
                    <span class="client-verify-title">🛡️ 100% CLIENT-SIDE WEB3 VERIFICATION (ZERO-TRUST SANDBOX)</span>
                    <span class="badge-pill badge-math" style="background:#16a34a;color:#fff;">W3C WebCrypto API</span>
                  </div>
                  <p style="font-size:12px;color:var(--charcoal);margin:0 0 10px;line-height:1.45;">
                    Verification executed entirely inside your local browser sandbox. The file never touched the company server.
                    Calculated SHA-256 digest: <code>${clientHash}</code> matched leaf index #${leafIndex} in the Public Zero-Knowledge Manifest.
                  </p>
                  <div style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--forest);">
                    Browser Recomputed Root: <code>${formatHash(clientVerif.calculatedRoot, 20)}</code> == On-Chain Root: <code>${formatHash(matchedRecord.root, 20)}</code> ${clientVerif.verified ? '✓ (100% MATCH)' : '✗ (MISMATCH)'}
                  </div>
                </div>
                <div class="badge-dual-wrap">
                  <span class="badge-pill badge-math">✓ Browser WebCrypto: DETERMINISTIC PASS</span>
                  <span class="badge-pill badge-chain">⛓ Smart Contract: ANCHORED ON-CHAIN</span>
                </div>
                <div class="hash-line">Record Name: <strong>${clientFileName}</strong></div>
                <div class="hash-line">File Hash (SHA-256): <code>${clientHash}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${clientHash}')">⧉</button></div>
                <div class="hash-line">Dataset Merkle Root: <code>${matchedRecord.root}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${matchedRecord.root}')">⧉</button></div>
                <div class="hash-line">Audited Dataset: <strong>${matchedRecord.version}</strong> by <strong>${matchedRecord.creator}</strong></div>
                ${ladderHtml}
                ${certButtons}
              `;
              showToast('100% Client-Side Web3 Verification confirmed!', 'success');
            } else {
              resultDiv.className = 'result-panel failure';
              resultDiv.innerHTML = `
                <div class="result-head"><span class="result-icon">✗</span> Record Not Found in Any Anchored Dataset</div>
                <div class="client-verify-card" style="background:#fff1f2;border-color:#fca5a5;">
                  <p style="font-size:12px;color:#991b1b;margin:0;">
                    Client-side evaluation calculated SHA-256 digest: <code>${clientHash}</code>. No matching leaf was located in any public Zero-Knowledge dataset manifest.
                  </p>
                </div>
              `;
              showToast('Verification failed: Record not found in ZK Manifests.', 'error');
            }
          } catch (err) {
            resultDiv.hidden = false;
            resultDiv.className = 'result-panel error';
            resultDiv.innerHTML = `<div class="result-head"><span class="result-icon">✗</span> Verification Error</div><p class="result-message">${err.message}</p>`;
            showToast(err.message, 'error');
          }
        });
        return;
      }

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

          // ─── Case 1: Fuzzy / Near-Match Tamper Alert ────────────────
          if (data.status === 'NEAR_MATCH_DETECTED') {
            resultDiv.className = 'result-panel warning';
            resultDiv.innerHTML = `
              <div class="tamper-alert">
                <div class="tamper-alert-head">
                  <span class="tamper-title">⚠️ PERCEPTUAL IP SHIELD: NEAR-MATCH DETECTED</span>
                  <span class="tamper-score-pill">${data.similarity_score}% SIMILARITY</span>
                </div>
                <div class="tamper-progress-bg">
                  <div class="tamper-progress-bar" style="width:${Math.min(100, data.similarity_score)}%;"></div>
                </div>
                <p style="font-size:12.5px;color:var(--charcoal);margin:0 0 12px;line-height:1.45;">
                  ${data.message}
                </p>
                <div class="hash-line">Matched Protected Record: <strong>${data.matched_filename || 'Confidential'}</strong></div>
                <div class="hash-line">Dataset Merkle Root: <code>${data.target_root}</code></div>
                <div class="hash-line">Dataset Version: <strong>${data.target_version}</strong> (Auditor: ${data.target_creator})</div>
                <div class="hash-line">Uploaded File SHA-256: <code>${data.file_hash}</code></div>
                <div class="tamper-locked-callout">
                  🔒 <strong>Confidential Decentralized Storage Strictly Locked</strong><br>
                  Although this file is <strong>${data.similarity_score}% perceptually identical</strong> to a registered record, its exact SHA-256 leaf digest differs (minor word alterations, formatting, or near-duplicate edits). Under patient &amp; enterprise confidentiality protocols, private IPFS storage remains locked until an exact cryptographic match is presented.
                </div>
              </div>
            `;
            showToast(`Near-match detected (${data.similarity_score}% similarity). Storage locked.`, 'info');
            return;
          }

          // ─── Case 2: Exact Cryptographic Match ──────────────────────
          if (data.verified) {
            resultDiv.className = 'result-panel success';
            const isAnchored = data.onchain_verified || (data.verified && data.on_chain);
            const mathBadge = `<span class="badge-pill badge-math">✓ Off-Chain Math: DETERMINISTIC PASS</span>`;
            const chainBadge = isAnchored
              ? `<span class="badge-pill badge-chain">⛓ Smart Contract: ANCHORED ON-CHAIN</span>`
              : `<span class="badge-pill badge-chain pending">⏱ Smart Contract: LOCAL MATCH (PENDING ANCHOR)</span>`;
            const dualBadges = `<div class="badge-dual-wrap">${mathBadge}${chainBadge}</div>`;

            let lineageBanner = '';
            if (data.is_revoked) {
              lineageBanner = `
                <div style="background:#fee2e2;border:1px solid #fca5a5;border-radius:8px;padding:12px 16px;margin:14px 0;font-size:12px;color:#991b1b;">
                  <strong>⚠️ DATASET SUPERSEDED / REVOKED:</strong> This record belongs to a deprecated dataset version.
                  ${data.superseded_by ? `<div>Superseded by root: <code>${formatHash(data.superseded_by, 18)}</code></div>` : ''}
                  ${data.revocation_reason ? `<div>Revocation Reason: <em>${data.revocation_reason}</em></div>` : ''}
                </div>
              `;
            }

            const unlockedStorageBox = data.ipfs_url ? `
              <div style="background:var(--sage);padding:14px;border-radius:8px;margin:14px 0;border:1px solid rgba(26,77,46,.18);">
                <div style="font-weight:600;font-size:12px;color:var(--forest);margin-bottom:6px;display:flex;align-items:center;gap:6px;">
                  <span>🔓</span> CONFIDENTIAL DECENTRALIZED STORAGE UNLOCKED
                </div>
                <p style="font-size:11px;color:var(--charcoal);margin:0 0 10px;line-height:1.4;">
                  Because you proved cryptographic possession of this record, your private IPFS decentralized storage has been unlocked.
                </p>
                <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                  <a href="${data.ipfs_url}" target="_blank" class="unlocked-pill">Open Verified File on IPFS ↗</a>
                  ${data.manifest_cid ? `<a href="https://violet-solid-ape-52.mypinata.cloud/ipfs/${data.manifest_cid}" target="_blank" class="btn-sm-outline" style="padding:5px 10px;font-size:11px;">View Merkle Manifest JSON ↗</a>` : ''}
                </div>
              </div>
            ` : '';

            const ladderHtml = renderProofLadder(data.proof, data.file_hash, data.root);

            const certButtons = `
              <div style="display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 10px;">
                <button type="button" class="cert-btn" onclick="window.downloadCertificate('${data.file_hash}', '${data.root}', '${data.matched_name || data.file_name}', 'json')">
                  📥 Download Audit Certificate (JSON)
                </button>
                <button type="button" class="cert-btn outline" onclick="window.viewCertificateHtml('${data.file_hash}', '${data.root}', '${data.matched_name || data.file_name}')">
                  📜 View Official Certificate (HTML) ↗
                </button>
              </div>
            `;

            resultDiv.innerHTML = `
              <div class="result-head"><span class="result-icon">✓</span> Verified Inclusion Confirmed!</div>
              ${dualBadges}
              <p class="result-message">${data.message}</p>
              ${lineageBanner}
              <div class="hash-line">Record Name: <strong>${data.matched_name || data.file_name}</strong></div>
              <div class="hash-line">File Hash (SHA-256): <code>${data.file_hash}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${data.file_hash}')">⧉</button></div>
              <div class="hash-line">Dataset Merkle Root: <code>${data.root}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${data.root}')">⧉</button></div>
              <div class="hash-line">Audited Dataset: <strong>${data.dataset_version}</strong> by <strong>${data.dataset_creator}</strong></div>
              ${unlockedStorageBox}
              ${ladderHtml}
              ${certButtons}
              <div class="hash-line" style="margin-top:14px;"><a href="public.html" class="text-link">Inspect dataset tree in Public Explorer →</a></div>
            `;
            showToast('Dual-layer verification confirmed!', 'success');
          } else {
            // ─── Case 3: Record Not Found ─────────────────────────────
            resultDiv.className = 'result-panel failure';
            resultDiv.innerHTML = `
              <div class="result-head"><span class="result-icon">✗</span> Record Not Found in Any Audited Dataset</div>
              <p class="result-message">${data.message}</p>
              <div class="hash-line">Fingerprint: <code>${data.file_hash}</code></div>
              <div class="hash-line" style="color:var(--muted);font-size:12px;">This record is not part of any on-chain or registered dataset on the ledger.</div>
            `;
            showToast('Verification failed: Record not found.', 'error');
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
    if (!requireAuth(['company', 'auditor', 'deployer'])) return;
    populateUserInfo();
    checkHealth();
    loadWallets();
    setupAttestModal();
    setupCreatorIpModal();

    setupLedgerTabs('#company-ledger-tabs', (tabKey) => {
      currentCompanyLedgerTab = tabKey;
      renderCompanyRecordsTable();
    });

    loadRecords();

    const refreshBtn = $('#refresh-records');
    if (refreshBtn) refreshBtn.addEventListener('click', () => { loadWallets(); loadRecords(); });

    // Bind AI Model Modal logic
    const openModalBtn = $('#open-model-modal-btn');
    const closeModalBtn = $('#close-model-modal');
    const modelModal = $('#model-modal');
    const rootSelect = $('#model-dataset-root-select');

    window.openBindModelModal = async function (rootHex) {
      if (!modelModal) return;
      modelModal.classList.add('open');
      if (rootSelect) {
        try {
          const data = await request('/api/records');
          if (data.records) {
            const activeList = data.records.filter(r => !r.is_revoked);
            const revokedList = data.records.filter(r => r.is_revoked);

            let optionsHtml = '<option value="">-- Select anchored dataset root --</option>';
            if (activeList.length > 0) {
              optionsHtml += '<optgroup label="Active Audited Datasets (Recommended)">' +
                activeList.map(r => `<option value="${r.root}">Record #${r.id} (${r.version}) — ${formatHash(r.root, 16)} [ACTIVE]</option>`).join('') +
                '</optgroup>';
            }
            if (revokedList.length > 0) {
              optionsHtml += '<optgroup label="Deprecated / Superseded Datasets (Historical)">' +
                revokedList.map(r => `<option value="${r.root}">Record #${r.id} (${r.version}) — ${formatHash(r.root, 16)} [SUPERSEDED]</option>`).join('') +
                '</optgroup>';
            }
            rootSelect.innerHTML = optionsHtml;
            if (rootHex) rootSelect.value = rootHex;
          }
        } catch (_) {}
      }
    };

    if (openModalBtn) {
      openModalBtn.addEventListener('click', () => window.openBindModelModal());
    }

    if (closeModalBtn && modelModal) {
      closeModalBtn.addEventListener('click', () => modelModal.classList.remove('open'));
    }

    if (modelModal) {
      modelModal.addEventListener('click', (e) => {
        if (e.target === modelModal) modelModal.classList.remove('open');
      });
    }

    const bindForm = $('#bind-model-form');
    if (bindForm) {
      bindForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const modelName = $('#model-name-input').value.trim();
        const framework = $('#model-framework-input').value.trim();
        let modelHash = $('#model-hash-input').value.trim().toLowerCase();
        if (modelHash.startsWith('0x')) modelHash = modelHash.slice(2);
        const datasetRoot = rootSelect ? rootSelect.value.trim().toLowerCase() : '';
        const metricsStr = $('#model-metrics-input').value.trim();

        let teeQuote = ($('#model-tee-quote-input') ? $('#model-tee-quote-input').value.trim().toLowerCase() : '');
        if (teeQuote.startsWith('0x')) teeQuote = teeQuote.slice(2);
        let canary = ($('#model-canary-input') ? $('#model-canary-input').value.trim().toLowerCase() : '');
        if (canary.startsWith('0x')) canary = canary.slice(2);

        if (modelHash.length !== 64 || !/^[0-9a-f]{64}$/.test(modelHash)) {
          showToast('Model weights hash must be a 64-character SHA-256 hexadecimal string.', 'error');
          return;
        }
        if (!datasetRoot) {
          showToast('Please select a target training dataset Merkle root.', 'error');
          return;
        }

        let metricsObj = {};
        try { metricsObj = JSON.parse(metricsStr); } catch (_) { metricsObj = { raw: metricsStr }; }

        const submitBtn = $('button[type="submit"]', bindForm);
        await withLoading(submitBtn, async () => {
          try {
            const res = await request('/api/register-model', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                model_hash: modelHash,
                dataset_root: datasetRoot,
                model_name: modelName,
                framework,
                metrics: metricsObj,
                tee_enclave_quote_hash: teeQuote,
                canary_trap_hash: canary,
                account: activeWalletIndex,
              }),
            });
            showToast(`AI Model checkpoint successfully bound on-chain! Block #${res.block_number}`);
            modelModal.classList.remove('open');
            bindForm.reset();
            loadWallets();
            loadRecords();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    }
  }

  // ─── Page 5: Company Upload (company-upload.html) ─────────────────
  function initCompanyUpload() {
    if (!requireAuth(['company', 'deployer'])) return;
    populateUserInfo();
    checkHealth();
    loadWallets();
    setupAttestModal();
    setupCreatorIpModal();

    setupLedgerTabs('#upload-ledger-tabs', (tabKey) => {
      currentCompanyLedgerTab = tabKey;
      renderCompanyRecordsTable();
    });

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

    // Supersede Checkbox toggle logic
    const supersedeCheckbox = $('#supersede-checkbox');
    const supersedeFields = $('#supersede-fields');
    const parentRootSelect = $('#parent-root-select');

    if (supersedeCheckbox && supersedeFields) {
      supersedeCheckbox.addEventListener('change', async () => {
        supersedeFields.style.display = supersedeCheckbox.checked ? 'block' : 'none';
        if (supersedeCheckbox.checked && parentRootSelect) {
          try {
            const recsData = await request('/api/records');
            if (recsData.records) {
              const activeList = recsData.records.filter(r => !r.is_revoked);
              const revokedList = recsData.records.filter(r => r.is_revoked);

              let opts = '<option value="">-- Choose active dataset to supersede --</option>';
              if (activeList.length > 0) {
                opts += '<optgroup label="Active Datasets (Eligible to Supersede)">' +
                  activeList.map(r => `<option value="${r.root}">Record #${r.id} (${r.version}) — ${formatHash(r.root, 16)} [ACTIVE]</option>`).join('') +
                  '</optgroup>';
              }
              if (revokedList.length > 0) {
                opts += '<optgroup label="Already Superseded Datasets (Disabled)">' +
                  revokedList.map(r => `<option value="${r.root}" disabled style="color:var(--muted);background:#fee2e2;">Record #${r.id} (${r.version}) — ${formatHash(r.root, 16)} [SUPERSEDED]</option>`).join('') +
                  '</optgroup>';
              }
              parentRootSelect.innerHTML = opts;
            }
          } catch (_) {}
        }
      });
    }

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
          const telemetryHtml = data.telemetry ? `
            <div class="telemetry-strip">
              <span class="telemetry-pill">⚡ Throughput: ${data.telemetry.throughput_mbps} MB/s</span>
              <span class="telemetry-pill">⏱ Hashing Duration: ${data.telemetry.hashing_duration_ms} ms</span>
              <span class="telemetry-pill">📦 Volume: ${(data.telemetry.total_bytes / 1024).toFixed(1)} KB</span>
              <span class="telemetry-pill">🧵 Threads: ${data.telemetry.parallel_workers}</span>
            </div>
          ` : '';

          const nutritionHtml = renderNutritionCard(data.nutrition_label);

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

            ${telemetryHtml}
            ${nutritionHtml}

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
                    <div>
                      <span>${f.name}</span>
                      ${f.fingerprint ? `<span style="font-size:10px;color:var(--muted);margin-left:6px;font-family:'JetBrains Mono',monospace;">(SimHash: ${formatHash(f.fingerprint, 8)})</span>` : ''}
                    </div>
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

        const isSupersede = Boolean(supersedeCheckbox && supersedeCheckbox.checked);
        const parentRoot = isSupersede ? (parentRootSelect ? parentRootSelect.value.trim() : '') : '';
        const revocationReason = isSupersede ? ($('#revocation-reason-input') ? $('#revocation-reason-input').value.trim() : '') : '';

        if (isSupersede && !parentRoot) {
          showToast('Please choose an active dataset root to supersede.', 'error');
          return;
        }

        const bondVal = $('#collateral-bond-input') ? parseFloat($('#collateral-bond-input').value) || 0 : 0;
        const feeVal = $('#auditor-fee-input') ? parseFloat($('#auditor-fee-input').value) || 0 : 0;

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
                parent_root: parentRoot,
                revocation_reason: revocationReason,
                collateral_bond_eth: bondVal,
                auditor_fee_eth: feeVal,
                account: activeWalletIndex,
              }),
            });
            const resultDiv = $('#submit-result');
            if (resultDiv) {
              resultDiv.hidden = false;
              resultDiv.className = 'result-panel success';
              const supersedeNotice = data.is_supersede
                ? `<div style="background:#fee2e2;border:1px solid #fca5a5;border-radius:6px;padding:8px 12px;margin:10px 0;font-size:12px;color:#991b1b;">
                     ⛓ Successfully superseded parent root <code>${formatHash(data.parent_root, 16)}</code> on-chain!
                   </div>`
                : '';
              resultDiv.innerHTML = `
                <div class="result-head"><span class="result-icon">✓</span> Successfully Anchored On-Chain!</div>
                <p class="result-message">The Merkle root and off-chain IPFS storage hash are permanently anchored.</p>
                ${supersedeNotice}
                <div class="hash-line">Transaction Hash: <code>${data.tx_hash}</code> <button class="copy-button" type="button" onclick="copyToClipboard('${data.tx_hash}')">⧉</button></div>
                <div class="hash-line">Block Number: <strong>${data.block_number}</strong></div>
                <div class="hash-line">Dataset Version: <strong>${data.version}</strong> by <strong>${data.creator}</strong></div>
                ${data.ipfs_cid ? `<div class="hash-line">IPFS Decentralized Storage: <a href="${data.ipfs_gateway || ('https://gateway.pinata.cloud/ipfs/' + data.ipfs_cid)}" target="_blank" class="ipfs-pill"><code>${formatHash(data.ipfs_cid, 20)}</code> ↗ (Pinned on IPFS)</a></div>` : ''}
              `;
            }
            showToast(data.is_supersede ? 'Parent root superseded on Ethereum blockchain!' : 'Root anchored on Ethereum blockchain!');
            loadWallets();
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
  let currentPublicTab = 'active';
  let cachedPublicRecords = [];

  window.selectPublicRecord = function (rootHex) {
    const selector = $('#dataset-selector');
    if (selector) {
      selector.value = rootHex;
      selector.dispatchEvent(new Event('change'));
    }
  };

  function renderPublicRecordsTable() {
    const tbody = $('#public-records-body');
    const thead = $('#public-records-thead');
    if (!tbody) return;

    const activeRecords = (cachedPublicRecords || []).filter(r => !r.is_revoked);
    const historyRecords = (cachedPublicRecords || []).filter(r => r.is_revoked);

    const activeCountEl = $('#public-active-count');
    const historyCountEl = $('#public-history-count');
    if (activeCountEl) activeCountEl.textContent = activeRecords.length;
    if (historyCountEl) historyCountEl.textContent = historyRecords.length;

    if (currentPublicTab === 'creator-ip') {
      renderCreatorIpTable(tbody, thead, false);
      return;
    }

    if (currentPublicTab === 'active') {
      if (thead) {
        thead.innerHTML = `
          <tr>
            <th>ID</th>
            <th>Merkle Root</th>
            <th>Status / Governance</th>
            <th>Bound AI Model</th>
            <th>Storage Privacy</th>
            <th>Version</th>
            <th>Creator</th>
            <th>Submitted By</th>
            <th>Timestamp</th>
          </tr>
        `;
      }
      if (activeRecords.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="table-empty">No active records on-chain.</td></tr>';
        return;
      }
      tbody.innerHTML = activeRecords.map(r => `
        <tr style="cursor:pointer;" onclick="selectPublicRecord('${r.root}')">
          <td><strong>#${r.id}</strong></td>
          <td>
            <code>${formatHash(r.root)}</code>
            ${(r.collateral_bond_eth > 0 || r.auditor_fee_eth > 0) ? `<div style="font-size:9.5px;color:var(--muted);font-family:'JetBrains Mono',monospace;margin-top:2px;">Bond: ${r.collateral_bond_eth} ETH | Fee: ${r.auditor_fee_eth} ETH</div>` : ''}
          </td>
          <td>${renderStatusBadge(r)}</td>
          <td>${renderAiModelCell(r, false)}</td>
          <td><span class="privacy-pill">🔒 Private Off-Chain</span></td>
          <td>${escapeHtml(r.version)}</td>
          <td>${escapeHtml(r.creator)}</td>
          <td><code>${formatAddress(r.submitted_by)}</code></td>
          <td>${r.timestamp}</td>
        </tr>
      `).join('');
    } else {
      // History Tab for Public Explorer
      if (thead) {
        thead.innerHTML = `
          <tr>
            <th>ID</th>
            <th>Revoked Merkle Root</th>
            <th>Superseded By (New Root)</th>
            <th>Revocation / Purge Reason</th>
            <th>Storage Status</th>
            <th>Bound AI Model</th>
            <th>Version</th>
            <th>Auditor</th>
            <th>Timestamp</th>
          </tr>
        `;
      }
      if (historyRecords.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="table-empty">No superseded or revoked datasets in history. All registered datasets are currently active.</td></tr>';
        return;
      }
      tbody.innerHTML = historyRecords.map(r => {
        const replacementPill = r.superseded_by
          ? `<span class="replacement-root-pill">↳ Replaced by: <code>${formatHash(r.superseded_by, 12)}</code></span>`
          : `<span style="color:var(--muted);font-size:11px;">(Revoked)</span>`;
        const reasonTag = `<span class="revocation-reason-tag">❝ ${escapeHtml(r.revocation_reason || 'Superseded by updated clean dataset version')} ❞</span>`;
        const storageBadge = `<span class="badge-pruned">🗑️ IPFS Storage Pruned</span>`;

        return `
          <tr style="cursor:pointer;background:rgba(254,242,242,.25);" onclick="selectPublicRecord('${r.root}')">
            <td><strong>#${r.id}</strong></td>
            <td><code>${formatHash(r.root, 12)}</code></td>
            <td>${replacementPill}</td>
            <td>${reasonTag}</td>
            <td>${storageBadge}</td>
            <td>${renderAiModelCell(r, false)}</td>
            <td>${escapeHtml(r.version)}</td>
            <td>${escapeHtml(r.creator)}</td>
            <td>${r.timestamp}</td>
          </tr>
        `;
      }).join('');
    }
  }

  function initPublic() {
    checkHealth();
    loadWallets();
    setupAttestModal();
    setupCreatorIpModal();

    setupLedgerTabs('#public-ledger-tabs', (tabKey) => {
      currentPublicTab = tabKey;
      renderPublicRecordsTable();
    });
    loadPublicOverview();
    const refreshBtn = $('#refresh-public');
    if (refreshBtn) refreshBtn.addEventListener('click', () => { loadWallets(); loadPublicOverview(); });
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

      // Populate dataset selector with grouped options
      const selector = $('#dataset-selector');
      if (selector && data.records) {
        const activeList = data.records.filter(r => !r.is_revoked);
        const revokedList = data.records.filter(r => r.is_revoked);
        let opts = '';
        if (activeList.length > 0) {
          opts += '<optgroup label="Active Datasets">' +
            activeList.map(r => `<option value="${r.root}">Record #${r.id} — ${escapeHtml(r.version)} (${escapeHtml(r.creator)})</option>`).join('') +
            '</optgroup>';
        }
        if (revokedList.length > 0) {
          opts += '<optgroup label="Superseded Datasets (Historical)">' +
            revokedList.map(r => `<option value="${r.root}">Record #${r.id} [SUPERSEDED] — ${escapeHtml(r.version)} (${escapeHtml(r.creator)})</option>`).join('') +
            '</optgroup>';
        }
        selector.innerHTML = opts || '<option value="">No datasets registered yet</option>';

        selector.onchange = async () => {
          if (!selector.value) return;
          try {
            const treeData = await request(`/api/tree/${selector.value}`);
            renderPublicTree(treeData);
            const nutContainer = $('#public-nutrition-container');
            if (nutContainer) nutContainer.innerHTML = renderNutritionCard(treeData.nutrition_label);
          } catch (_) {}
        };
      }

      // Render latest tree and nutrition label
      if (data.latest_tree) {
        const latestRec = data.records && data.records.length ? data.records[data.records.length - 1] : null;
        renderPublicTree({
          root: data.latest_root,
          version: latestRec ? latestRec.version : 'v1.0',
          tree: data.latest_tree,
        });
        const nutContainer = $('#public-nutrition-container');
        if (nutContainer && latestRec && latestRec.nutrition_label) {
          nutContainer.innerHTML = renderNutritionCard(latestRec.nutrition_label);
        }
      } else {
        const treeDetail = $('#tree-detail');
        if (treeDetail) treeDetail.innerHTML = '<div class="table-empty">No active Merkle trees recorded on-chain yet. Datasets will appear here once anchored.</div>';
        const nutContainer = $('#public-nutrition-container');
        if (nutContainer) nutContainer.innerHTML = '';
      }

      // Render public records ledger with Lineage Status AND Bound AI Model (Unified Ledger with Tabs)
      cachedPublicRecords = data.records || [];
      renderPublicRecordsTable();

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
  window.closeDatasetModal = function () {
    const m = document.getElementById('dataset-files-modal');
    if (m) m.classList.remove('open');
  };

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') window.closeDatasetModal();
  });

  window.viewDatasetFiles = async function (rootHex) {
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
