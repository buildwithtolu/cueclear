// CueClear studio controller — clearance workflow only

let currentCues = [];
let activeFilter = 'all';
let isRunning = false;
let sampleDataMap = {};
let activeReelId = 'sample_mixed';
let hasTimelineLoaded = false;
let hasClearanceResult = false;
let activeEventSource = null;

document.addEventListener('DOMContentLoaded', async () => {
  initUI();
  await refreshHealth();
  await loadSampleTimelines();
});

function initUI() {
  const btnExport = document.getElementById('btnExportMenu');
  const exportPopup = document.getElementById('exportMenuPopup');
  if (btnExport && exportPopup) {
    btnExport.addEventListener('click', (e) => {
      e.stopPropagation();
      if (btnExport.disabled) return;
      exportPopup.classList.toggle('show');
    });
    document.addEventListener('click', () => exportPopup.classList.remove('show'));
  }

  document.getElementById('btnReelTrailer')?.addEventListener('click', () => switchReel('sample_trailer'));
  document.getElementById('btnReelIndie')?.addEventListener('click', () => switchReel('sample_indie'));
  document.getElementById('btnReelMixed')?.addEventListener('click', () => switchReel('sample_mixed'));

  const fileInput = document.getElementById('fileInput');
  document.getElementById('btnReelCustom')?.addEventListener('click', () => fileInput?.click());

  const dropzone = document.getElementById('technicalDropzone');
  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
      }
    });
  }

  document.getElementById('btnResolveRights')?.addEventListener('click', startClearanceStream);

  document.querySelectorAll('.filter-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.dataset.filter || 'all';
      renderCueMatrix();
    });
  });

  document.getElementById('matrixSearchInput')?.addEventListener('input', () => renderCueMatrix());

  const modalOverlay = document.getElementById('splitModalOverlay');
  const modalCloseBtn = document.getElementById('modalCloseBtn');
  if (modalCloseBtn && modalOverlay) {
    modalCloseBtn.addEventListener('click', () => modalOverlay.classList.remove('show'));
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) modalOverlay.classList.remove('show');
    });
  }

  setExportEnabled(false);
  setResolveEnabled(false, 'Load a timeline first.');
}

async function refreshHealth() {
  const geminiEl = document.getElementById('healthGemini');
  const parallelEl = document.getElementById('healthParallel');
  try {
    const res = await fetch('/api/health', { credentials: 'same-origin' });
    const data = await res.json();
    const hasDetail = Object.prototype.hasOwnProperty.call(data, 'gemini_active');
    if (geminiEl) {
      geminiEl.textContent = hasDetail
        ? (data.gemini_active ? 'CONNECTED' : 'NOT CONFIGURED')
        : 'AVAILABLE';
    }
    if (parallelEl) {
      parallelEl.textContent = hasDetail
        ? (data.parallel_search_configured ? 'CONNECTED' : 'NOT CONFIGURED')
        : 'AVAILABLE';
    }
    clearTerminal();
    logTerminal('term-sys', 'CueClear ready.');
    if (hasDetail && !data.gemini_active) {
      logTerminal('term-flagged', 'Gemini key not configured. Clearance can still run with offline catalog fallback.');
    }
    if (hasDetail && !data.parallel_search_configured) {
      logTerminal('term-flagged', 'Parallel key not configured. Live Search/Extract unavailable until PARALLEL_API_KEY is set.');
    }
    if (hasDetail && data.gemini_active && data.parallel_search_configured) {
      logTerminal('term-verified', 'Gemini and Parallel are connected.');
    }
    logTerminal('term-sys', 'Load a sample timeline or upload an EDL/XML file to begin.');
  } catch (err) {
    if (geminiEl) geminiEl.textContent = 'UNREACHABLE';
    if (parallelEl) parallelEl.textContent = 'UNREACHABLE';
    clearTerminal();
    logTerminal('term-flagged', `Could not reach API health endpoint: ${err.message}`);
  }
}

