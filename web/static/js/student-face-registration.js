const STUDENT_FACE_REQUEST_STEPS = [
  { key: 'front', label: 'Chính diện' },
  { key: 'left', label: 'Nghiêng trái' },
  { key: 'right', label: 'Nghiêng phải' },
  { key: 'up', label: 'Nhìn lên nhẹ' },
  { key: 'down', label: 'Nhìn xuống nhẹ' },
];

let studentFaceRequestStream = null;
let studentFaceRequestCaptures = new Map();
let studentOfficialFaceCount = 0;
let studentFacePoseTimer = null;
let studentFacePoseBusy = false;
let studentFaceCaptureBusy = false;
let studentFacePoseStableCount = 0;
let studentFaceLastPose = null;
let studentFaceScanningStarted = false;

const STUDENT_FACE_ANALYZE_INTERVAL_MS = 650;
const STUDENT_FACE_AUTO_STABLE_FRAMES = 2;

function studentFaceRequestDate(value) {
  return value ? String(value).replace('T', ' ') : '-';
}

function studentFaceRequestStatusLabel(status) {
  const labels = {
    pending: 'Chờ duyệt',
    approved: 'Đã được duyệt',
    rejected: 'Bị từ chối',
    cancelled: 'Đã hủy',
  };
  return labels[status] || status || '-';
}

window.loadStudentFaceRegistration = async function loadStudentFaceRegistration(faceData = null) {
  const panel = document.getElementById('studentFaceRequestPanel');
  if (!panel) return;
  try {
    const data = await api('/api/student/face-registration');
    const officialCount = Number(data?.official_face_count ?? faceData?.count ?? 0);
    const latest = data?.latest_request;
    studentOfficialFaceCount = officialCount;
    if (latest?.status === 'pending') {
      const removeCount = Number(latest.replace_count_now ?? latest.planned_remove_count ?? 0);
      const afterCount = Number(latest.face_count_after_approval ?? officialCount - removeCount + 5);
      const isUpdate = officialCount > 0 || latest.request_type === 'update';
      const resultText = removeCount > 0
        ? `${removeCount} ảnh FaceID cũ nhất sẽ được thay bằng 5 ảnh mới; bộ mẫu sẽ thành ${afterCount}/10.`
        : `5 ảnh mới sẽ được bổ sung; bộ mẫu sẽ thành ${afterCount}/10.`;
      panel.innerHTML = `
        <div class="student-face-request-state pending">
          <strong>${isUpdate ? 'FaceID đang hoạt động — yêu cầu cập nhật đang chờ duyệt' : 'Yêu cầu đang chờ duyệt'}</strong>
          <span>Bạn đã gửi đủ 5 ảnh vào lúc ${escapeHtml(studentFaceRequestDate(latest.created_at))}. ${isUpdate ? `Nếu được duyệt, ${resultText}` : 'FaceID chưa được dùng cho đến khi quản lý duyệt.'}</span>
          <div class="student-face-request-actions"><button class="secondary" type="button" onclick="cancelStudentFaceRequest(${Number(latest.id)})">Hủy yêu cầu</button></div>
        </div>`;
      return;
    }
    if (officialCount > 0) {
      const rejectedText = latest?.status === 'rejected'
        ? `<span>Yêu cầu cập nhật gần nhất bị từ chối: ${escapeHtml(latest.reject_reason || 'Vui lòng chụp lại ảnh rõ hơn.')}</span>`
        : '';
      panel.innerHTML = `
        <div class="student-face-request-state approved">
          <strong>FaceID đã hoạt động (${officialCount}/10 mẫu)</strong>
          <span>Bộ ảnh hiện tại vẫn đang dùng để điểm danh. Bạn có thể gửi thêm 5 ảnh mới để cập nhật hoặc bổ sung bộ mẫu.</span>
          ${rejectedText}
          <div class="student-face-request-actions"><button type="button" onclick="openStudentFaceRequestCapture()">Cập nhật / bổ sung 5 ảnh FaceID</button></div>
        </div>`;
      return;
    }
    if (latest?.status === 'rejected') {
      panel.innerHTML = `
        <div class="student-face-request-state rejected">
          <strong>Yêu cầu gần nhất bị từ chối</strong>
          <span>Lý do: ${escapeHtml(latest.reject_reason || 'Vui lòng chụp lại ảnh rõ hơn.')}</span>
          <div class="student-face-request-actions"><button type="button" onclick="openStudentFaceRequestCapture()">Chụp và gửi lại</button></div>
        </div>`;
      return;
    }
    panel.innerHTML = `
      <div class="student-face-request-state empty">
        <strong>Bạn chưa có FaceID</strong>
        <span>Chụp 5 ảnh khuôn mặt và gửi yêu cầu để quản lý kiểm tra trước khi dùng điểm danh.</span>
        <div class="student-face-request-actions"><button type="button" onclick="openStudentFaceRequestCapture()">Bắt đầu đăng ký FaceID</button></div>
      </div>`;
  } catch (error) {
    panel.innerHTML = `<div class="student-face-request-state rejected"><strong>Không tải được trạng thái FaceID</strong><span>${escapeHtml(error.message || 'Vui lòng thử lại.')}</span></div>`;
  }
};

