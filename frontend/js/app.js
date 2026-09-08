// CueClear studio controller — clearance workflow only

const STUDIO_STORAGE_KEY = 'cueclear_studio_v1';

let currentCues = [];
let currentClips = [];
let currentProjectTitle = 'Production Sequence';
let currentComplianceScore = null;
let activeFilter = 'all';
let isRunning = false;
let sampleDataMap = {};
let activeReelId = null;
let hasTimelineLoaded = false;
let hasClearanceResult = false;
let activeStreamAbort = null;
let streamCompletedCleanly = false;

document.addEventListener('DOMContentLoaded', async () => {
  initUI();
  clearTerminal();
  logTerminal('term-sys', 'Select a sample timeline or upload an EDL/XML file to begin.');
  await refreshHealth({ quiet: true });
  const restored = restoreStudioState();
  await loadSampleTimelines({ skipAutoSelect: restored });
  if (!restored && sampleDataMap.sample_mixed) {
    await switchReel('sample_mixed');
  }
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

  ['exportExcel', 'exportCisac', 'exportJson'].forEach((id) => {
    document.getElementById(id)?.addEventListener('click', async (e) => {
      if (!hasClearanceResult || !currentCues.length) return;
      e.preventDefault();
      const ok = await ensureServerManifest();
      if (!ok) {
        logTerminal('term-flagged', 'Could not sync cue sheet to server for export. Try running clearance again.');
        return;
      }
      const href = e.currentTarget.getAttribute('href');
      if (href) window.location.href = href;
    });
  });
}

async function refreshHealth(options = {}) {
  const quiet = Boolean(options.quiet);
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
    if (!quiet) {
      clearTerminal();
      logTerminal('term-sys', 'Select a sample timeline or upload an EDL/XML file to begin.');
    }
  } catch (err) {
    if (geminiEl) geminiEl.textContent = 'UNREACHABLE';
    if (parallelEl) parallelEl.textContent = 'UNREACHABLE';
    if (!quiet) {
      clearTerminal();
      logTerminal('term-flagged', `Could not reach API health endpoint: ${err.message}`);
    }
  }
}

async function loadSampleTimelines(options = {}) {
  try {
    const res = await fetch('/api/sample-timelines', { credentials: 'same-origin' });
    const samples = await res.json();
    samples.forEach((s) => {
      sampleDataMap[s.id] = s;
    });
    if (!options.skipAutoSelect) {
      if (sampleDataMap.sample_mixed) {
        await switchReel('sample_mixed');
      } else if (sampleDataMap.sample_trailer) {
        await switchReel('sample_trailer');
      }
    }
  } catch (err) {
    logTerminal('term-flagged', `Failed to load sample timelines: ${err.message}`);
  }
}

async function switchReel(reelId) {
  if (isRunning) {
    logTerminal('term-flagged', 'Clearance is still running. Wait for it to finish before switching samples.');
    return;
  }

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
    clearTerminal();
    logTerminal('term-flagged', `Sample "${reelId}" is not available.`);
    return;
  }

  clearTerminal();
  logTerminal('term-sys', `Loading sample: ${sample.name}…`);

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
    const readyHint = reelId === 'sample_mixed'
      ? 'Recommended demo: Case A cleared · Case B pending · unresolved non-catalog.'
      : 'Ready to clear this timeline.';
    applyTimelineMeta(data, readyHint, sample.name);
    resetClearanceState({ persist: true });
    clearTerminal();
    logTerminal('term-sys', `Selected: ${sample.name}`);
    logTerminal('term-sys', `${data.total_clips} audio cue(s) ready. Click Run rights clearance.`);
    if (reelId === 'sample_mixed') {
      logTerminal('term-sys', 'Demo path: Midnight City (Case A) → Exit Music (Case B) → Unknown cue (unresolved).');
    }
    persistStudioState();
  } catch (err) {
    clearTerminal();
    logTerminal('term-flagged', `Failed to ingest sample: ${err.message}`);
  }
}