async function loadSampleTimelines() {
  try {
    const res = await fetch('/api/sample-timelines', { credentials: 'same-origin' });
    const samples = await res.json();
    samples.forEach((s) => {
      sampleDataMap[s.id] = s;
    });

    if (sampleDataMap.sample_mixed) {
      await switchReel('sample_mixed');
    } else if (sampleDataMap.sample_trailer) {
      await switchReel('sample_trailer');
    }
  } catch (err) {
    logTerminal('term-flagged', `Failed to load sample timelines: ${err.message}`);
  }
}

async function switchReel(reelId) {
  activeReelId = reelId;
  document.querySelectorAll('.btn-reel-select').forEach((b) => b.classList.remove('active'));

  const activeLabel = document.getElementById('activeTimelineLabel');
  if (reelId === 'sample_trailer') {
    document.getElementById('btnReelTrailer')?.classList.add('active');
    if (activeLabel) activeLabel.textContent = 'Trailer sample (.edl)';
  } else if (reelId === 'sample_indie') {
    document.getElementById('btnReelIndie')?.classList.add('active');
    if (activeLabel) activeLabel.textContent = 'Indie sample (.xml)';
  } else if (reelId === 'sample_mixed') {
    document.getElementById('btnReelMixed')?.classList.add('active');
    if (activeLabel) activeLabel.textContent = 'Mixed clearance sample (.edl)';
  }

  const sample = sampleDataMap[reelId];
  if (!sample) {
    logTerminal('term-flagged', `Sample "${reelId}" is not available.`);
    return;
  }

  const formData = new FormData();
  formData.append('raw_content', sample.content);
  formData.append('file_type', sample.type);
  formData.append('project_title', sample.name);

  try {
    const res = await fetch('/api/upload-timeline', { method: 'POST', body: formData, credentials: 'same-origin' });
    if (!res.ok) {
      throw new Error(`Upload failed (${res.status})`);
    }
    const data = await res.json();
    applyTimelineMeta(data);
    resetClearanceState();
    logTerminal('term-sys', `Loaded "${sample.name}" — ${data.total_clips} audio cue(s) detected.`);
  } catch (err) {
    logTerminal('term-flagged', `Failed to ingest sample: ${err.message}`);
  }
}

async function handleFileUpload(file) {
  document.querySelectorAll('.btn-reel-select').forEach((b) => b.classList.remove('active'));
  document.getElementById('btnReelCustom')?.classList.add('active');

  const ext = (file.name.split('.').pop() || 'FILE').toUpperCase();
  const activeLabel = document.getElementById('activeTimelineLabel');
  if (activeLabel) activeLabel.textContent = `${file.name} (.${ext.toLowerCase()})`;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('project_title', file.name.replace(/\.[^/.]+$/, ''));

  try {
    const res = await fetch('/api/upload-timeline', { method: 'POST', body: formData, credentials: 'same-origin' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    const data = await res.json();
    applyTimelineMeta(data);
    resetClearanceState();
    logTerminal('term-pro', `Uploaded "${file.name}" — ${data.total_clips} audio cue(s) detected.`);
  } catch (err) {
    logTerminal('term-flagged', `Timeline upload failed: ${err.message}`);
  }
}

function applyTimelineMeta(data) {
  hasTimelineLoaded = Number(data.total_clips || 0) > 0;
  document.getElementById('valClipCount').textContent = hasTimelineLoaded
    ? `${data.total_clips} cue${data.total_clips === 1 ? '' : 's'}`
    : '0 cues';
  document.getElementById('valFps').textContent = hasTimelineLoaded ? `${deriveFps(data.clips)} fps` : '—';
  document.getElementById('valDuration').textContent = hasTimelineLoaded
    ? computeSequenceDuration(data.clips)
    : '—';
  setResolveEnabled(
    hasTimelineLoaded,
    hasTimelineLoaded ? 'Ready to clear this timeline.' : 'Load a timeline first.'
  );
}

function resetClearanceState() {
  currentCues = [];
  hasClearanceResult = false;
  setExportEnabled(false);
  updateCompliance(null);
  renderCueMatrix();
  document.getElementById('topbarStatusVal').textContent = 'READY';
  document.getElementById('agentTelemetryPill').textContent = 'IDLE';
}

function computeSequenceDuration(clips) {
  if (!Array.isArray(clips) || clips.length === 0) return '—';
  let best = clips[0].record_out || '00:00:00:00';
  for (const clip of clips) {
    const out = clip.record_out || '00:00:00:00';
    if (out > best) best = out;
  }
  return best;
}

function deriveFps(clips) {
  if (!Array.isArray(clips) || clips.length === 0) return '24.00';
  return Number(clips[0].fps || 24).toFixed(2);
}

function startClearanceStream() {
  if (isRunning) return;
  if (!hasTimelineLoaded) {
    logTerminal('term-flagged', 'Load a timeline before running clearance.');
    return;
  }

  isRunning = true;
  currentCues = [];
  hasClearanceResult = false;
  setExportEnabled(false);
  renderCueMatrix();

  const statusPill = document.getElementById('agentTelemetryPill');
  const topbarStatus = document.getElementById('topbarStatusVal');
  const btnResolve = document.getElementById('btnResolveRights');

  if (statusPill) statusPill.textContent = 'RUNNING';
  if (topbarStatus) topbarStatus.textContent = 'CLEARING';
  if (btnResolve) {
    btnResolve.disabled = true;
    btnResolve.textContent = 'Clearance in progress…';
  }
  setResolveHelper('Clearance running. Watch the activity log for Parallel and Gemini steps.');

  logTerminal('term-sys', 'Starting rights clearance…');

  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }

  const eventSource = new EventSource('/api/stream-clearance');
  activeEventSource = eventSource;

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleAgentEvent(data, eventSource);
    } catch (e) {
      console.error('SSE parse error', e);
    }
  };

  eventSource.onerror = () => {
    if (!isRunning) return;
    eventSource.close();
    activeEventSource = null;
    logTerminal('term-flagged', 'Clearance stream disconnected before completion.');
    finishRun(false);
  };
}