async function openStudentFaceRequestCapture() {
  const modal = document.getElementById('studentFaceRequestCaptureModal');
  const message = document.getElementById('studentFaceCaptureMessage');
  const title = document.getElementById('studentFaceRequestModalTitle');
  if (!modal) return;
  if (title) title.textContent = studentOfficialFaceCount > 0
    ? 'Gửi yêu cầu cập nhật FaceID'
    : 'Gửi yêu cầu đăng ký FaceID';
  resetStudentFaceRequestCapture();
  modal.classList.remove('hidden');
  if (message) message.textContent = 'Sẵn sàng chụp 5 tư thế. Bấm “Bắt đầu quét tự động” để mở camera và bắt đầu.';
}

async function startStudentFaceRequestScan() {
  const video = document.getElementById('studentFaceRequestVideo');
  const message = document.getElementById('studentFaceCaptureMessage');
  if (!video || studentFaceScanningStarted) return;
  studentFaceScanningStarted = true;
  renderStudentFaceRequestCapture();
  if (message) message.textContent = 'Đang mở camera...';
  try {
    studentFaceRequestStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user' },
      audio: false,
    });
    video.srcObject = studentFaceRequestStream;
    await video.play();
    startStudentFacePoseAnalyzer();
    if (message) message.textContent = 'Hệ thống đang tự nhận diện tư thế. Nếu cần, bạn vẫn có thể bấm Chụp thủ công.';
  } catch (error) {
    studentFaceScanningStarted = false;
    renderStudentFaceRequestCapture();
    if (message) message.textContent = 'Không mở được camera. Hãy cho phép quyền dùng camera rồi thử lại.';
  }
}

function resetStudentFaceRequestCapture() {
  for (const capture of studentFaceRequestCaptures.values()) {
    if (capture.url) URL.revokeObjectURL(capture.url);
  }
  studentFaceRequestCaptures = new Map();
  const note = document.getElementById('studentFaceRequestNote');
  const consent = document.getElementById('studentFaceRequestConsent');
  if (note) note.value = '';
  if (consent) consent.checked = false;
  renderStudentFaceRequestCapture();
}

function restartStudentFaceRequestCapture() {
  resetStudentFaceRequestCapture();
  if (studentFaceRequestStream) startStudentFacePoseAnalyzer();
  const message = document.getElementById('studentFaceCaptureMessage');
  if (message) message.textContent = 'Đã xóa ảnh đã chụp. Bắt đầu lại từ tư thế chính diện.';
}

function currentStudentFaceRequestStep() {
  return STUDENT_FACE_REQUEST_STEPS.find((step) => !studentFaceRequestCaptures.has(step.key)) || null;
}

