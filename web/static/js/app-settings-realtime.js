function renderLivenessModelStatus(status) {
  const element = document.getElementById('livenessModelStatus');
  if (!element) return;
  element.textContent = status?.message || 'Không kiểm tra được trạng thái model chống giả mạo.';
  element.classList.toggle('error-text', status?.status === 'error');
}

async function loadSettings(fillForm = true) {
  settings = await api('/api/settings');
  if (!fillForm) return;
  document.getElementById('settingThreshold').value = settings.face_threshold || 0.55;
  document.getElementById('settingCooldown').value = settings.check_cooldown_seconds || 30;
  document.getElementById('settingFrameSkip').value = settings.frame_skip || 2;
  document.getElementById('settingLivenessEnabled').checked = String(settings.liveness_enabled || 'false') === 'true';
  try {
    renderLivenessModelStatus(await api('/api/settings/liveness-status'));
  } catch (_error) {
    renderLivenessModelStatus();
  }
}

async function saveSettings() {
  const msg = document.getElementById('settingsMessage');
  msg.textContent = '';
  const payload = {
    face_threshold: Number(document.getElementById('settingThreshold').value),
    check_cooldown_seconds: Number(document.getElementById('settingCooldown').value),
    frame_skip: Number(document.getElementById('settingFrameSkip').value),
    liveness_enabled: document.getElementById('settingLivenessEnabled').checked,
  };

  try {
    const res = await fetch('/api/settings', {
      method: 'PUT',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorMessage(data.detail));
    msg.textContent = 'Đã lưu cài đặt.';
    await loadSettings();
  } catch (error) {
    msg.textContent = `Không lưu được: ${error.message}`;
  }
}

function realtimeCameraConfig(action) {
  return action === 'check_out'
    ? {
        action,
        label: 'Check-out',
        buttonId: 'checkOutToggleBtn',
        streamImageId: 'checkOutServerStream',
        overlayId: 'checkOutOverlay',
        resultId: 'checkOutResult',
        cameraLabelId: 'checkOutCameraLabel',
        onText: 'Out on',
        offText: 'Out off',
      }
    : {
        action: 'check_in',
        label: 'Check-in',
        buttonId: 'checkInToggleBtn',
        streamImageId: 'checkInServerStream',
        overlayId: 'checkInOverlay',
        resultId: 'checkInResult',
        cameraLabelId: 'checkInCameraLabel',
        onText: 'Vào on',
        offText: 'Vào off',
      };
}

function updateRealtimeToggle(action) {
  const config = realtimeCameraConfig(action);
  const running = realtimeSessions[config.action].serverRunning;
  const button = document.getElementById(config.buttonId);
  if (!button) return;
  button.textContent = running ? config.offText : config.onText;
  button.classList.toggle('secondary', running);
}

function updateRealtimeCameraLabel(action, text) {
  const element = document.getElementById(realtimeCameraConfig(action).cameraLabelId);
  if (element) element.textContent = text;
}

async function serverCameraPost(path) {
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: csrfHeaders(),
  });
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Phiên đăng nhập đã hết hạn.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiErrorMessage(data.detail));
  return data;
}

function clearRealtimeOverlay(action) {
  const canvas = document.getElementById(realtimeCameraConfig(action).overlayId);
  if (!canvas) return;
  canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
}

function attachServerCameraStream(action) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[action];
  const image = document.getElementById(config.streamImageId);
  if (!image || session.serverStreamAttached) return;
  image.hidden = false;
  image.src = `/api/server-cameras/${action}/stream?view=${Date.now()}`;
  image.onerror = () => {
    session.serverStreamAttached = false;
    image.hidden = true;
    image.removeAttribute('src');
  };
  session.serverStreamAttached = true;
}

function detachServerCameraStream(action) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[action];
  const image = document.getElementById(config.streamImageId);
  if (image) {
    image.onerror = null;
    image.hidden = true;
    image.removeAttribute('src');
  }
  session.serverStreamAttached = false;
  session.lastResultSequence = -1;
  clearRealtimeOverlay(action);
}