function handleAgentEvent(event, eventSource) {
  const timeStr = event.timestamp ? `[${event.timestamp}] ` : '';

  switch (event.event_type) {
    case 'start':
      logTerminal('term-sys', `${timeStr}${event.message}`);
      break;
    case 'reasoning':
      logTerminal('term-extract', `${timeStr}${event.message}`);
      break;
    case 'parallel_query':
    case 'parallel_result':
      logTerminal('term-pro', `${timeStr}${event.message}`);
      break;
    case 'reconciliation':
      logTerminal('term-audit', `${timeStr}${event.message}`);
      break;
    case 'cue_verified':
      logTerminal('term-verified', `${timeStr}${event.message}`);
      if (event.data) addOrUpdateCue(event.data);
      break;
    case 'cue_flagged':
      logTerminal('term-flagged', `${timeStr}${event.message}`);
      if (event.data) addOrUpdateCue(event.data);
      break;
    case 'complete':
      logTerminal('term-verified', `${timeStr}${event.message}`);
      if (event.data) {
        updateCompliance(event.data.compliance_score);
        if (Array.isArray(event.data.cues) && event.data.cues.length) {
          currentCues = event.data.cues;
          renderCueMatrix();
        }
      }
      hasClearanceResult = currentCues.length > 0;
      setExportEnabled(hasClearanceResult);
      if (eventSource) {
        eventSource.close();
        activeEventSource = null;
      }
      finishRun(true);
      break;
    default:
      break;
  }
}

function addOrUpdateCue(cueData) {
  const existingIdx = currentCues.findIndex((c) => c.cue_number === cueData.cue_number);
  if (existingIdx >= 0) {
    currentCues[existingIdx] = cueData;
  } else {
    currentCues.push(cueData);
  }
  renderCueMatrix();
}

function finishRun(success) {
  isRunning = false;
  const statusPill = document.getElementById('agentTelemetryPill');
  const topbarStatus = document.getElementById('topbarStatusVal');
  const btnResolve = document.getElementById('btnResolveRights');

  if (statusPill) statusPill.textContent = 'IDLE';
  if (topbarStatus) topbarStatus.textContent = success ? 'CLEARED' : 'READY';
  if (btnResolve) {
    btnResolve.disabled = !hasTimelineLoaded;
    btnResolve.textContent = 'Run rights clearance again';
  }
  setResolveHelper(
    hasClearanceResult
      ? 'Inspect cues below. Pending items can be signed off before export.'
      : 'Load a timeline, then run clearance.'
  );
}

