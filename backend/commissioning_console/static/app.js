'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const model = { authenticated: false, status: null, routes: [], route: null, step: null,
    original: null, stages: [], expectedVisual: '', draft: null, dirty: false,
    busy: false, polling: false, cameraBusy: false, cameraUrl: null, statusAt: 0,
    view: 'camera', before: null, after: null };
  let initialToken = '';
  if (location.hash) {
    const fragment = new URLSearchParams(location.hash.slice(1));
    initialToken = fragment.get('token') || (location.hash.slice(1).includes('=') ? '' : location.hash.slice(1));
    history.replaceState(null, '', location.pathname + location.search);
  }
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const number = (value, digits = 3) => finite(value) ? value.toFixed(digits) : '—';
  const poseText = (value) => Array.isArray(value) ? value.map((x) => number(x)).join(', ') : '미확인';
  const requestId = () => {
    if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    return Array.from(bytes, (byte, i) => `${[4, 6, 8, 10].includes(i) ? '-' : ''}${byte.toString(16).padStart(2, '0')}`).join('');
  };
  const owned = () => model.status?.ownership?.owned === true;
  const runActive = () => model.status?.run?.active === true || model.status?.run?.running === true ||
    ['EXECUTING', 'PREPARING', 'OBSERVING', 'STOPPING', 'RUNNING'].includes(String(model.status?.state || '').toUpperCase());
  const freshStatus = () => model.status && Date.now() - model.statusAt < 6500;
  const signalPending = () => !!model.status?.run?.signal_gate && model.status.run.signal_gate.accepted !== true && model.status.run.signal_gate.admitted !== true;
  const hasNativeReceipt = () => !!model.status?.run?.receipt;
  const changes = () => {
    if (!model.original) return [];
    const result = [];
    model.stages.forEach((stage, index) => ['X', 'Y'].forEach((axis, i) => {
      const original = model.original.stages[index]?.target_base?.[i];
      if (stage.target_base[i] !== original) result.push({ label: `${stage.id} · ${axis}`, before: original, after: stage.target_base[i] });
    }));
    if (model.expectedVisual !== (model.original.expected_visual || '')) result.push({ label: '기대 관측', before: model.original.expected_visual || '', after: model.expectedVisual });
    return result;
  };
  const setText = (id, text) => { $(id).textContent = text; };
  function message(text, error = false) {
    setText('operation-message', text);
    $('message-dot').style.background = error ? '#ba7560' : '#79a08d';
  }
  async function api(path, method = 'GET', data, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, { method, credentials: 'same-origin', cache: 'no-store',
        headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
        body: data === undefined ? undefined : JSON.stringify(data), signal: controller.signal });
      const contentType = response.headers.get('content-type') || '';
      const value = contentType.includes('json') ? await response.json() : null;
      if (!response.ok) {
        const detail = value?.error || value?.detail || value || {};
        const error = new Error(detail.message || detail.code || `HTTP ${response.status}`);
        error.code = detail.code || `HTTP_${response.status}`;
        error.status = response.status;
        throw error;
      }
      return value;
    } catch (error) {
      if (error.name === 'AbortError') {
        const delayed = new Error(method === 'GET' ? '서버 상태 응답이 지연되고 있습니다.' : '응답 지연: 실행 여부를 확인 중입니다. 같은 작업을 다시 누르지 마세요.');
        delayed.code = 'RESPONSE_DELAYED';
        throw delayed;
      }
      throw error;
    } finally { clearTimeout(timer); }
  }
  function showLogin(text = '') {
    model.authenticated = false;
    $('login-layer').hidden = false;
    $('console').inert = true;
    setText('login-error', text);
    $('stop-button').disabled = true;
  }
  async function enterConsole() {
    model.authenticated = true;
    $('login-layer').hidden = true;
    $('console').inert = false;
    await Promise.allSettled([pollStatus(), loadRoutes()]);
    refreshCamera();
  }
  async function login(token) {
    const submit = $('login-form').querySelector('button');
    submit.disabled = true;
    setText('login-error', '');
    try {
      await api('/api/login', 'POST', { token });
      $('token').value = '';
      await enterConsole();
    } catch (error) { showLogin(`${error.code || 'LOGIN_FAILED'} · ${error.message}`); }
    finally { submit.disabled = false; }
  }
  async function pollStatus() {
    if (!model.authenticated || model.polling) return;
    model.polling = true;
    try {
      const status = await api('/api/status');
      model.status = status;
      model.statusAt = Date.now();
      renderStatus();
    } catch (error) {
      if (error.status === 401 || error.status === 403) showLogin('인증이 필요합니다.');
      else {
        $('connection').className = 'connection error';
        $('connection').lastChild.textContent = '서버 응답 지연';
        message(`${error.code || 'STATUS_UNAVAILABLE'} · 현재 실행 여부를 확인할 수 없습니다.`, true);
        updateControls();
      }
    } finally { model.polling = false; }
  }
  async function loadRoutes() {
    try {
      const value = await api('/api/routes');
      model.routes = Array.isArray(value?.routes) ? value.routes.map((route) => ({ ...route,
        steps: [...(route.steps || []), ...(route.empty_return || []).map((step) => ({ ...step, console_return: true }))] })) : [];
      renderRoutes();
      if (!model.route && model.routes.length) selectRoute(model.routes[0].code);
    } catch (error) {
      if (error.status === 401) showLogin('인증이 필요합니다.');
      else message(`${error.code || 'ROUTES_UNAVAILABLE'} · ${error.message}`, true);
    }
  }
  function renderRoutes() {
    const tabs = $('route-tabs');
    tabs.replaceChildren();
    model.routes.forEach((route) => {
      const button = document.createElement('button');
      button.textContent = route.code;
      button.className = model.route?.code === route.code ? 'selected' : '';
      button.setAttribute('aria-pressed', String(model.route?.code === route.code));
      button.addEventListener('click', () => selectRoute(route.code));
      tabs.append(button);
    });
  }
  function selectRoute(code) {
    if (model.dirty && !confirm('저장하지 않은 변경을 버리고 경로를 바꾸시겠습니까?')) return;
    model.route = model.routes.find((route) => route.code === code) || null;
    model.step = null;
    renderRoutes();
    setText('route-title', model.route?.destination || '실제 경로 없음');
    setText('route-count', model.route ? `${model.route.steps.length} steps` : '—');
    if (model.route?.steps.length) selectStep(model.route.steps[0].id, true);
    else { renderSteps(); resetEditor(); }
  }
  function completedStepIds() {
    const result = new Set();
    const run = model.status?.run;
    if (run?.route !== model.route?.code) return result;
    (run.completed_steps || []).forEach((value) => result.add(typeof value === 'string' ? value : value.step_id || value.id));
    if (run.step_id && run.receipt) result.add(run.step_id);
    let requested = null;
    (model.status.history || []).forEach((event) => {
      if (event.kind === 'unit_requested') requested = event.value?.request || null;
      if (event.kind === 'unit_native_complete' && requested?.route === model.route?.code) result.add(requested.step_id);
      if (event.kind === 'unit_interrupted') requested = null;
    });
    return result;
  }
  function renderSteps() {
    const list = $('step-list');
    list.replaceChildren();
    const completed = completedStepIds();
    (model.route?.steps || []).forEach((step, index) => {
      const button = document.createElement('button');
      button.className = `step-item${model.step?.id === step.id ? ' selected' : ''}${completed.has(step.id) ? ' completed' : ''}`;
      if (model.step?.id === step.id) button.setAttribute('aria-current', 'step');
      const badge = document.createElement('span'); badge.className = 'step-number'; badge.textContent = completed.has(step.id) ? '✓' : String(index + 1).padStart(2, '0');
      const text = document.createElement('span');
      const title = document.createElement('strong'); title.textContent = step.console_return ? '빈 공구 START 복귀' : step.id;
      const detail = document.createElement('small'); detail.textContent = `${step.console_return ? step.id : step.empty_tool ? '빈 공구' : '접근·접촉·후퇴 포함'} · ${(step.stages || []).length} segments${step.signal_gate ? ' · 신호' : ''}${step.at_goal ? ' · 도착' : ''}`;
      text.append(title, detail); button.append(badge, text);
      button.addEventListener('click', () => selectStep(step.id)); list.append(button);
    });
  }
  function resetEditor() {
    model.original = null; model.stages = []; model.expectedVisual = ''; model.dirty = false; model.draft = null;
    $('coordinate-table').replaceChildren();
    setText('selected-step', '단계를 선택하세요');
    $('expected-visual').value = ''; $('change-reason').value = '';
    updateControls(); renderPath();
  }
  function selectStep(id, skipPrompt = false) {
    if (!skipPrompt && model.dirty && !confirm('저장하지 않은 변경을 버리고 단계를 바꾸시겠습니까?')) return;
    const step = model.route?.steps.find((entry) => entry.id === id);
    if (!step) return;
    model.step = step; model.original = clone(step); model.stages = clone(step.stages || []);
    model.expectedVisual = step.expected_visual || ''; model.dirty = false; model.draft = null;
    $('expected-visual').value = model.expectedVisual; $('change-reason').value = '';
    setText('selected-step', step.id);
    setText('selected-kind', `${step.kind || '좌표 단위'} · ${step.console_return ? '빈 공구 START 복귀' : step.empty_tool ? '빈 공구' : '접근·접촉·후퇴 포함'}${step.signal_gate ? ' · 신호 게이트' : ''}`);
    renderSteps(); renderEditor(); renderDiff(); renderPath(); updateControls();
  }
  function renderEditor() {
    const table = $('coordinate-table'); table.replaceChildren();
    model.stages.forEach((stage, index) => {
      const row = document.createElement('tr');
      const name = document.createElement('td');
      const strong = document.createElement('strong'); strong.textContent = `${index + 1}`;
      const small = document.createElement('small'); small.textContent = stage.phase || '—'; name.append(strong, small); row.append(name);
      [0, 1].forEach((axis) => {
        const cell = document.createElement('td');
        const input = document.createElement('input'); input.type = 'number'; input.step = '.001';
        input.value = finite(stage.target_base?.[axis]) ? String(stage.target_base[axis]) : '';
        input.setAttribute('aria-label', `${stage.id || index + 1} 목표 ${axis === 0 ? 'X' : 'Y'} mm`);
        input.dataset.stage = index; input.dataset.axis = axis;
        input.addEventListener('input', () => {
          const value = input.value === '' ? NaN : Number(input.value);
          input.setCustomValidity(finite(value) ? '' : '유효한 좌표를 입력하세요.');
          if (finite(value)) {
            model.stages[index].target_base[axis] = value;
            if (model.stages[index + 1]) model.stages[index + 1].start_base[axis] = value;
          }
          model.dirty = true; model.draft = null;
          input.classList.toggle('edited', value !== model.original.stages[index].target_base[axis]);
          renderDiff(); renderPath(); renderFixedDetails(); updateControls();
        });
        cell.append(input); row.append(cell);
      });
      const z = document.createElement('td'); z.textContent = number(stage.target_base?.[2]); row.append(z); table.append(row);
    });
    renderFixedDetails();
  }
  function renderFixedDetails() {
    const area = $('fixed-details'); area.replaceChildren();
    model.stages.forEach((stage, index) => {
      const line = document.createElement('div');
      line.textContent = `${index + 1}. ${stage.id || ''} · START [${poseText(stage.start_base)}] · TARGET R [${poseText(stage.target_base?.slice(3))}]`;
      area.append(line);
    });
  }
  function renderDiff() {
    const list = $('diff-list'); list.replaceChildren(); const diff = changes();
    if (!diff.length) { list.className = 'empty-copy'; list.textContent = '변경 없음'; }
    else { list.className = ''; diff.forEach((item) => {
      const row = document.createElement('div'); row.className = 'diff-entry';
      const name = document.createElement('strong'); name.textContent = item.label;
      const before = typeof item.before === 'number' ? number(item.before) : item.before;
      const after = typeof item.after === 'number' ? number(item.after) : item.after;
      row.append(name, document.createTextNode(` · ${before} → ${after}`)); list.append(row);
    }); }
    setText('draft-badge', model.draft ? (model.draft.approved ? '승인된 초안' : '미승인 초안') : model.dirty ? '수정 중' : '원본');
  }
  function statusBlocks() {
    const result = [];
    if (!freshStatus()) result.push('최신 서버 상태가 필요합니다.');
    if (!owned()) result.push('이 콘솔의 제어권이 없습니다.');
    const blockers = model.status?.ownership?.blockers;
    if (Array.isArray(blockers)) blockers.forEach((value) => result.push(typeof value === 'string' ? value : value.code || value.message || JSON.stringify(value)));
    if (runActive()) result.push('진행 중인 작업이 있습니다. 완료 또는 Stop 후 확인하세요.');
    if (model.status?.state === 'RECONCILIATION_REQUIRED') result.push(model.status.error || '미확정 이동 결과를 먼저 확인해야 합니다.');
    if (model.status?.state === 'REVIEW_REQUIRED') result.push(signalPending() ? '신호 관측이 필요합니다. 검토 확인으로 신호 게이트를 넘길 수 없습니다.' : '완료된 이동과 MUSE 원본 결과를 검토한 뒤 다음 단계를 선택하세요.');
    return [...new Set(result)];
  }
  function updateControls() {
    const ready = model.authenticated && freshStatus() && owned() && !model.busy && !runActive() && ['READY', 'REVIEW_REQUIRED'].includes(model.status?.state);
    const selected = !!model.step;
    const valid = Array.from($('coordinate-table').querySelectorAll('input')).every((input) => input.validity.valid && input.value !== '');
    const reason = $('change-reason').value.trim();
    const reasonValid = reason.length >= 10 && reason.length <= 500;
    const expectedValid = model.expectedVisual.length >= 10 && model.expectedVisual.length <= 700;
    const phase = model.status?.state;
    $('ownership-button').disabled = !model.authenticated || model.busy || !freshStatus() || (owned() ? !['READY', 'REVIEW_REQUIRED'].includes(phase) || runActive() : phase !== 'READ_ONLY');
    $('ownership-button').textContent = owned() ? '제어권 반납' : '제어권 확보';
    $('stop-button').disabled = !model.authenticated;
    $('expected-visual').disabled = !ready || !selected;
    $('change-reason').disabled = !ready || !selected;
    $('coordinate-table').querySelectorAll('input').forEach((input) => { input.disabled = !ready; });
    $('save-button').disabled = !ready || !selected || !model.dirty || !valid || !reasonValid || !expectedValid;
    $('approve-button').disabled = !ready || !model.draft || model.draft.approved || model.dirty || !reasonValid;
    $('execute-button').disabled = !ready || phase !== 'READY' || !selected || model.dirty || (model.draft && !model.draft.approved) || statusBlocks().length > 0;
    $('observe-button').disabled = !ready || phase !== 'REVIEW_REQUIRED' || !hasNativeReceipt();
    $('ack-button').disabled = !ready || phase !== 'REVIEW_REQUIRED' || !hasNativeReceipt() || !reasonValid || signalPending();
    $('signal-button').hidden = !model.status?.run?.signal_gate;
    $('signal-button').disabled = !ready || phase !== 'REVIEW_REQUIRED' || !hasNativeReceipt() || !signalPending();
    $('signal-button').textContent = signalPending() ? '신호등 2프레임 관측' : '초록 신호 승인 기록 있음';
    $('revert-button').disabled = !selected || model.busy || (!model.dirty && !model.draft);
    const blocks = statusBlocks(); const area = $('blockers'); area.replaceChildren(); area.classList.toggle('clear', !blocks.length);
    (blocks.length ? blocks : ['제어권 확보됨 · 실제 실행 가능 여부는 서버가 다시 확인합니다.']).forEach((value) => {
      const line = document.createElement('span'); line.textContent = value; area.append(line);
    });
    const confirmExecute = $('confirm-execute');
    confirmExecute.disabled = $('execute-button').disabled;
    if ($('approval-dialog').open) updateApprovalChecks();
  }
  function reviewData() {
    return model.status?.run?.review || model.status?.last_operation?.review || model.status?.review || null;
  }
  function artifactId(value) {
    if (typeof value === 'string') return value;
    return value?.artifact_id || value?.id || null;
  }
  function renderArtifact(which, id) {
    if (model[which] === id) return;
    model[which] = id;
    const image = $(`${which}-image`); image.hidden = true;
    $(`${which}-empty`).hidden = false; setText(`${which}-label`, id || '원본 없음');
    if (!id) { image.removeAttribute('src'); return; }
    image.onload = () => { if (model[which] === id) { image.hidden = false; $(`${which}-empty`).hidden = true; } };
    image.onerror = () => { image.hidden = true; $(`${which}-empty`).hidden = false; $(`${which}-empty`).textContent = '원본 이미지를 불러올 수 없습니다.'; };
    image.src = `/api/artifacts/${encodeURIComponent(id)}`;
  }
  function renderStatus() {
    const status = model.status; const robot = status.robot || {}; const run = status.run || {};
    $('connection').className = 'connection connected';
    $('connection').lastChild.textContent = '서버 연결됨';
    setText('revision-label', `revision ${status.revision ?? '—'}`);
    setText('run-state', run.phase || run.state || status.state || '미확인');
    setText('run-detail', [run.route, run.step_id, run.error?.code || run.error || status.error || status.last_operation?.error?.code].filter(Boolean).join(' · ') || '실행 중인 단계 없음');
    const tcp = robot.tcp_base || robot.pose_base || robot.tcp || robot.pose || robot.latest_measurement?.tcp_base;
    setText('tcp-value', Array.isArray(tcp) ? `X ${number(tcp[0], 2)}   Y ${number(tcp[1], 2)}` : '—');
    const stationary = robot.stationary ?? robot.idle;
    setText('robot-detail', Array.isArray(tcp) ? `Z ${number(tcp[2])} mm · ${robot.connected === true ? '연결' : robot.connected === false ? '연결 종료' : '연결 미확인'} · ${stationary === true ? '정지' : stationary === false ? '정지 확인 중' : '정지 미확인'}` : robot.reason || '실제 좌표 응답 없음');
    const review = reviewData();
    setText('review-state', review?.car?.verdict || review?.verdict || review?.decision || review?.state || '관측 기록 없음');
    setText('review-detail', review?.summary || review?.car?.summary || review?.message || '관측 실행 후 실제 결과가 표시됩니다.');
    renderArtifact('before', artifactId(run.before_artifact_id || run.before || review?.before_artifact_id || review?.before));
    renderArtifact('after', artifactId(run.after_artifact_id || run.after || review?.after_artifact_id || review?.after));
    const list = $('history-list'); list.replaceChildren();
    const historyRows = Array.isArray(status.history) ? status.history.slice(-12).reverse() : [];
    if (!historyRows.length) { const item = document.createElement('li'); item.className = 'empty-copy'; item.textContent = '실제 작업 기록 없음'; list.append(item); }
    historyRows.forEach((event) => {
      const item = document.createElement('li');
      const detail = event.value || event;
      item.textContent = [event.kind || event.event || event.type, event.step_id || detail.step_id || detail.request?.step_id, event.message || event.code || event.status || detail.code || detail.state].filter(Boolean).join(' · ') || JSON.stringify(event);
      const time = document.createElement('span');
      const timestamp = event.at || event.timestamp || event.created_at;
      time.textContent = typeof timestamp === 'number' ? new Date(timestamp * 1000).toLocaleString('ko-KR', { hour12: false }) : timestamp || '';
      item.append(time); list.append(item);
    });
    renderSteps(); renderPath(); updateControls();
  }
  function renderPath() {
    const svg = $('base-path'); svg.replaceChildren();
    const stages = model.stages.filter((entry) => Array.isArray(entry.start_base) && Array.isArray(entry.target_base) && [...entry.start_base.slice(0, 2), ...entry.target_base.slice(0, 2)].every(finite));
    $('path-empty').hidden = stages.length > 0;
    if (!stages.length) return;
    const rect = svg.getBoundingClientRect(); const width = Math.max(rect.width, 300); const height = Math.max(rect.height, 220);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const points = stages.flatMap((stage) => [stage.start_base, stage.target_base]);
    const robot = model.status?.robot || {}; const tcp = robot.tcp_base || robot.pose_base || robot.tcp || robot.pose || robot.latest_measurement?.tcp_base;
    if (Array.isArray(tcp) && finite(tcp[0]) && finite(tcp[1])) points.push(tcp);
    const minX = Math.min(...points.map((p) => p[0])); const maxX = Math.max(...points.map((p) => p[0]));
    const minY = Math.min(...points.map((p) => p[1])); const maxY = Math.max(...points.map((p) => p[1]));
    const pad = 56; const scale = Math.min((width - pad * 2) / Math.max(maxX - minX, 20), (height - pad * 2) / Math.max(maxY - minY, 20));
    const centerX = (minX + maxX) / 2; const centerY = (minY + maxY) / 2;
    const project = (point) => [width / 2 + (point[0] - centerX) * scale, height / 2 - (point[1] - centerY) * scale];
    const ns = 'http://www.w3.org/2000/svg';
    const add = (tag, attrs, text) => { const node = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value))); if (text !== undefined) node.textContent = text; svg.append(node); return node; };
    const grid = Math.max(10, Math.ceil(Math.max(maxX - minX, maxY - minY, 20) / 100) * 10);
    for (let x = Math.floor(minX / grid) * grid; x <= maxX + grid; x += grid) { const p = project([x, centerY]); add('line', { x1: p[0], y1: 38, x2: p[0], y2: height - 36, class: 'path-grid' }); }
    for (let y = Math.floor(minY / grid) * grid; y <= maxY + grid; y += grid) { const p = project([centerX, y]); add('line', { x1: 32, y1: p[1], x2: width - 32, y2: p[1], class: 'path-grid' }); }
    stages.forEach((stage, index) => {
      const a = project(stage.start_base); const b = project(stage.target_base);
      const color = stage.phase === 'contact' ? '#e98250' : stage.phase === 'withdraw' ? '#82a99b' : '#97b1bf';
      add('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: color, 'stroke-width': stage.phase === 'contact' ? 5 : 3, 'stroke-linecap': 'round', 'stroke-dasharray': stage.phase === 'contact' ? '' : '5 5' });
      add('circle', { cx: b[0], cy: b[1], r: 5, fill: '#f7f9fa', stroke: color, 'stroke-width': 2 });
      add('text', { x: b[0] + 9, y: b[1] - 9, fill: '#7791a1', 'font-size': 10 }, String(index + 1));
      if (index === 0) add('circle', { cx: a[0], cy: a[1], r: 6, fill: '#fff', stroke: '#9dafba', 'stroke-width': 2 });
    });
    if (Array.isArray(tcp) && finite(tcp[0]) && finite(tcp[1])) {
      const p = project(tcp); add('circle', { cx: p[0], cy: p[1], r: 10, fill: '#68a1b52e', stroke: '#638f9f', 'stroke-width': 1.5 }); add('circle', { cx: p[0], cy: p[1], r: 4, fill: '#638f9f' });
    }
    add('text', { x: 21, y: 26, fill: '#8d9faa', 'font-size': 10 }, `+Y ↑   +X →   · grid ${grid} mm`);
  }
  async function refreshCamera() {
    if (!model.authenticated || model.cameraBusy || document.hidden || model.view !== 'camera') return;
    model.cameraBusy = true;
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`/api/camera?t=${Date.now()}`, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!(response.headers.get('content-type') || '').startsWith('image/')) throw new Error('IMAGE_REQUIRED');
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const image = new Image();
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
      const old = model.cameraUrl; model.cameraUrl = url;
      $('live-camera').src = url; $('live-camera').hidden = false; $('camera-empty').hidden = true;
      if (old) URL.revokeObjectURL(old);
      setText('scene-time', `원본 수신 ${new Date().toLocaleTimeString('ko-KR', { hour12: false })}`);
    } catch (error) {
      setText('scene-time', model.cameraUrl ? '마지막 수신 프레임 · 새 영상 대기' : '카메라 응답 대기');
      if (!model.cameraUrl) $('camera-empty').hidden = false;
    } finally { clearTimeout(timer); model.cameraBusy = false; }
  }
  async function mutate(path, payload, success, timeout = 15000) {
    if (model.busy) return null;
    model.busy = true; updateControls();
    try {
      const value = await api(path, 'POST', { request_id: requestId(), expected_revision: model.status?.revision, ...payload }, timeout);
      message(success); await pollStatus(); return value;
    } catch (error) {
      message(`${error.code || 'REQUEST_FAILED'} · ${error.message}`, true);
      if (error.status === 401) showLogin('인증이 필요합니다.');
      await pollStatus(); return null;
    } finally { model.busy = false; updateControls(); }
  }
  $('login-form').addEventListener('submit', (event) => { event.preventDefault(); login($('token').value.trim()); });
  $('ownership-button').addEventListener('click', async () => {
    const release = owned();
    await mutate(`/api/session/${release ? 'release' : 'acquire'}`, {}, release ? '제어권을 반납했습니다.' : '제어권 확보 결과를 확인했습니다.');
  });
  $('expected-visual').addEventListener('input', () => { model.expectedVisual = $('expected-visual').value; model.dirty = true; model.draft = null; renderDiff(); updateControls(); });
  $('change-reason').addEventListener('input', updateControls);
  $('revert-button').addEventListener('click', () => { if (model.step) selectStep(model.step.id, true); });
  $('save-button').addEventListener('click', async () => {
    if (!model.step || $('save-button').disabled) return;
    const result = await mutate('/api/drafts', { route: model.route.code, step_id: model.step.id, stages: clone(model.stages), expected_visual: model.expectedVisual, reason: $('change-reason').value.trim() }, '초안이 저장되었습니다. 승인 전에는 실행하지 않습니다.');
    if (result) {
      const draft = result.draft || result;
      if (!draft.id && !draft.draft_id) { message('초안 식별자가 응답에 없습니다. 서버 기록을 확인하세요.', true); return; }
      model.draft = { ...draft, id: draft.id || draft.draft_id, approved: draft.approved === true || draft.status === 'APPROVED' };
      if (Array.isArray(draft.stages)) model.stages = clone(draft.stages);
      model.dirty = false; renderEditor(); renderDiff(); renderPath(); updateControls();
    }
  });
  function updateApprovalChecks() {
    const checks = Array.from($('approval-checks').querySelectorAll('input'));
    const required = model.draft?.required_reviewed_fields || [];
    $('confirm-approve').disabled = $('approve-button').disabled || !/^[0-9a-f]{64}$/.test(model.draft?.geometry_sha256 || '') || required.length !== 5 || checks.length !== 5 || checks.some((check) => !check.checked);
  }
  $('approve-button').addEventListener('click', () => {
    if (!model.draft || $('approve-button').disabled) return;
    const labels = {
      fixed_z_orientation: '모든 구간의 Z 높이와 그리퍼 자세가 고정되어 있음을 확인했습니다.',
      tool_car_hose_clearance: '그리퍼 전체·자동차·로봇 암·호스의 여유 공간을 확인했습니다.',
      contact_release: '접촉면 법선과 후퇴·분리 거리가 적절함을 확인했습니다.',
      path_continuity: '앞 구간 끝점과 다음 시작점이 연속적이며 접근·후퇴가 의도대로임을 확인했습니다.',
      bounded_xy_region: '전체 이동 경로가 검토된 XY 허용 영역 안에 있음을 확인했습니다.'
    };
    const fields = model.draft.required_reviewed_fields || [];
    if (fields.length !== 5 || fields.some((field) => !labels[field]) || new Set(fields).size !== 5) {
      message('서버의 필수 검토 항목을 확인할 수 없습니다. 초안을 다시 확인하세요.', true); return;
    }
    setText('approval-hash', model.draft.geometry_sha256 || '미확인');
    setText('approval-normal', model.draft.required_contact_normal_base_xy ? `[${poseText(model.draft.required_contact_normal_base_xy)}]` : '해당 접촉 법선 없음 · 서버 원본 기준');
    setText('approval-reason', `검토 사유: ${$('change-reason').value.trim()}`);
    const area = $('approval-checks'); area.replaceChildren();
    fields.forEach((field) => { const label = document.createElement('label'); const input = document.createElement('input'); input.type = 'checkbox'; input.value = field; input.addEventListener('change', updateApprovalChecks); label.append(input, document.createTextNode(labels[field])); area.append(label); });
    $('approval-dialog').returnValue = ''; $('approval-dialog').showModal(); updateApprovalChecks();
  });
  $('approval-dialog').addEventListener('close', async () => {
    if ($('approval-dialog').returnValue !== 'approve' || $('confirm-approve').disabled || !model.draft) return;
    const reviewedFields = Array.from($('approval-checks').querySelectorAll('input:checked')).map((input) => input.value);
    const result = await mutate(`/api/drafts/${encodeURIComponent(model.draft.id)}/approve`, { reason: $('change-reason').value.trim(), reviewed_fields: reviewedFields }, '정확한 수정 형상에 대한 시험 검토를 기록했습니다. 실행 버튼은 별도로 눌러야 합니다.');
    if (result) { const draft = result.draft || result; model.draft = { ...model.draft, ...draft, approved: draft.approved === true || draft.status === 'APPROVED' }; renderDiff(); updateControls(); }
  });
  $('execute-button').addEventListener('click', () => {
    if ($('execute-button').disabled) return;
    setText('confirm-description', `${model.route.code} · ${model.route.destination} / ${model.step.id}`);
    const facts = $('confirm-facts'); facts.replaceChildren();
    const contacts = model.stages.filter((stage) => stage.phase === 'contact');
    [['첫 목표 BASE', poseText(model.stages[0]?.target_base)], ['접촉 구간', `${contacts.length}개`], ['총 구간', `${model.stages.length}개`], ['실행 형상', model.draft ? `승인 초안 ${model.draft.id}` : '저장된 원본']].forEach(([label, value]) => {
      const dt = document.createElement('dt'); dt.textContent = label; const dd = document.createElement('dd'); dd.textContent = value; facts.append(dt, dd);
    });
    const stages = $('confirm-stages'); stages.replaceChildren();
    model.stages.forEach((stage, i) => { const row = document.createElement('div'); row.textContent = `${i + 1}. ${stage.phase} → [${poseText(stage.target_base)}]`; stages.append(row); });
    $('confirm-dialog').returnValue = '';
    $('confirm-dialog').showModal(); updateControls();
  });
  $('confirm-dialog').addEventListener('close', async () => {
    if ($('confirm-dialog').returnValue !== 'execute' || $('execute-button').disabled) return;
    await mutate('/api/execute', { route: model.route.code, step_id: model.step.id, draft_id: model.draft?.id || null }, '선택한 1개 단계의 실행 요청을 전송했습니다. 다음 단계는 자동 실행하지 않습니다.');
  });
  $('observe-button').addEventListener('click', () => mutate('/api/observe', {}, '관측 요청을 전송했습니다. 실제 결과를 기다립니다.'));
  $('ack-button').addEventListener('click', () => {
    const reason = $('change-reason').value.trim();
    if (reason.length < 10 || reason.length > 500) { message('Native 이동 완료와 관측 결과의 검토 사유를 10–500자로 입력하세요.', true); $('change-reason').focus(); return; }
    mutate('/api/review/ack', { reason }, 'Native 이동 완료 검토를 기록했습니다. MUSE 판정은 변경하지 않았으며 다음 단계는 자동 실행하지 않습니다.');
  });
  $('signal-button').addEventListener('click', () => {
    if ($('signal-button').disabled) return;
    mutate('/api/signal', {}, '두 실제 프레임의 신호 관측을 요청했습니다. 결과를 기다립니다.');
  });
  $('stop-button').addEventListener('click', async () => {
    const button = $('stop-button'); if (button.dataset.pending) return;
    button.dataset.pending = 'true';
    message('Stop 요청을 전송하고 있습니다.');
    try {
      await api('/api/stop', 'POST', { request_id: requestId(), reason: 'Operator pressed persistent console Stop' }, 12000);
      message('Stop 요청이 접수되었습니다. 실제 로봇 정지 상태를 확인하세요.'); await pollStatus();
    } catch (error) { message(`${error.code || 'STOP_UNCONFIRMED'} · Stop 접수를 확인할 수 없습니다. 현장 정지 상태를 확인하세요.`, true); }
    finally { delete button.dataset.pending; updateControls(); }
  });
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => {
    model.view = button.dataset.view;
    document.querySelectorAll('[data-view]').forEach((entry) => { entry.classList.toggle('selected', entry.dataset.view === model.view); entry.setAttribute('aria-pressed', String(entry.dataset.view === model.view)); });
    document.querySelectorAll('[data-scene]').forEach((entry) => { entry.hidden = entry.dataset.scene !== model.view; });
    if (model.view === 'path') renderPath(); if (model.view === 'camera') refreshCamera();
  }));
  window.addEventListener('resize', renderPath);
  window.addEventListener('pagehide', () => { if (model.cameraUrl) URL.revokeObjectURL(model.cameraUrl); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && model.authenticated) { pollStatus(); refreshCamera(); } });
  setInterval(() => { if (model.authenticated) { pollStatus(); updateControls(); } }, 2000);
  setInterval(refreshCamera, 1600);
  if (initialToken) { const token = initialToken; initialToken = ''; login(token); }
  else api('/api/status').then((status) => { model.status = status; model.statusAt = Date.now(); enterConsole(); }).catch(() => showLogin());
})();