function applyServerCameraStatus(action, status) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[action];
  const result = document.getElementById(config.resultId);
  session.serverRunning = Boolean(status?.running);

  if (status?.running && status?.connected) {
    attachServerCameraStream(action);
    updateRealtimeCameraLabel(action, status.source || 'Camera backend');
    if (status.frame_width > 0 && status.frame_height > 0) {
      const canvas = document.getElementById(config.overlayId);
      if (canvas && (canvas.width !== status.frame_width || canvas.height !== status.frame_height)) {
        canvas.width = status.frame_width;
        canvas.height = status.frame_height;
      }
    }
    if (status.last_result && status.last_result_sequence !== session.lastResultSequence) {
      session.lastResultSequence = status.last_result_sequence;
      handleRealtimeRecognition(action, status.last_result, {
        frameWidth: status.frame_width,
        frameHeight: status.frame_height,
        refreshDashboard: false,
      });
    } else if (!status.last_result && result) {
      result.textContent = `${config.label} đang chạy, đang chờ nhận diện...`;
    }
  } else {
    detachServerCameraStream(action);
    if (status?.running) {
      updateRealtimeCameraLabel(action, 'Đang kết nối lại');
      if (result) result.textContent = status.last_error || `${config.label} đang kết nối camera...`;
    } else {
      updateRealtimeCameraLabel(action, 'Chưa bật');
      if (result) result.textContent = status?.last_error || 'Chưa bật camera';
    }
  }
  updateRealtimeToggle(action);
}

async function refreshServerCameraStatus() {
  if (serverCameraStatusBusy) return;
  serverCameraStatusBusy = true;
  try {
    const statuses = await api('/api/server-cameras/status');
    applyServerCameraStatus('check_in', statuses.check_in || {});
    applyServerCameraStatus('check_out', statuses.check_out || {});
  } catch (error) {
    ['check_in', 'check_out'].forEach((action) => {
      const result = document.getElementById(realtimeCameraConfig(action).resultId);
      if (result) result.textContent = `Không tải được trạng thái camera: ${error.message}`;
    });
  } finally {
    serverCameraStatusBusy = false;
  }
}

function startServerCameraStatusPolling() {
  if (serverCameraStatusTimer) clearInterval(serverCameraStatusTimer);
  serverCameraStatusTimer = setInterval(refreshServerCameraStatus, SERVER_CAMERA_STATUS_INTERVAL_MS);
}

async function startServerRealtimeCamera(action) {
  const config = realtimeCameraConfig(action);
  const result = document.getElementById(config.resultId);
  try {
    if (result) result.textContent = `${config.label} đang khởi động...`;
    const status = await serverCameraPost(`/api/server-cameras/${action}/start`);
    applyServerCameraStatus(action, status);
    await refreshServerCameraStatus();
  } catch (error) {
    if (result) result.textContent = `Không bật được ${config.label}: ${error.message}`;
  }
}

async function stopServerRealtimeCamera(action) {
  const config = realtimeCameraConfig(action);
  const result = document.getElementById(config.resultId);
  try {
    const status = await serverCameraPost(`/api/server-cameras/${action}/stop`);
    applyServerCameraStatus(action, status);
    if (result) result.textContent = `${config.label} đã tắt.`;
  } catch (error) {
    if (result) result.textContent = `Không tắt được ${config.label}: ${error.message}`;
  }
}

async function stopAllServerRealtimeCameras() {
  try {
    const statuses = await serverCameraPost('/api/server-cameras/stop-all');
    applyServerCameraStatus('check_in', statuses.check_in || {});
    applyServerCameraStatus('check_out', statuses.check_out || {});
  } catch (error) {
    ['check_in', 'check_out'].forEach((action) => {
      const result = document.getElementById(realtimeCameraConfig(action).resultId);
      if (result) result.textContent = `Không tắt được camera: ${error.message}`;
    });
  }
}