function setResolveEnabled(enabled, helperText) {
  const btnResolve = document.getElementById('btnResolveRights');
  if (btnResolve) {
    btnResolve.disabled = !enabled || isRunning;
    if (!isRunning) btnResolve.textContent = 'Run rights clearance';
  }
  setResolveHelper(helperText);
}

function setResolveHelper(text) {
  const helper = document.getElementById('resolveHelper');
  if (helper) helper.textContent = text || '';
}

function setExportEnabled(enabled) {
  const btnExport = document.getElementById('btnExportMenu');
  const popup = document.getElementById('exportMenuPopup');
  if (btnExport) {
    btnExport.disabled = !enabled;
    btnExport.title = enabled
      ? 'Download Excel, CISAC XML, or JSON'
      : 'Run clearance before exporting';
  }
  if (!enabled && popup) popup.classList.remove('show');
}

function updateCompliance(score) {
  const scoreElem = document.getElementById('matrixComplianceScore');
  if (!scoreElem) return;
  if (score === null || score === undefined || Number.isNaN(Number(score))) {
    scoreElem.textContent = '—';
    return;
  }
  scoreElem.textContent = `${score}%`;
}

function clearTerminal() {
  const terminal = document.getElementById('terminalFeed');
  if (terminal) terminal.innerHTML = '';
}