async function handleFileUpload(file) {
  if (isRunning) {
    logTerminal('term-flagged', 'Clearance is still running. Wait for it to finish before uploading.');
    return;
  }

  activeReelId = 'custom';
  document.querySelectorAll('.btn-reel-select').forEach((b) => b.classList.remove('active'));
  document.getElementById('btnReelCustom')?.classList.add('active');

  const ext = (file.name.split('.').pop() || 'FILE').toUpperCase();
  const activeLabel = document.getElementById('activeTimelineLabel');
  if (activeLabel) activeLabel.textContent = `${file.name} (.${ext.toLowerCase()})`;

  clearTerminal();
  logTerminal('term-sys', `Uploading ${file.name}…`);

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
    const projectTitle = file.name.replace(/\.[^/.]+$/, '');
    applyTimelineMeta(data, 'Ready to clear this timeline.', projectTitle);
    resetClearanceState({ persist: true });
    clearTerminal();
    logTerminal('term-pro', `Selected: ${file.name}`);
    logTerminal('term-sys', `${data.total_clips} audio cue(s) ready. Click Run rights clearance.`);
    persistStudioState();
  } catch (err) {
    clearTerminal();
    logTerminal('term-flagged', `Timeline upload failed: ${err.message}`);
  }
}

function applyTimelineMeta(data, readyHint, projectTitle) {
  currentClips = Array.isArray(data.clips) ? data.clips : [];
  currentProjectTitle = projectTitle || data.project_title || currentProjectTitle || 'Production Sequence';
  hasTimelineLoaded = currentClips.length > 0;
  document.getElementById('valClipCount').textContent = hasTimelineLoaded
    ? `${currentClips.length} cue${currentClips.length === 1 ? '' : 's'}`
    : '0 cues';
  document.getElementById('valFps').textContent = hasTimelineLoaded ? `${deriveFps(currentClips)} fps` : '—';
  document.getElementById('valDuration').textContent = hasTimelineLoaded
    ? computeSequenceDuration(currentClips)
    : '—';
  setResolveEnabled(
    hasTimelineLoaded,
    hasTimelineLoaded
      ? (readyHint || 'Ready to clear this timeline.')
      : 'Load a timeline first.'
  );
}

function resetClearanceState(options = {}) {
  currentCues = [];
  hasClearanceResult = false;
  currentComplianceScore = null;
  setExportEnabled(false);
  updateCompliance(null);
  renderCueMatrix();
  document.getElementById('topbarStatusVal').textContent = 'READY';
  document.getElementById('agentTelemetryPill').textContent = 'IDLE';
  if (options.persist) persistStudioState();
}

function persistStudioState() {
  try {
    const activeLabel = document.getElementById('activeTimelineLabel');
    const payload = {
      version: 1,
      savedAt: new Date().toISOString(),
      activeReelId,
      currentProjectTitle,
      currentClips,
      currentCues,
      currentComplianceScore,
      hasTimelineLoaded,
      hasClearanceResult,
      timelineLabel: activeLabel ? activeLabel.textContent : '',
    };
    localStorage.setItem(STUDIO_STORAGE_KEY, JSON.stringify(payload));
  } catch (_err) {
    // Ignore quota / private-mode failures.
  }
}