async function initializeRealtimeCameraUi() {
  ['check_in', 'check_out'].forEach((action) => {
    const button = document.getElementById(realtimeCameraConfig(action).buttonId);
    if (button && !isAdmin()) {
      button.disabled = true;
      button.title = 'Chỉ admin được bật hoặc tắt camera backend.';
    }
  });
  const stopAllButton = document.getElementById('stopAllCameraBtn');
  if (stopAllButton && !isAdmin()) {
    stopAllButton.disabled = true;
    stopAllButton.title = 'Chỉ admin được bật hoặc tắt camera backend.';
  }
  await refreshServerCameraStatus();
  startServerCameraStatusPolling();
}

async function toggleRealtimeCamera(action) {
  if (realtimeSessions[action].serverRunning) {
    await stopServerRealtimeCamera(action);
  } else {
    await startServerRealtimeCamera(action);
  }
}

function stopAllRealtimeCameras() {
  void stopAllServerRealtimeCameras();
}

function handleRealtimeRecognition(action, data, options = {}) {
  const config = realtimeCameraConfig(action);
  const result = document.getElementById(config.resultId);
  if (data.type === 'skip') return;
  if (data.type === 'error') {
    clearRealtimeOverlay(action);
    result.textContent = data.message;
    return;
  }

  const canvas = document.getElementById(config.overlayId);
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  const sourceWidth = Number(options.frameWidth) || canvas.width;
  const sourceHeight = Number(options.frameHeight) || canvas.height;
  const scaleX = sourceWidth > 0 ? canvas.width / sourceWidth : 1;
  const scaleY = sourceHeight > 0 ? canvas.height / sourceHeight : 1;
  const items = data.items || [];

  items.forEach((item) => {
    if (!Array.isArray(item.bbox) || item.bbox.length < 4) return;
    const [x1, y1, x2, y2] = item.bbox;
    const drawX = Math.max(0, Math.min(canvas.width, x1 * scaleX));
    const drawY = Math.max(0, Math.min(canvas.height, y1 * scaleY));
    const drawW = Math.max(0, Math.min(canvas.width - drawX, (x2 - x1) * scaleX));
    const drawH = Math.max(0, Math.min(canvas.height - drawY, (y2 - y1) * scaleY));
    if (drawW <= 0 || drawH <= 0) return;

    context.lineWidth = 3;
    const status = itemDisplayStatus(item);
    const color = statusColor(status, item.recognized);
    context.strokeStyle = color;
    context.strokeRect(drawX, drawY, drawW, drawH);
    const label = itemOverlayText(item);
    context.font = `600 18px ${getComputedStyle(document.body).fontFamily}`;
    const labelPaddingX = 8;
    const labelHeight = 26;
    const labelWidth = Math.min(canvas.width - 4, context.measureText(label).width + labelPaddingX * 2);
    const labelX = Math.max(2, Math.min(drawX, canvas.width - labelWidth - 2));
    const labelY = drawY > labelHeight + 8 ? drawY - labelHeight - 4 : drawY + 4;
    context.fillStyle = 'rgba(15, 23, 42, 0.88)';
    context.fillRect(labelX, labelY, labelWidth, labelHeight);
    context.fillStyle = color;
    context.fillText(label, labelX + labelPaddingX, labelY + 18);
  });

  const primaryItem = items.find((item) => itemDisplayStatus(item) !== 'secondary');
  if (primaryItem) {
    result.innerHTML = realtimeResultHtml(primaryItem, config.label);
    maybeShowRealtimeNotice(config.action, primaryItem);
    if (options.refreshDashboard !== false) loadDashboard();
  } else {
    result.textContent = `${config.label}: không thấy khuôn mặt trong khung hình`;
  }
}

async function initApp() {
  await loadCurrentUser();
  applySettingsInputLimits();
  initListFilters();
  await loadDashboard();
  await loadStudents();
  await loadSettings(false);
  await initializeRealtimeCameraUi();
  renderFaceScanGuide();
  const requestedPage = new URLSearchParams(window.location.search).get('page');
  if (requestedPage && pages[requestedPage]) {
    showPage(requestedPage);
    window.history.replaceState({}, '', '/');
  } else if (window.location.search) {
    window.history.replaceState({}, '', '/');
  }
}

initApp().catch((error) => {
  console.error(error);
});