function logTerminal(className, text) {
  const terminal = document.getElementById('terminalFeed');
  if (!terminal) return;
  const line = document.createElement('div');
  line.className = `term-line ${className}`;
  line.textContent = text;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderCueMatrix() {
  const tbody = document.getElementById('matrixTableBody');
  if (!tbody) return;

  const searchVal = document.getElementById('matrixSearchInput')?.value.toLowerCase().trim() || '';

  let filtered = currentCues.filter((cue) => {
    if (activeFilter === 'cleared') return cue.is_verified;
    if (activeFilter === 'pending') return cue.split_status === 'PRO_REGISTERED_SPLIT_UNDISCLOSED';
    if (activeFilter === 'partial') {
      return (
        cue.split_status === 'PARTIAL_PUBLISHER_CLAIM_FLAGGED' ||
        cue.split_status === 'UNREGISTERED_WORK_FLAGGED' ||
        (!cue.is_verified && cue.split_status !== 'PRO_REGISTERED_SPLIT_UNDISCLOSED')
      );
    }
    if (activeFilter === 'live') return cue.source_type === 'LIVE_PARALLEL_API' || cue.is_live_hit;
    return true;
  });

  if (searchVal) {
    filtered = filtered.filter((cue) => {
      const writersStr = (cue.writers || []).map((w) => w.name).join(' ').toLowerCase();
      const pubStr = (cue.publishers || []).map((p) => p.name).join(' ').toLowerCase();
      return (
        (cue.title || '').toLowerCase().includes(searchVal) ||
        (cue.artist || '').toLowerCase().includes(searchVal) ||
        writersStr.includes(searchVal) ||
        pubStr.includes(searchVal) ||
        (cue.work_id || '').toLowerCase().includes(searchVal)
      );
    });
  }

  const displayedCountElem = document.getElementById('displayedCount');
  const totalCountElem = document.getElementById('totalCount');
  if (displayedCountElem) displayedCountElem.textContent = filtered.length;
  if (totalCountElem) totalCountElem.textContent = currentCues.length;

  if (filtered.length === 0) {
    const message = currentCues.length === 0
      ? 'No cues yet. Load a timeline and run rights clearance.'
      : 'No cues match this filter or search.';
    tbody.innerHTML = `
      <tr>
        <td colspan="11" class="empty-state-cell">${escapeHtml(message)}</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map((cue) => {
    const writersFormatted = (cue.writers || []).length
      ? (cue.writers || []).map((w) => `<span class="font-mono">${escapeHtml(w.name)} [${escapeHtml(w.pro || '—')}]</span>`).join('<br>')
      : '<span class="muted">None found</span>';
    const pubsFormatted = (cue.publishers || []).length
      ? (cue.publishers || []).map((p) => `<span class="font-mono">${escapeHtml(p.name)} [${escapeHtml(p.pro || '—')}]</span>`).join('<br>')
      : '<span class="muted">None found</span>';

    let statusTag = '';
    let writerPill = '';
    let pubPill = '';

    if (cue.supervisor_signed_off) {
      statusTag = '<span class="tag-supervisor-signed">Signed off</span>';
      writerPill = `<span class="font-mono status-ok">${escapeHtml(cue.total_writer_share)}%</span>`;
      pubPill = `<span class="font-mono status-ok">${escapeHtml(cue.total_publisher_share)}%</span>`;
    } else if (cue.is_verified) {
      statusTag = '<span class="tag-inverted-black">Cleared</span>';
      writerPill = `<span class="font-mono">${escapeHtml(cue.total_writer_share)}%</span>`;
      pubPill = `<span class="font-mono">${escapeHtml(cue.total_publisher_share)}%</span>`;
    } else if (cue.split_status === 'PRO_REGISTERED_SPLIT_UNDISCLOSED') {
      statusTag = '<span class="tag-amber-outline">Pending sign-off</span>';
      writerPill = `<span class="font-mono status-warn">Undisclosed${cue.estimated_equal_share != null ? ` (est. ${escapeHtml(cue.estimated_equal_share)}%)` : ''}</span>`;
      pubPill = '<span class="font-mono status-warn">Undisclosed</span>';
    } else if (cue.split_status === 'PARTIAL_PUBLISHER_CLAIM_FLAGGED') {
      statusTag = '<span class="tag-red-outline">Partial claim</span>';
      writerPill = `<span class="font-mono">${escapeHtml(cue.total_writer_share)}%</span>`;
      pubPill = `<span class="font-mono status-bad">${escapeHtml(cue.total_publisher_share)}% open</span>`;
    } else if (cue.split_status === 'UNREGISTERED_WORK_FLAGGED') {
      statusTag = '<span class="tag-red-outline">Unresolved</span>';
      writerPill = '<span class="font-mono muted">—</span>';
      pubPill = '<span class="font-mono muted">—</span>';
    } else {
      statusTag = '<span class="tag-red-outline">Needs review</span>';
      writerPill = `<span class="font-mono">${escapeHtml(cue.total_writer_share ?? '—')}</span>`;
      pubPill = `<span class="font-mono">${escapeHtml(cue.total_publisher_share ?? '—')}</span>`;
    }

    let sourceTag = '';
    if (cue.is_live_hit || cue.source_type === 'LIVE_PARALLEL_API') {
      sourceTag = `<span class="tag-telemetry-chip live">Live Parallel${cue.latency_ms != null ? ` · ${escapeHtml(cue.latency_ms)}ms` : ''}</span>`;
    } else if (cue.source_type === 'LOCAL_PRO_CATALOG_FALLBACK') {
      sourceTag = '<span class="tag-telemetry-chip cached">Offline fallback</span>';
    } else if ((cue.artist || '').toLowerCase().includes('sound design') || (cue.title || '').toLowerCase().includes('sfx')) {
      sourceTag = '<span class="tag-telemetry-chip sfx">In-house SFX</span>';
    }

    return `
      <tr>
        <td class="font-mono" style="font-weight: 800;">${String(cue.cue_number).padStart(3, '0')}</td>
        <td>
          <strong style="font-size: 13px; font-weight: 800; display: block;">${escapeHtml(cue.title)}</strong>
          <span style="font-size: 11px; color: var(--swiss-gray-mid); display: block;">${escapeHtml(cue.artist || 'Unknown artist')}</span>
          <div>${sourceTag}</div>
        </td>
        <td><span class="tag-usage-outline">${escapeHtml(cue.usage_type || '—')}</span></td>
        <td class="font-mono">${escapeHtml(cue.timecode_in)} → ${escapeHtml(cue.timecode_out)}</td>
        <td class="font-mono" style="font-weight: 800;">${escapeHtml(cue.duration_timecode)}</td>
        <td>${writersFormatted}</td>
        <td style="text-align: center;">${writerPill}</td>
        <td>${pubsFormatted}</td>
        <td style="text-align: center;">${pubPill}</td>
        <td>${statusTag}</td>
        <td>
          <button class="btn-inspect-action" type="button" onclick="showSplitModal(${cue.cue_number})">Details</button>
        </td>
      </tr>
    `;
  }).join('');
}

window.showSplitModal = function showSplitModal(cueNumber) {
  const cue = currentCues.find((c) => c.cue_number === cueNumber);
  if (!cue) return;

  const modalOverlay = document.getElementById('splitModalOverlay');
  const titleElem = document.getElementById('modalHeaderTitle');
  const bodyElem = document.getElementById('modalBodyContent');

  if (titleElem) {
    titleElem.textContent = `Cue ${String(cue.cue_number).padStart(3, '0')}: ${cue.title}`;
  }

  const writersList = (cue.writers || []).map((w) => {
    const shareStr = (w.share !== null && w.share !== undefined)
      ? `${w.share}%`
      : `Undisclosed${cue.estimated_equal_share != null ? ` (est. ${cue.estimated_equal_share}%)` : ''}`;
    return `
      <div class="holder-row">
        <span><strong>${escapeHtml(w.name)}</strong> · ${escapeHtml(w.role || 'Composer')}</span>
        <span>${escapeHtml(w.pro || '—')} · <strong>${escapeHtml(shareStr)}</strong></span>
      </div>
    `;
  }).join('');

  const pubsList = (cue.publishers || []).map((p) => {
    const shareStr = (p.share !== null && p.share !== undefined) ? `${p.share}%` : 'Undisclosed';
    return `
      <div class="holder-row">
        <span><strong>${escapeHtml(p.name)}</strong> · ${escapeHtml(p.role || 'Publisher')}</span>
        <span>${escapeHtml(p.pro || '—')} · <strong>${escapeHtml(shareStr)}</strong></span>
      </div>
    `;
  }).join('');

  const writerWidth = Math.max(0, Math.min(Number(cue.total_writer_share) || 0, 100));
  const pubWidth = Math.max(0, Math.min(Number(cue.total_publisher_share) || 0, 100));
  const needsSignOff = !cue.is_verified && !cue.supervisor_signed_off && (
    cue.split_status === 'PRO_REGISTERED_SPLIT_UNDISCLOSED' ||
    cue.split_status === 'PARTIAL_PUBLISHER_CLAIM_FLAGGED'
  );

  bodyElem.innerHTML = `
    <div class="modal-metadata-grid">
      <div class="modal-meta-box">
        <small>Work ID</small>
        <strong>${escapeHtml(cue.work_id || 'Not found')}</strong>
      </div>
      <div class="modal-meta-box">
        <small>ISWC</small>
        <strong>${escapeHtml(cue.iswc || 'Not found')}</strong>
      </div>
      <div class="modal-meta-box">
        <small>Duration</small>
        <strong>${escapeHtml(cue.duration_timecode)} (${escapeHtml(cue.duration_frames)} frames)</strong>
      </div>
    </div>

    <div>
      <div class="split-labels">
        <span>Writer share: ${escapeHtml(cue.total_writer_share)}%</span>
        <span>Publisher share: ${escapeHtml(cue.total_publisher_share)}%</span>
      </div>
      <div class="swiss-split-bar" aria-hidden="true">
        <div class="bar-segment-writers" style="width: ${writerWidth}%;"></div>
        <div class="bar-segment-publishers" style="width: ${pubWidth}%;"></div>
      </div>
    </div>

    <div>
      <div class="section-label">Writers</div>
      ${writersList || '<p class="muted">No writers registered</p>'}
    </div>

    <div>
      <div class="section-label">Publishers</div>
      ${pubsList || '<p class="muted">No publishers registered</p>'}
    </div>

    ${cue.split_status === 'PRO_REGISTERED_SPLIT_UNDISCLOSED' && !cue.supervisor_signed_off ? `
      <div class="notice notice-warn">
        <strong>Pending music supervisor sign-off</strong>
        <p>PRO registration is present, but public split percentages are undisclosed. This cue counts as 0% cleared until signed off.</p>
      </div>
    ` : ''}

    ${cue.split_status === 'PARTIAL_PUBLISHER_CLAIM_FLAGGED' && !cue.supervisor_signed_off ? `
      <div class="notice notice-bad">
        <strong>Incomplete publisher claim</strong>
        <p>Publisher shares sum to ${escapeHtml(cue.total_publisher_share)}% (less than 100%). Clearance is incomplete.</p>
      </div>
    ` : ''}

    ${cue.supervisor_signed_off ? `
      <div class="notice notice-ok">
        <strong>Supervisor signed off</strong>
        <p>Approved by ${escapeHtml(cue.signed_off_by || 'Music Supervisor')}${cue.signed_off_at ? ` at ${escapeHtml(cue.signed_off_at)}` : ''}.</p>
      </div>
    ` : ''}

    <div class="audit-box">
      <div><strong>Provenance:</strong> ${escapeHtml(cue.provenance || cue.source_type || 'Unknown')}</div>
      <div><strong>Invoke mode:</strong> ${escapeHtml(cue.invoke_mode || '—')}</div>
      <div><strong>Parallel Search ID:</strong> ${escapeHtml(cue.search_id || '—')}${cue.latency_ms != null ? ` (${escapeHtml(cue.latency_ms)}ms)` : ''}</div>
      <div><strong>Parallel Extract ID:</strong> ${escapeHtml(cue.extract_id || '—')}</div>
      <div><strong>Extracted URLs:</strong> ${(cue.extracted_urls && cue.extracted_urls.length) ? escapeHtml(cue.extracted_urls.join(' | ')) : '—'}</div>
      <div><strong>Notes:</strong> ${escapeHtml(cue.confidence_notes || cue.source_reference || '—')}</div>
      ${cue.fallback_reason ? `<div class="status-warn"><strong>ADK fallback:</strong> ${escapeHtml(cue.fallback_reason)}</div>` : ''}
    </div>

    ${(cue.excerpts && cue.excerpts.length) ? `
      <div class="excerpts-box">
        <strong>Parallel excerpts used for grounding</strong>
        <ol>
          ${cue.excerpts.slice(0, 6).map((ex) => `<li>${escapeHtml(String(ex).slice(0, 280))}</li>`).join('')}
        </ol>
      </div>
    ` : ''}

    <div class="modal-actions">
      ${needsSignOff ? `
        <button class="btn-export-trigger" type="button" onclick="confirmSplitSignOff(${cue.cue_number})">
          Confirm &amp; sign off
        </button>
      ` : ''}
      <button class="btn-inspect-action" type="button" onclick="document.getElementById('splitModalOverlay').classList.remove('show')">
        Close
      </button>
    </div>
  `;

  if (modalOverlay) modalOverlay.classList.add('show');
};

window.confirmSplitSignOff = async function confirmSplitSignOff(cueNumber) {
  const cue = currentCues.find((c) => c.cue_number === cueNumber);
  if (!cue) return;

  try {
    const res = await fetch('/api/sign-off', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cue_number: cueNumber,
        signed_off_by: 'Music Supervisor',
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      logTerminal('term-flagged', `Sign-off failed for cue ${String(cueNumber).padStart(2, '0')}: ${err.detail || res.status}`);
      return;
    }

    const manifest = await res.json();
    currentCues = manifest.cues || [];
    hasClearanceResult = currentCues.length > 0;
    setExportEnabled(hasClearanceResult);
    updateCompliance(manifest.compliance_score ?? 0);
    renderCueMatrix();

    logTerminal(
      'term-verified',
      `Cue ${String(cueNumber).padStart(2, '0')} (${cue.title}) signed off. Exports updated. Compliance ${manifest.compliance_score}%.`
    );

    document.getElementById('splitModalOverlay')?.classList.remove('show');
  } catch (err) {
    logTerminal('term-flagged', `Sign-off request failed: ${err.message}`);
  }
};