function renderStudentFaceRequestCapture() {
  const steps = document.getElementById('studentFaceCaptureSteps');
  const preview = document.getElementById('studentFaceCapturePreview');
  const hint = document.getElementById('studentFaceCaptureHint');
  const captureButton = document.getElementById('studentFaceCaptureBtn');
  const startScanButton = document.getElementById('studentFaceStartScanBtn');
  const submitButton = document.getElementById('studentFaceSubmitRequestBtn');
  const current = currentStudentFaceRequestStep();
  const replaceCount = Math.max(0, studentOfficialFaceCount + STUDENT_FACE_REQUEST_STEPS.length - 10);
  const afterCount = studentOfficialFaceCount - replaceCount + STUDENT_FACE_REQUEST_STEPS.length;
  if (hint) hint.textContent = current
    ? `Bước ${STUDENT_FACE_REQUEST_STEPS.indexOf(current) + 1}/5: ${current.label}`
    : studentOfficialFaceCount > 0
      ? `Đã chụp đủ 5 ảnh. Khi được duyệt: ${replaceCount ? `thay ${replaceCount} ảnh cũ nhất` : 'không thay ảnh cũ'}; bộ mẫu sẽ thành ${afterCount}/10.`
      : 'Đã chụp đủ 5 ảnh. Kiểm tra lại trước khi gửi yêu cầu.';
  if (steps) {
    steps.innerHTML = STUDENT_FACE_REQUEST_STEPS.map((step, index) => {
      const done = studentFaceRequestCaptures.has(step.key) ? 'done' : '';
      const active = current?.key === step.key ? 'active' : '';
      return `<span class="scan-step ${done} ${active}">${index + 1}. ${step.label}</span>`;
    }).join('');
  }
  if (preview) {
    preview.innerHTML = STUDENT_FACE_REQUEST_STEPS.map((step) => {
      const capture = studentFaceRequestCaptures.get(step.key);
      return `<article class="student-face-request-preview-item"><span>${step.label}</span>${capture ? `<img src="${escapeHtml(capture.url)}" alt="${escapeHtml(step.label)}" />` : '<div class="student-face-request-placeholder">Chưa chụp</div>'}</article>`;
    }).join('');
  }
  if (captureButton) {
    captureButton.disabled = !current || studentFaceCaptureBusy || !studentFaceRequestStream;
    captureButton.textContent = studentFaceCaptureBusy
      ? 'Đang chụp...'
      : current ? `Chụp thủ công: ${current.label}` : 'Đã chụp đủ 5 ảnh';
  }
  if (startScanButton) {
    startScanButton.disabled = !current || studentFaceScanningStarted;
    startScanButton.textContent = studentFaceScanningStarted ? 'Đang quét tự động' : 'Bắt đầu quét tự động';
  }
  if (submitButton) submitButton.disabled = Boolean(current) || !document.getElementById('studentFaceRequestConsent')?.checked;
}

function startStudentFacePoseAnalyzer() {
  stopStudentFacePoseAnalyzer();
  studentFacePoseTimer = setInterval(analyzeStudentFaceRequestFrame, STUDENT_FACE_ANALYZE_INTERVAL_MS);
  analyzeStudentFaceRequestFrame();
}

function stopStudentFacePoseAnalyzer() {
  if (studentFacePoseTimer) clearInterval(studentFacePoseTimer);
  studentFacePoseTimer = null;
  studentFacePoseBusy = false;
  studentFacePoseStableCount = 0;
  studentFaceLastPose = null;
}

function studentFacePoseLabel(pose) {
  const step = STUDENT_FACE_REQUEST_STEPS.find((item) => item.key === pose);
  return step ? step.label : pose || 'chưa rõ';
}

function studentFaceRequestFrameDataUrl() {
  const video = document.getElementById('studentFaceRequestVideo');
  const canvas = document.getElementById('studentFaceRequestCanvas');
  if (!video || !canvas || video.videoWidth < 2 || video.videoHeight < 2) return null;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext('2d');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const image = canvas.toDataURL('image/jpeg', 0.72);
  context.clearRect(0, 0, canvas.width, canvas.height);
  return image;
}

async function analyzeStudentFaceRequestFrame() {
  const current = currentStudentFaceRequestStep();
  const message = document.getElementById('studentFaceCaptureMessage');
  if (!current || studentFacePoseBusy || studentFaceCaptureBusy || !studentFaceRequestStream) return;
  const image = studentFaceRequestFrameDataUrl();
  if (!image) return;

  studentFacePoseBusy = true;
  try {
    const result = await api('/api/student/face-registration/analyze', {
      method: 'POST',
      body: JSON.stringify({ image }),
    });
    if (!result?.ok) {
      studentFacePoseStableCount = 0;
      studentFaceLastPose = null;
      if (message) message.textContent = result?.message || 'Đưa khuôn mặt rõ vào giữa khung hình để tự chụp.';
      return;
    }

    const matched = result.pose === current.key;
    if (matched && studentFaceLastPose === result.pose) {
      studentFacePoseStableCount += 1;
    } else {
      studentFacePoseStableCount = matched ? 1 : 0;
      studentFaceLastPose = result.pose;
    }

    if (matched) {
      if (message) message.textContent = `Đúng tư thế “${current.label}” (${studentFacePoseStableCount}/${STUDENT_FACE_AUTO_STABLE_FRAMES}). Giữ yên...`;
      if (studentFacePoseStableCount >= STUDENT_FACE_AUTO_STABLE_FRAMES) {
        studentFacePoseStableCount = 0;
        studentFaceLastPose = null;
        await captureStudentFaceRequestImage(true);
      }
    } else if (message) {
      message.textContent = `Cần: ${current.label}. Hệ thống đang thấy: ${studentFacePoseLabel(result.pose)}. Bạn có thể giữ tư thế để tự chụp hoặc bấm Chụp thủ công.`;
    }
  } catch (error) {
    if (message) message.textContent = 'Không tự nhận diện được tư thế. Bạn vẫn có thể bấm Chụp thủ công.';
  } finally {
    studentFacePoseBusy = false;
  }
}