function restoreStudioState() {
  try {
    const raw = localStorage.getItem(STUDIO_STORAGE_KEY);
    if (!raw) return false;
    const saved = JSON.parse(raw);
    if (!saved || !Array.isArray(saved.currentCues) || saved.currentCues.length === 0) {
      return false;
    }

    activeReelId = saved.activeReelId || null;
    currentProjectTitle = saved.currentProjectTitle || 'Production Sequence';
    currentClips = Array.isArray(saved.currentClips) ? saved.currentClips : [];
    currentCues = saved.currentCues;
    currentComplianceScore = saved.currentComplianceScore;
    hasTimelineLoaded = Boolean(saved.hasTimelineLoaded) || currentClips.length > 0;
    hasClearanceResult = true;

    document.querySelectorAll('.btn-reel-select').forEach((b) => b.classList.remove('active'));
    if (activeReelId === 'sample_trailer') document.getElementById('btnReelTrailer')?.classList.add('active');
    if (activeReelId === 'sample_indie') document.getElementById('btnReelIndie')?.classList.add('active');
    if (activeReelId === 'sample_mixed') document.getElementById('btnReelMixed')?.classList.add('active');
    if (activeReelId === 'custom') document.getElementById('btnReelCustom')?.classList.add('active');

    const activeLabel = document.getElementById('activeTimelineLabel');
    if (activeLabel && saved.timelineLabel) activeLabel.textContent = saved.timelineLabel;

    document.getElementById('valClipCount').textContent = hasTimelineLoaded
      ? `${currentClips.length || currentCues.length} cue(s)`
      : '0 cues';
    document.getElementById('valFps').textContent = currentClips.length ? `${deriveFps(currentClips)} fps` : '—';
    document.getElementById('valDuration').textContent = currentClips.length
      ? computeSequenceDuration(currentClips)
      : '—';

    updateCompliance(currentComplianceScore);
    renderCueMatrix();
    setExportEnabled(true);
    setResolveEnabled(hasTimelineLoaded, 'Restored previous clearance. Run again anytime.');
    document.getElementById('topbarStatusVal').textContent = 'CLEARED';
    document.getElementById('agentTelemetryPill').textContent = 'IDLE';

    clearTerminal();
    logTerminal('term-verified', `Restored previous cue sheet (${currentCues.length} cues).`);
    logTerminal('term-sys', `Project: ${currentProjectTitle}`);
    logTerminal('term-sys', 'Select another sample to start fresh, or run clearance again.');
    return true;
  } catch (_err) {
    return false;
  }
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

async function startClearanceStream() {
  if (isRunning) return;
  if (!hasTimelineLoaded || !currentClips.length) {
    logTerminal('term-flagged', 'Load a timeline before running clearance.');
    return;
  }

  if (activeStreamAbort) {
    activeStreamAbort.abort();
    activeStreamAbort = null;
  }

  isRunning = true;
  streamCompletedCleanly = false;
  currentCues = [];
  hasClearanceResult = false;
  currentComplianceScore = null;
  setExportEnabled(false);
  updateCompliance(null);
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

  clearTerminal();
  logTerminal('term-sys', `Starting rights clearance for ${currentProjectTitle}…`);
  logTerminal('term-sys', `${currentClips.length} timeline cue(s) in this run.`);

  const controller = new AbortController();
  activeStreamAbort = controller;

  try {
    const res = await fetch('/api/stream-clearance', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        project_title: currentProjectTitle,
        clips: currentClips,
      }),
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = `Clearance failed (${res.status})`;
      try {
        const errBody = await res.json();
        detail = errBody.detail || detail;
      } catch (_e) {
        // ignore
      }
      throw new Error(detail);
    }

    if (!res.body) {
      throw new Error('Browser could not open a streaming response body.');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let splitAt = buffer.indexOf('\n\n');
      while (splitAt !== -1) {
        const rawEvent = buffer.slice(0, splitAt);
        buffer = buffer.slice(splitAt + 2);
        const dataLines = rawEvent
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart());
        if (dataLines.length) {
          try {
            const payload = JSON.parse(dataLines.join('\n'));
            handleAgentEvent(payload);
          } catch (e) {
            console.error('SSE parse error', e);
          }
        }
        splitAt = buffer.indexOf('\n\n');
      }
    }

    if (isRunning && !streamCompletedCleanly) {
      if (currentCues.length > 0) {
        hasClearanceResult = true;
        setExportEnabled(true);
        persistStudioState();
        logTerminal('term-flagged', 'Stream ended early, but partial cue results were kept.');
        finishRun(true);
      } else {
        logTerminal('term-flagged', 'Clearance stream disconnected before completion.');
        finishRun(false);
      }
    }
  } catch (err) {
    if (err && err.name === 'AbortError') {
      return;
    }
    if (isRunning) {
      logTerminal('term-flagged', `Clearance stream error: ${err.message || err}`);
      if (currentCues.length > 0) {
        hasClearanceResult = true;
        setExportEnabled(true);
        persistStudioState();
        finishRun(true);
      } else {
        finishRun(false);
      }
    }
  } finally {
    if (activeStreamAbort === controller) {
      activeStreamAbort = null;
    }
  }
}

