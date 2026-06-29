function renderLivenessModelStatus(status) {
  const element = document.getElementById('livenessModelStatus');
  if (!element) return;
  element.textContent = status?.message || 'Không kiểm tra được trạng thái model chống giả mạo.';
  element.classList.toggle('error-text', status?.status === 'error');
}

async function loadSettings(fillForm = true) {
  settings = await api('/api/settings');
  if (fillForm) {
    document.getElementById('settingThreshold').value = settings.face_threshold || 0.55;
    document.getElementById('settingCooldown').value = settings.check_cooldown_seconds || 30;
    document.getElementById('settingFrameSkip').value = settings.frame_skip || 2;
    document.getElementById('settingLivenessEnabled').checked = String(settings.liveness_enabled || 'false') === 'true';
    document.getElementById('settingAutoStartCameras').checked = String(settings.auto_start_cameras || 'false') === 'true';
    document.getElementById('settingCheckInCameraSource').value = settings.check_in_camera_source || '';
    document.getElementById('settingCheckOutCameraSource').value = settings.check_out_camera_source || '';
    try {
      renderLivenessModelStatus(await api('/api/settings/liveness-status'));
    } catch (_error) {
      renderLivenessModelStatus();
    }
    await loadCameraDevices();
  }
}

async function saveSettings() {
  const checkInCamera = document.getElementById('settingCheckInCamera');
  const checkOutCamera = document.getElementById('settingCheckOutCamera');
  const msg = document.getElementById('settingsMessage');
  msg.textContent = '';
  const payload = {
    face_threshold: Number(document.getElementById('settingThreshold').value),
    check_cooldown_seconds: Number(document.getElementById('settingCooldown').value),
    frame_skip: Number(document.getElementById('settingFrameSkip').value),
    check_in_camera_device_id: checkInCamera ? checkInCamera.value : '',
    check_out_camera_device_id: checkOutCamera ? checkOutCamera.value : '',
    auto_start_cameras: document.getElementById('settingAutoStartCameras').checked,
    check_in_camera_source: document.getElementById('settingCheckInCameraSource').value.trim(),
    check_out_camera_source: document.getElementById('settingCheckOutCameraSource').value.trim(),
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
    if (!res.ok) {
      throw new Error(apiErrorMessage(data.detail));
    }
    msg.textContent = 'Đã lưu cài đặt.';
    await loadSettings();
  } catch (e) {
    msg.textContent = `Không lưu được: ${e.message}`;
  }
}

function realtimeCameraConfig(action) {
  return action === 'check_out'
    ? {
        action,
        label: 'Check-out',
        settingKey: 'check_out_camera_device_id',
        buttonId: 'checkOutToggleBtn',
        videoId: 'checkOutVideo',
        overlayId: 'checkOutOverlay',
        resultId: 'checkOutResult',
        cameraLabelId: 'checkOutCameraLabel',
        onText: 'Out on',
        offText: 'Out off',
      }
    : {
        action: 'check_in',
        label: 'Check-in',
        settingKey: 'check_in_camera_device_id',
        buttonId: 'checkInToggleBtn',
        videoId: 'checkInVideo',
        overlayId: 'checkInOverlay',
        resultId: 'checkInResult',
        cameraLabelId: 'checkInCameraLabel',
        onText: 'Vào on',
        offText: 'Vào off',
      };
}

function populateCameraSelect(selectId, selectedValue) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const options = ['<option value="">Camera mặc định</option>'].concat(
    cameraDevices.map((device, idx) => `<option value="${device.deviceId}">${device.label || `Camera ${idx + 1}`}</option>`)
  );
  select.innerHTML = options.join('');
  select.value = selectedValue || '';
}

async function loadCameraDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
  const devices = await navigator.mediaDevices.enumerateDevices();
  cameraDevices = devices.filter((device) => device.kind === 'videoinput');
  populateCameraSelect('settingCheckInCamera', settings.check_in_camera_device_id || '');
  populateCameraSelect('settingCheckOutCamera', settings.check_out_camera_device_id || '');
}

function selectedCameraLabel(deviceId) {
  const device = cameraDevices.find((item) => item.deviceId === deviceId);
  return device ? device.label || 'Camera đã chọn' : 'Camera mặc định';
}

function realtimeCameraConstraints(action) {
  const config = realtimeCameraConfig(action);
  const deviceId = settings[config.settingKey] || '';
  const video = { width: 640, height: 360 };
  if (deviceId) video.deviceId = { exact: deviceId };
  return { video, audio: false };
}

function updateRealtimeToggle(action) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[config.action];
  const btn = document.getElementById(config.buttonId);
  if (!btn) return;
  const running = Boolean(session.stream);
  btn.textContent = running ? config.offText : config.onText;
  btn.classList.toggle('secondary', running);
}

function updateRealtimeCameraLabel(action, text) {
  const el = document.getElementById(realtimeCameraConfig(action).cameraLabelId);
  if (el) el.textContent = text;
}

async function toggleRealtimeCamera(action) {
  const session = realtimeSessions[action];
  if (session && session.stream) {
    stopRealtimeCamera(action, true);
    return;
  }
  await startRealtimeCamera(action);
}