async function captureStudentFaceRequestImage(autoCapture = false) {
  const step = currentStudentFaceRequestStep();
  const video = document.getElementById('studentFaceRequestVideo');
  const canvas = document.getElementById('studentFaceRequestCanvas');
  const message = document.getElementById('studentFaceCaptureMessage');
  if (!step || !video || !canvas || studentFaceCaptureBusy) return;
  if (!studentFaceRequestStream || video.videoWidth < 2 || video.videoHeight < 2) {
    if (message) message.textContent = 'Camera chưa sẵn sàng. Hãy chờ một chút rồi thử lại.';
    return;
  }
  studentFaceCaptureBusy = true;
  renderStudentFaceRequestCapture();
  try {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    if (!blob) {
      if (message) message.textContent = 'Không chụp được ảnh, vui lòng thử lại.';
      return;
    }
    studentFaceRequestCaptures.set(step.key, { blob, url: URL.createObjectURL(blob) });
    if (message) message.textContent = currentStudentFaceRequestStep()
      ? `${autoCapture ? 'Đã tự chụp' : 'Đã chụp'} ${step.label}. Tiếp theo: ${currentStudentFaceRequestStep().label}.`
      : 'Đã chụp đủ 5 ảnh. Tích xác nhận và gửi yêu cầu.';
  } finally {
    studentFaceCaptureBusy = false;
    renderStudentFaceRequestCapture();
  }
}

async function submitStudentFaceRequest() {
  const message = document.getElementById('studentFaceCaptureMessage');
  const consent = document.getElementById('studentFaceRequestConsent');
  const submitButton = document.getElementById('studentFaceSubmitRequestBtn');
  if (currentStudentFaceRequestStep()) {
    if (message) message.textContent = 'Vui lòng chụp đủ 5 ảnh trước khi gửi.';
    return;
  }
  if (!consent?.checked) {
    if (message) message.textContent = 'Bạn cần xác nhận trước khi gửi yêu cầu.';
    return;
  }
  const form = new FormData();
  STUDENT_FACE_REQUEST_STEPS.forEach((step) => {
    const capture = studentFaceRequestCaptures.get(step.key);
    form.append('files', new File([capture.blob], `${step.key}.jpg`, { type: 'image/jpeg' }));
  });
  form.append('note', document.getElementById('studentFaceRequestNote')?.value.trim() || '');
  if (submitButton) submitButton.disabled = true;
  if (message) message.textContent = 'Đang kiểm tra ảnh và gửi yêu cầu...';
  try {
    const response = await fetch('/api/student/face-registration/request', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: csrfHeaders(),
      body: form,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiErrorMessage(data.detail));
    closeStudentFaceRequestCapture();
    await loadStudentFaces();
  } catch (error) {
    if (message) message.textContent = error.message || 'Không gửi được yêu cầu.';
    renderStudentFaceRequestCapture();
  }
}

async function cancelStudentFaceRequest(requestId) {
  if (!confirm('Hủy yêu cầu đăng ký FaceID này?')) return;
  try {
    await api(`/api/student/face-registration/${requestId}/cancel`, { method: 'PATCH' });
    await loadStudentFaces();
  } catch (error) {
    alert(error.message || 'Không hủy được yêu cầu.');
  }
}

function closeStudentFaceRequestCapture() {
  const video = document.getElementById('studentFaceRequestVideo');
  stopStudentFacePoseAnalyzer();
  if (studentFaceRequestStream) {
    studentFaceRequestStream.getTracks().forEach((track) => track.stop());
  }
  studentFaceRequestStream = null;
  studentFaceScanningStarted = false;
  if (video) video.srcObject = null;
  document.getElementById('studentFaceRequestCaptureModal')?.classList.add('hidden');
  resetStudentFaceRequestCapture();
}

document.addEventListener('change', (event) => {
  if (event.target?.id === 'studentFaceRequestConsent') renderStudentFaceRequestCapture();
});