function handleAgentEvent(event) {
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
        currentComplianceScore = event.data.compliance_score;
        updateCompliance(event.data.compliance_score);
        if (Array.isArray(event.data.cues) && event.data.cues.length) {
          currentCues = event.data.cues;
          renderCueMatrix();
        }
      }
      hasClearanceResult = currentCues.length > 0;
      setExportEnabled(hasClearanceResult);
      streamCompletedCleanly = true;
      persistStudioState();
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
  persistStudioState();
}

function finishRun(success) {
  isRunning = false;
  const statusPill = document.getElementById('agentTelemetryPill');
  const topbarStatus = document.getElementById('topbarStatusVal');
  const btnResolve = document.getElementById('btnResolveRights');

  if (statusPill) statusPill.textContent = 'IDLE';
  if (topbarStatus) topbarStatus.textContent = success && hasClearanceResult ? 'CLEARED' : 'READY';
  if (btnResolve) {
    btnResolve.disabled = !hasTimelineLoaded;
    btnResolve.textContent = 'Run rights clearance again';
  }
  setResolveHelper(
    hasClearanceResult
      ? 'Inspect cues below. Pending items can be signed off before export.'
      : 'Load a timeline, then run clearance.'
  );
  persistStudioState();
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

const EXCERPT_CHROME_PATTERNS = [
  /please select title/gi,
  /songview logo/gi,
  /tailor your search for the info you want/gi,
  /more detailed information with songview technology[\s\S]{0,240}/gi,
  /with songview technology integrated into the search tools[\s\S]{0,280}/gi,
  /update:\s*songview is expanding[\s\S]{0,260}/gi,
  /the four major u\.?s\.? pros[\s\S]{0,260}/gi,
  /title performer writer\/composer publisher bmi work id iswc/gi,
  /see a combined view of more than[\s\S]{0,200}/gi,
  /see the ownership of all musical works covered under a bmi license[\s\S]{0,200}/gi,
];

function cleanExcerptText(raw) {
  let text = String(raw || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text) return '';

  EXCERPT_CHROME_PATTERNS.forEach((pattern) => {
    text = text.replace(pattern, ' ');
  });

  text = text
    .replace(/\b(Title|Performer|Writer\/Composer|Publisher|BMI Work ID|ISWC)\b(?:\s+\1\b){1,6}/gi, '$1')
    .replace(/\s+/g, ' ')
    .replace(/\s([,.;:])/g, '$1')
    .trim();

  return text;
}

function scoreExcerptText(text, cueTitle) {
  const lower = text.toLowerCase();
  let score = 0;
  const signals = [
    'iswc', 'work id', 'bmi', 'ascap', 'songview', 'writer', 'composer',
    'publisher', 'share', 'repertory', 'undisclosed', 'ipi',
  ];
  signals.forEach((signal) => {
    if (lower.includes(signal)) score += 3;
  });
  if (/\d+(\.\d+)?\s*%/.test(text)) score += 4;
  if (/t-\d{3}\.\d{3}\.\d{3}-\d/i.test(text)) score += 5;
  if (cueTitle) {
    const titleToken = String(cueTitle).toLowerCase().slice(0, 18);
    if (titleToken && lower.includes(titleToken)) score += 4;
  }
  if (lower.includes('wikiwand') || lower.includes('romeo + juliet')) score -= 2;
  if (lower.includes('please select') || lower.includes('logo')) score -= 4;
  // Prefer denser evidence snippets over giant page dumps.
  if (text.length > 900) score -= 2;
  if (text.length < 40) score -= 3;
  return score;
}

function prepareExcerptsForDisplay(excerpts, cueTitle) {
  const cleaned = (excerpts || [])
    .map((ex) => cleanExcerptText(ex))
    .filter((text) => text.length >= 24);

  const deduped = [];
  cleaned.forEach((text) => {
    const key = text.slice(0, 120).toLowerCase();
    if (!deduped.some((existing) => existing.slice(0, 120).toLowerCase() === key)) {
      deduped.push(text);
    }
  });

  return deduped
    .map((text) => {
      const clipped = text.length > 1400 ? `${text.slice(0, 1400).trim()}…` : text;
      return { text: clipped, score: scoreExcerptText(clipped, cueTitle) };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 8)
    .map((item) => item.text);
}

let activeExcerptStore = [];

function renderExcerptsHtml(excerpts, cueTitle) {
  const prepared = prepareExcerptsForDisplay(excerpts, cueTitle);
  activeExcerptStore = prepared;
  if (!prepared.length) {
    return `
      <div class="excerpts-box">
        <strong>Parallel excerpts used for grounding</strong>
        <span class="excerpts-box-hint">No clean PRO evidence snippets were available for this cue.</span>
      </div>
    `;
  }

  const previewLimit = 220;
  const items = prepared.map((fullText, index) => {
    const needsToggle = fullText.length > previewLimit;
    const preview = needsToggle ? `${fullText.slice(0, previewLimit).trim()}…` : fullText;
    return `
      <li class="excerpt-item ${needsToggle ? 'is-collapsed' : 'is-expanded'}" data-excerpt-index="${index}">
        <span class="excerpt-item-label">Evidence snippet</span>
        <div class="excerpt-item-text">${escapeHtml(preview)}</div>
        ${needsToggle ? `
          <button class="excerpt-toggle" type="button" onclick="toggleExcerptExpand(this)">Read more</button>
        ` : ''}
      </li>
    `;
  }).join('');

  return `
    <div class="excerpts-box">
      <strong>Parallel excerpts used for grounding</strong>
      <span class="excerpts-box-hint">Cleaned PRO evidence first. Use Read more for the full snippet.</span>
      <ol>${items}</ol>
    </div>
  `;
}

window.toggleExcerptExpand = function toggleExcerptExpand(button) {
  const item = button?.closest('.excerpt-item');
  const textEl = item?.querySelector('.excerpt-item-text');
  if (!item || !textEl) return;

  const index = Number(item.dataset.excerptIndex);
  const fullText = activeExcerptStore[index] || '';
  if (!fullText) return;

  const expanding = item.classList.contains('is-collapsed');
  if (expanding) {
    item.classList.remove('is-collapsed');
    item.classList.add('is-expanded');
    textEl.textContent = fullText;
    button.textContent = 'Show less';
  } else {
    item.classList.add('is-collapsed');
    item.classList.remove('is-expanded');
    const previewLimit = 220;
    textEl.textContent = `${fullText.slice(0, previewLimit).trim()}…`;
    button.textContent = 'Read more';
  }
};

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

    const provenanceBits = [];
    if (cue.provenance) {
      provenanceBits.push(`<span class="tag-telemetry-chip provenance" title="Provenance">${escapeHtml(String(cue.provenance).replace(/_/g, ' '))}</span>`);
    }
    if (cue.invoke_mode) {
      provenanceBits.push(`<span class="tag-telemetry-chip invoke" title="ADK Parallel Search invoke mode">S ${escapeHtml(cue.invoke_mode)}</span>`);
    }
    if (cue.audit_invoke_mode) {
      provenanceBits.push(`<span class="tag-telemetry-chip invoke" title="ADK split audit invoke mode">A ${escapeHtml(cue.audit_invoke_mode)}</span>`);
    }
    if (cue.search_id) {
      provenanceBits.push(`<span class="tag-telemetry-chip idchip" title="Parallel Search ID">S ${escapeHtml(String(cue.search_id).slice(0, 10))}</span>`);
    }
    if (cue.extract_id) {
      provenanceBits.push(`<span class="tag-telemetry-chip idchip" title="Parallel Extract ID">E ${escapeHtml(String(cue.extract_id).slice(0, 10))}</span>`);
    }
    const provenanceRow = provenanceBits.length
      ? `<div class="cue-provenance-row">${provenanceBits.join('')}</div>`
      : '';

    return `
      <tr>
        <td class="font-mono" style="font-weight: 800;">${String(cue.cue_number).padStart(3, '0')}</td>
        <td>
          <strong style="font-size: 13px; font-weight: 800; display: block;">${escapeHtml(cue.title)}</strong>
          <span style="font-size: 11px; color: var(--swiss-gray-mid); display: block;">${escapeHtml(cue.artist || 'Unknown artist')}</span>
          <div>${sourceTag}</div>
          ${provenanceRow}
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
      <div><strong>Search invoke mode:</strong> ${escapeHtml(cue.invoke_mode || '—')}</div>
      <div><strong>Audit invoke mode:</strong> ${escapeHtml(cue.audit_invoke_mode || '—')}</div>
      <div><strong>Parallel Search ID:</strong> ${escapeHtml(cue.search_id || '—')}${cue.latency_ms != null ? ` (${escapeHtml(cue.latency_ms)}ms)` : ''}</div>
      <div><strong>Parallel Extract ID:</strong> ${escapeHtml(cue.extract_id || '—')}</div>
      <div><strong>Extracted URLs:</strong> ${(cue.extracted_urls && cue.extracted_urls.length) ? escapeHtml(cue.extracted_urls.join(' | ')) : '—'}</div>
      <div><strong>Notes:</strong> ${escapeHtml(cue.confidence_notes || cue.source_reference || '—')}</div>
      ${cue.fallback_reason ? `<div class="status-warn"><strong>ADK search fallback:</strong> ${escapeHtml(cue.fallback_reason)}</div>` : ''}
      ${cue.audit_fallback_reason ? `<div class="status-warn"><strong>ADK audit fallback:</strong> ${escapeHtml(cue.audit_fallback_reason)}</div>` : ''}
    </div>

    ${(cue.excerpts && cue.excerpts.length) ? renderExcerptsHtml(cue.excerpts, cue.title) : ''}

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
    const synced = await ensureServerManifest();
    if (!synced) {
      logTerminal('term-flagged', 'Could not sync cue sheet before sign-off. Try again.');
      return;
    }

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
    currentComplianceScore = manifest.compliance_score ?? 0;
    setExportEnabled(hasClearanceResult);
    updateCompliance(currentComplianceScore);
    renderCueMatrix();
    persistStudioState();

    logTerminal(
      'term-verified',
      `Cue ${String(cueNumber).padStart(2, '0')} (${cue.title}) signed off. Exports updated. Compliance ${manifest.compliance_score}%.`
    );

    document.getElementById('splitModalOverlay')?.classList.remove('show');
  } catch (err) {
    logTerminal('term-flagged', `Sign-off request failed: ${err.message}`);
  }
};

async function ensureServerManifest() {
  if (!currentCues.length) return false;
  try {
    const total = currentCues.length;
    const cleared = currentCues.filter((c) => c.is_verified).length;
    const res = await fetch('/api/restore-manifest', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_title: currentProjectTitle || 'Production Sequence',
        cues: currentCues,
        total_cues: total,
        cleared_cues: cleared,
        flagged_cues: total - cleared,
        compliance_score: currentComplianceScore ?? (total ? Math.round((cleared / total) * 1000) / 10 : 100),
      }),
    });
    return res.ok;
  } catch (_err) {
    return false;
  }
}