async function startRealtimeCamera(action) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[config.action];
  const video = document.getElementById(config.videoId);
  const canvas = document.getElementById(config.overlayId);
  const result = document.getElementById(config.resultId);
  stopFaceRegisterCamera(false);
  await loadSettings(false);
  await loadCameraDevices();
  session.stopping = false;

  try {
    session.stream = await navigator.mediaDevices.getUserMedia(realtimeCameraConstraints(config.action));
    video.srcObject = session.stream;
    await new Promise((resolve) => {
      video.onloadedmetadata = resolve;
    });
    const frameSize = realtimeFrameSize(video);
    canvas.width = frameSize.width;
    canvas.height = frameSize.height;
    const wsProtocol = location.protocol === 'https:' ? 'wss' : 'ws';
    session.ws = new WebSocket(`${wsProtocol}://${location.host}/ws/recognize?action=${config.action}`);
    session.ws.onmessage = (event) => handleRealtimeRecognition(config.action, JSON.parse(event.data));
    session.ws.onopen = () => {
      session.sendTimer = setInterval(() => sendRealtimeFrame(config.action), REALTIME_SEND_INTERVAL_MS);
      result.textContent = `${config.label} đang chạy, đang chờ nhận diện...`;
      updateRealtimeCameraLabel(config.action, selectedCameraLabel(settings[config.settingKey] || ''));
      updateRealtimeToggle(config.action);
    };
    session.ws.onclose = () => {
      session.busy = false;
      if (session.stopping) return;
      stopRealtimeCamera(config.action, false);
      result.textContent = `${config.label} đã dừng. Bật lại camera để tiếp tục nhận diện.`;
    };
  } catch (e) {
    stopRealtimeCamera(config.action, false);
    result.textContent = e.message || `Không bật được camera ${config.label}.`;
  }
}

function stopRealtimeCamera(action, showMessage = true) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[config.action];
  session.stopping = true;
  if (session.sendTimer) clearInterval(session.sendTimer);
  if (session.ws) {
    session.ws.onclose = null;
    session.ws.close();
  }
  if (session.stream) session.stream.getTracks().forEach((track) => track.stop());
  session.sendTimer = null;
  session.ws = null;
  session.stream = null;
  session.busy = false;

  const video = document.getElementById(config.videoId);
  const canvas = document.getElementById(config.overlayId);
  if (video) video.srcObject = null;
  if (canvas) {
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  if (showMessage) {
    const result = document.getElementById(config.resultId);
    if (result) result.textContent = `${config.label} đã tắt.`;
  }
  updateRealtimeCameraLabel(config.action, 'Chưa bật');
  updateRealtimeToggle(config.action);
  session.stopping = false;
}

function stopAllRealtimeCameras(showMessage = true) {
  stopRealtimeCamera('check_in', showMessage);
  stopRealtimeCamera('check_out', showMessage);
}

function sendRealtimeFrame(action) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[config.action];
  const video = document.getElementById(config.videoId);
  if (!session.ws || session.ws.readyState !== WebSocket.OPEN || video.readyState < 2) return;
  if (session.busy) return;
  const temp = document.createElement('canvas');
  const frameSize = realtimeFrameSize(video);
  temp.width = frameSize.width;
  temp.height = frameSize.height;
  const overlay = document.getElementById(config.overlayId);
  if (overlay.width !== temp.width || overlay.height !== temp.height) {
    overlay.width = temp.width;
    overlay.height = temp.height;
  }
  temp.getContext('2d').drawImage(video, 0, 0, temp.width, temp.height);
  session.busy = true;
  session.ws.send(JSON.stringify({ image: temp.toDataURL('image/jpeg', REALTIME_JPEG_QUALITY) }));
}

function handleRealtimeRecognition(action, data) {
  const config = realtimeCameraConfig(action);
  const session = realtimeSessions[config.action];
  session.busy = false;
  const result = document.getElementById(config.resultId);
  if (data.type === 'skip') return;
  if (data.type === 'error') {
    const canvas = document.getElementById(config.overlayId);
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    result.textContent = data.message;
    return;
  }
  const canvas = document.getElementById(config.overlayId);
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const items = data.items || [];
  items.forEach((item) => {
    if (!Array.isArray(item.bbox) || item.bbox.length < 4) return;
    const [x1, y1, x2, y2] = item.bbox;
    const drawX = Math.max(0, Math.min(canvas.width, canvas.width - x2));
    const drawY = Math.max(0, Math.min(canvas.height, y1));
    const drawW = Math.max(0, Math.min(canvas.width - drawX, x2 - x1));
    const drawH = Math.max(0, Math.min(canvas.height - drawY, y2 - y1));
    if (drawW <= 0 || drawH <= 0) return;
    ctx.lineWidth = 3;
    const status = itemDisplayStatus(item);
    const color = statusColor(status, item.recognized);
    ctx.strokeStyle = color;
    ctx.strokeRect(drawX, drawY, drawW, drawH);
    const label = itemOverlayText(item);
    ctx.font = `600 18px ${getComputedStyle(document.body).fontFamily}`;
    const labelPaddingX = 8;
    const labelHeight = 26;
    const labelWidth = Math.min(canvas.width - 4, ctx.measureText(label).width + labelPaddingX * 2);
    const labelX = Math.max(2, Math.min(drawX, canvas.width - labelWidth - 2));
    const labelY = drawY > labelHeight + 8 ? drawY - labelHeight - 4 : drawY + 4;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    ctx.fillRect(labelX, labelY, labelWidth, labelHeight);
    ctx.fillStyle = color;
    ctx.fillText(label, labelX + labelPaddingX, labelY + 18);
  });
  const primaryItem = items.find((item) => itemDisplayStatus(item) !== 'secondary');
  if (primaryItem) {
    result.innerHTML = realtimeResultHtml(primaryItem, config.label);
    maybeShowRealtimeNotice(config.action, primaryItem);
    loadDashboard();
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
  renderFaceScanGuide();
  const requestedPage = new URLSearchParams(window.location.search).get('page');
  if (requestedPage && pages[requestedPage]) {
    showPage(requestedPage);
    window.history.replaceState({}, '', '/');
  } else if (window.location.search) {
    window.history.replaceState({}, '', '/');
  }
}

initApp().catch((err) => {
  console.error(err);
});
