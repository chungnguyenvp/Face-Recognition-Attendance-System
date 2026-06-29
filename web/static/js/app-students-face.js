async function loadStudents(q = '', preferredStudentId = null, options = {}) {
  const data = await api('/api/students' + (q ? `?q=${encodeURIComponent(q)}` : ''));
  students = data.items;
  faceMaxEmbeddings = Number(data.max_faces || faceMaxEmbeddings || 10);

  document.getElementById('studentsTable').innerHTML =
    students
      .map(
        (st) => {
          const adminActions = canDeleteSystemData()
            ? `<button class="secondary" onclick="deleteStudent(${st.id})">Xóa</button>`
            : '<span class="role-table-note">Vận hành</span>';
          return `<tr>
    <td>${escapeHtml(st.student_code)}</td><td>${escapeHtml(st.full_name)}</td><td>${escapeHtml(st.class_name || '')}</td><td>${escapeHtml(st.status)}</td><td>${st.face_count > 0 ? 'Đã đăng ký' : 'Chưa đăng ký'}</td>
    <td><button class="text-btn work-time-btn" onclick="openStudentWorkTimeModal(${st.id})">${escapeHtml(studentWorkTimeText(st))}</button></td>
    <td>${adminActions}</td>
  </tr>`;
        }
      )
      .join('') || '<tr><td colspan="7">Chưa có sinh viên</td></tr>';

  const select = document.getElementById('faceStudentSelect');
  if (select) {
    const selectedValue = preferredStudentId !== null ? String(preferredStudentId) : select.value;
    select.innerHTML = students.map((st) => `<option value="${st.id}">${escapeHtml(st.student_code)} - ${escapeHtml(st.full_name)}</option>`).join('');
    if (selectedValue && students.some((st) => String(st.id) === String(selectedValue))) {
      select.value = selectedValue;
    }
    select.onchange = () => {
      resetFaceScanProgress(false);
      updateFaceSampleSummary();
    };
    if (preferredStudentId !== null && options.resetFaceScan !== false) {
      resetFaceScanProgress(false);
    }
    updateFaceSampleSummary();
  }
}

function studentWorkTimeText(student) {
  const start = student?.work_start_time || settings.work_start_time || '08:00';
  const end = student?.work_end_time || settings.work_end_time || '17:00';
  return `${start} - ${end}`;
}

function openStudentWorkTimeModal(studentId) {
  const student = students.find((item) => Number(item.id) === Number(studentId));
  if (!student) return;
  document.getElementById('studentWorkTimeStudentId').value = student.id;
  document.getElementById('studentWorkTimeName').textContent = `${student.student_code} - ${student.full_name}`;
  document.getElementById('studentWorkStartTime').value = student.work_start_time || settings.work_start_time || '08:00';
  document.getElementById('studentWorkEndTime').value = student.work_end_time || settings.work_end_time || '17:00';
  document.getElementById('studentWorkTimeMessage').textContent = '';
  document.getElementById('studentWorkTimeModal').classList.remove('hidden');
}

function closeStudentWorkTimeModal() {
  document.getElementById('studentWorkTimeModal').classList.add('hidden');
}

async function saveStudentWorkTime() {
  const studentId = document.getElementById('studentWorkTimeStudentId').value;
  const msg = document.getElementById('studentWorkTimeMessage');
  msg.textContent = '';
  try {
    await api(`/api/students/${studentId}/work-time`, {
      method: 'PUT',
      body: JSON.stringify({
        work_start_time: document.getElementById('studentWorkStartTime').value || '08:00',
        work_end_time: document.getElementById('studentWorkEndTime').value || '17:00',
      }),
    });
    closeStudentWorkTimeModal();
    await loadStudents(document.getElementById('studentSearch').value);
    await loadDashboard();
    if (document.getElementById('attendance').classList.contains('active-page')) await loadAttendanceRecords();
  } catch (e) {
    msg.textContent = e.message;
  }
}

async function resetStudentWorkTime() {
  const studentId = document.getElementById('studentWorkTimeStudentId').value;
  const msg = document.getElementById('studentWorkTimeMessage');
  msg.textContent = '';
  try {
    await api(`/api/students/${studentId}/work-time`, { method: 'DELETE' });
    closeStudentWorkTimeModal();
    await loadStudents(document.getElementById('studentSearch').value);
    await loadDashboard();
    if (document.getElementById('attendance').classList.contains('active-page')) await loadAttendanceRecords();
  } catch (e) {
    msg.textContent = e.message;
  }
}

function selectedFaceStudent() {
  const select = document.getElementById('faceStudentSelect');
  if (!select || !select.value) return null;
  return students.find((st) => String(st.id) === String(select.value)) || null;
}

function updateFaceSampleSummary(faceCount = null, maxFaces = null) {
  const el = document.getElementById('faceSampleCount');
  const statusEl = document.getElementById('faceSampleStatusText');
  if (!el) return;
  const student = selectedFaceStudent();
  const rawCount = faceCount !== null ? Number(faceCount) : Number(student?.face_count ?? 0);
  const rawMax = maxFaces !== null ? Number(maxFaces) : Number(faceMaxEmbeddings || 10);
  const count = Number.isFinite(rawCount) ? rawCount : 0;
  const max = Number.isFinite(rawMax) && rawMax > 0 ? rawMax : 10;
  el.textContent = `${count}/${max} mẫu`;
  el.title = count > 0 ? 'Xem ảnh khuôn mặt đã đăng ký' : 'Sinh viên này chưa có ảnh khuôn mặt';
  if (statusEl) {
    if (!student) {
      statusEl.textContent = 'Chọn sinh viên để xem bộ mẫu.';
    } else if (count <= 0) {
      statusEl.textContent = 'Chưa có mẫu. Nên quét lại 5 tư thế để tạo bộ nền.';
    } else if (count >= max) {
      statusEl.textContent = `Đủ ${max}/${max}. Thêm mẫu mới sẽ tự bỏ mẫu cũ nhất.`;
    } else {
      statusEl.textContent = `Còn ${max - count} vị trí. Có thể thêm mẫu bằng camera hoặc từ máy.`;
    }
  }
}

async function refreshFaceRegistrationData(studentId) {
  await loadStudents('', studentId, { resetFaceScan: false });
  if (faceGalleryIsOpen()) await loadFaceGallery(studentId);
  await loadDashboard();
}

function faceGalleryIsOpen() {
  const modal = document.getElementById('faceGalleryModal');
  return Boolean(modal && !modal.classList.contains('hidden'));
}

async function openFaceGallery() {
  const student = selectedFaceStudent();
  const modal = document.getElementById('faceGalleryModal');
  const nameEl = document.getElementById('faceGalleryStudentName');
  const grid = document.getElementById('faceGalleryGrid');
  const message = document.getElementById('faceGalleryMessage');
  if (!modal || !grid || !student) return;
  if (nameEl) nameEl.textContent = `${student.student_code} - ${student.full_name}`;
  if (message) message.textContent = '';
  grid.innerHTML = '<div class="detail-empty">Đang tải ảnh khuôn mặt...</div>';
  modal.classList.remove('hidden');
  await loadFaceGallery(student.id);
}

function closeFaceGallery() {
  const modal = document.getElementById('faceGalleryModal');
  if (modal) modal.classList.add('hidden');
}

function faceCreatedAtText(value) {
  if (!value) return 'Không rõ thời gian';
  return String(value).replace('T', ' ');
}

function renderFaceGalleryItem(studentId, face) {
  const imagePath = protectedFaceUrl(face);
  const imageArg = escapeHtml(JSON.stringify(imagePath));
  return `<article class="face-gallery-item">
    <img class="face-gallery-thumb" src="${escapeHtml(imagePath)}" alt="Ảnh khuôn mặt đã đăng ký" loading="lazy" onclick="openFaceGalleryImage(${imageArg})" />
    <div class="face-gallery-meta">${escapeHtml(faceCreatedAtText(face.created_at))}</div>
    <div class="face-gallery-actions">
      <button class="secondary" onclick="openFaceGalleryImage(${imageArg})">Xem</button>
      <button class="danger-lite" onclick="deleteStudentFace(${studentId}, ${face.id})">Xóa</button>
    </div>
  </article>`;
}

function openFaceGalleryImage(imagePath) {
  reopenFaceGalleryAfterEvidence = true;
  closeFaceGallery();
  openEvidenceModal(imagePath, 'Ảnh khuôn mặt đã đăng ký');
}

async function loadFaceGallery(studentId) {
  const grid = document.getElementById('faceGalleryGrid');
  const message = document.getElementById('faceGalleryMessage');
  if (!grid) return;
  try {
    const data = await api(`/api/students/${studentId}`);
    const faces = data.faces || [];
    updateFaceSampleSummary(data.face_count, data.max_faces);
    grid.innerHTML = faces.length
      ? faces.map((face) => renderFaceGalleryItem(studentId, face)).join('')
      : '<div class="detail-empty">Sinh viên này chưa có ảnh khuôn mặt.</div>';
    if (message) message.textContent = faces.length ? `Đang có ${faces.length}/${data.max_faces || faceMaxEmbeddings} mẫu khuôn mặt.` : '';
  } catch (e) {
    grid.innerHTML = '';
    if (message) message.textContent = e.message || 'Không tải được ảnh khuôn mặt.';
  }
}

async function deleteStudentFace(studentId, faceId) {
  if (!confirm('Xóa ảnh khuôn mặt này khỏi bộ mẫu nhận diện?')) return;
  const message = document.getElementById('faceGalleryMessage');
  if (message) message.textContent = '';
  try {
    await api(`/api/students/${studentId}/faces/${faceId}`, { method: 'DELETE' });
    await loadStudents(document.getElementById('studentSearch')?.value || '');
    await loadFaceGallery(studentId);
    await loadDashboard();
  } catch (e) {
    if (message) message.textContent = e.message || 'Không xóa được ảnh khuôn mặt.';
  }
}

function applySettingsInputLimits() {
  [
    ['settingThreshold', '0', '1', '0.01'],
    ['settingCooldown', '1', null, '1'],
    ['settingFrameSkip', '1', null, '1'],
    ['settingLateGraceMinutes', '0', '240', '1'],
    ['settingEarlyLeaveGraceMinutes', '0', '240', '1'],
  ].forEach(([id, min, max, step]) => {
    const input = document.getElementById(id);
    if (!input) return;
    input.min = min;
    if (max !== null) input.max = max;
    input.step = step;
  });
}

function openStudentModal() {
  document.getElementById('studentCode').value = '';
  document.getElementById('studentName').value = '';
  document.getElementById('studentClass').value = '';
  document.getElementById('studentModalMessage').textContent = '';
  document.getElementById('studentModal').classList.remove('hidden');
  document.getElementById('studentCode').focus();
}

function closeStudentModal() {
  document.getElementById('studentModal').classList.add('hidden');
}

async function createStudent() {
  const msg = document.getElementById('studentModalMessage');
  const studentCode = document.getElementById('studentCode').value.trim();
  const fullName = document.getElementById('studentName').value.trim();
  const className = document.getElementById('studentClass').value.trim();
  msg.textContent = '';
  if (!studentCode || !fullName) {
    msg.textContent = 'Vui lòng nhập mã sinh viên và họ tên.';
    return;
  }
  try {
    const result = await api('/api/students', {
      method: 'POST',
      body: JSON.stringify({
        student_code: studentCode,
        full_name: fullName,
        class_name: className,
        status: 'active',
      }),
    });
    closeStudentModal();
    await loadStudents('', result?.id || null);
    await loadDashboard();
  } catch (e) {
    msg.textContent = e.message;
  }
}

async function deleteStudent(id) {
  if (!canDeleteSystemData()) return;
  if (!confirm('Xóa sinh viên này và toàn bộ ảnh khuôn mặt?')) return;
  await api(`/api/students/${id}`, { method: 'DELETE' });
  await loadStudents();
  await loadDashboard();
}

async function uploadFaceFile(studentId, file) {
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`/api/students/${studentId}/faces/upload`, { method: 'POST', body: form, credentials: 'same-origin', cache: 'no-store', headers: csrfHeaders() });
    if (res.status === 401) {
      window.location.href = '/login';
      return { ok: false, data: { detail: 'Phiên đăng nhập đã hết hạn.' } };
    }
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  } catch (e) {
    return { ok: false, data: { detail: e.message || 'Không gửi được ảnh lên server.' } };
  }
}

function duplicateWarningsText(warnings) {
  if (!warnings || !warnings.length) return '';
  const bestByStudent = new Map();
  warnings.forEach((item) => {
    const key = item.student_id || item.student_code;
    const current = bestByStudent.get(key);
    if (!current || Number(item.score || 0) > Number(current.score || 0)) {
      bestByStudent.set(key, item);
    }
  });
  return Array.from(bestByStudent.values())
    .map((item) => {
      const score = item.score !== undefined ? Number(item.score).toFixed(4) : '';
      return `${item.student_code || item.student_id} - ${item.full_name || ''}${score ? ` (${score})` : ''}`;
    })
    .join(', ');
}

async function uploadSupplementalFaces() {
  const studentId = document.getElementById('faceStudentSelect').value;
  const input = document.getElementById('supplementalFaceInput');
  const msg = document.getElementById('supplementalFaceMessage');
  const files = Array.from(input?.files || []);
  if (!studentId) {
    msg.textContent = 'Vui lòng chọn sinh viên trước khi thêm ảnh.';
    return;
  }
  if (!files.length) {
    msg.textContent = 'Vui lòng chọn ít nhất 1 ảnh.';
    return;
  }

  let successCount = 0;
  const failures = [];
  const duplicateWarnings = [];
  for (let i = 0; i < files.length; i += 1) {
    msg.textContent = `Đang thêm ảnh ${i + 1}/${files.length}...`;
    const result = await uploadFaceFile(studentId, files[i]);
    if (result.ok) {
      successCount += 1;
      duplicateWarnings.push(...(result.data.duplicate_warnings || []));
      if (result.data.face_count !== undefined) {
        updateFaceSampleSummary(result.data.face_count, result.data.max_faces);
      }
    } else {
      failures.push(`${files[i].name}: ${apiErrorMessage(result.data.detail) || 'không thêm được'}`);
    }
  }

  input.value = '';
  await loadStudents();
  if (faceGalleryIsOpen()) await loadFaceGallery(studentId);
  if (failures.length) {
    msg.textContent = `Đã thêm ${successCount}/${files.length} ảnh. Lỗi: ${failures.join(' | ')}`;
  } else {
    msg.textContent = `Đã thêm ${successCount}/${files.length} ảnh vào bộ mẫu. Hệ thống tự giữ tối đa ${faceMaxEmbeddings} mẫu mới nhất.`;
  }
  const duplicateText = duplicateWarningsText(duplicateWarnings);
  if (duplicateText) {
    msg.textContent += ` Cảnh báo trùng khuôn mặt với: ${duplicateText}`;
  }
}

function updateFaceRegisterToggleButton(running) {
  const btn = document.getElementById('faceRegisterToggleBtn');
  if (!btn) return;
  btn.textContent = running ? 'Tắt camera' : 'Bật camera';
  btn.classList.toggle('secondary', running);
}

async function toggleFaceRegisterCamera() {
  if (faceRegisterStream) {
    stopFaceRegisterCamera(true);
    return;
  }
  await startFaceRegisterCamera();
}

async function startFaceRegisterCamera() {
  const msg = document.getElementById('faceRegisterMessage');
  const video = document.getElementById('faceRegisterVideo');
  msg.textContent = '';
  if (faceRegisterStream) {
    renderFaceScanGuide();
    updateFaceRegisterToggleButton(true);
    return;
  }
  try {
    stopAllRealtimeCameras(false);
    faceRegisterStream = await navigator.mediaDevices.getUserMedia({ video: { width: 960, height: 540 }, audio: false });
    video.srcObject = faceRegisterStream;
    await new Promise((resolve) => {
      video.onloadedmetadata = resolve;
    });
    renderFaceScanGuide();
    if (faceRegisterMode === 'replace') startFacePoseAnalyzer();
    updateFaceRegisterToggleButton(true);
    const steps = getFaceScanSteps();
    msg.textContent = faceRegisterMode === 'replace'
      ? `Camera đăng ký đã bật. Giữ tư thế: ${steps[faceScanStepIndex].label}`
      : 'Camera đăng ký đã bật. Giữ mặt rõ trong khung rồi chụp thêm mẫu.';
  } catch (e) {
    faceRegisterStream = null;
    updateFaceRegisterToggleButton(false);
    msg.textContent = e.message || 'Không bật được camera.';
  }
}

function stopFaceRegisterCamera(showMessage = true) {
  stopFacePoseAnalyzer();
  if (faceRegisterStream) {
    faceRegisterStream.getTracks().forEach((t) => t.stop());
    faceRegisterStream = null;
  }
  const video = document.getElementById('faceRegisterVideo');
  const canvas = document.getElementById('faceRegisterCanvas');
  if (video) video.srcObject = null;
  if (canvas) {
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  if (showMessage) {
    const msg = document.getElementById('faceRegisterMessage');
    if (msg) msg.textContent = 'Đã tắt camera đăng ký.';
  }
  updateFaceRegisterToggleButton(false);
}

async function captureFaceFromCamera() {
  if (faceRegisterMode === 'append') {
    await captureAppendFaceFromCamera();
    return;
  }
  await captureCurrentFaceStep(false);
}

function startFacePoseAnalyzer() {
  stopFacePoseAnalyzer();
  faceAnalyzeTimer = setInterval(analyzeFaceRegisterFrame, FACE_ANALYZE_INTERVAL_MS);
  analyzeFaceRegisterFrame();
}

function stopFacePoseAnalyzer() {
  if (faceAnalyzeTimer) clearInterval(faceAnalyzeTimer);
  faceAnalyzeTimer = null;
  faceAnalyzeBusy = false;
  facePoseStableCount = 0;
  faceLastPose = null;
}

function drawFaceRegisterFrame(quality = 0.9) {
  const video = document.getElementById('faceRegisterVideo');
  const canvas = document.getElementById('faceRegisterCanvas');
  if (!video || !canvas || video.videoWidth < 2 || video.videoHeight < 2) return null;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', quality);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  return dataUrl;
}

async function captureAppendFaceFromCamera() {
  const msg = document.getElementById('faceRegisterMessage');
  const studentId = document.getElementById('faceStudentSelect').value;
  const video = document.getElementById('faceRegisterVideo');
  const canvas = document.getElementById('faceRegisterCanvas');
  if (msg) msg.textContent = '';
  if (faceScanBusy) return;
  if (!studentId) {
    if (msg) msg.textContent = 'Vui lòng chọn sinh viên trước khi thêm mẫu.';
    return;
  }
  if (!faceRegisterStream || !video?.srcObject) {
    if (msg) msg.textContent = 'Vui lòng bật camera đăng ký.';
    return;
  }
  if (video.videoWidth < 2 || video.videoHeight < 2) {
    if (msg) msg.textContent = 'Camera chưa sẵn sàng, thử lại sau vài giây.';
    return;
  }

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!blob) {
    if (msg) msg.textContent = 'Không chụp được ảnh từ camera.';
    return;
  }

  faceScanBusy = true;
  renderFaceScanGuide();
  if (msg) msg.textContent = 'Đang thêm mẫu từ camera...';
  try {
    const file = new File([blob], `capture_add_${Date.now()}.jpg`, { type: 'image/jpeg' });
    const result = await uploadFaceFile(studentId, file);
    if (!result.ok) {
      throw new Error(apiErrorMessage(result.data.detail) || 'Không thêm được mẫu từ camera.');
    }
    updateFaceSampleSummary(result.data.face_count, result.data.max_faces);
    await loadStudents(document.getElementById('studentSearch')?.value || '');
    if (faceGalleryIsOpen()) await loadFaceGallery(studentId);
    await loadDashboard();
    if (msg) {
      msg.textContent = `Đã thêm 1 mẫu từ camera. Hệ thống tự giữ tối đa ${result.data.max_faces || faceMaxEmbeddings} mẫu mới nhất.`;
      const duplicateText = duplicateWarningsText(result.data.duplicate_warnings || []);
      if (duplicateText) msg.textContent += ` Cảnh báo trùng khuôn mặt với: ${duplicateText}`;
    }
  } catch (e) {
    if (msg) msg.textContent = e.message || 'Không thêm được mẫu từ camera.';
  } finally {
    faceScanBusy = false;
    renderFaceScanGuide();
  }
}

async function analyzeFaceRegisterFrame() {
  if (faceRegisterMode !== 'replace' || faceAnalyzeBusy || faceScanBusy || !faceRegisterStream) return;
  const steps = getFaceScanSteps();
  if (faceScanCompleted.size >= steps.length) return;

  const msg = document.getElementById('faceRegisterMessage');
  const currentStep = steps[faceScanStepIndex];
  const image = drawFaceRegisterFrame(0.72);
  if (!image) return;

  faceAnalyzeBusy = true;
  try {
    const result = await api('/api/students/face-scan/analyze', {
      method: 'POST',
      body: JSON.stringify({ image }),
    });
    if (!result || !result.ok) {
      facePoseStableCount = 0;
      faceLastPose = null;
      if (msg) msg.textContent = result?.message || 'Đưa mặt rõ vào giữa khung.';
      return;
    }

    const matched = result.pose === currentStep.key;
    if (matched && faceLastPose === result.pose) {
      facePoseStableCount += 1;
    } else {
      facePoseStableCount = matched ? 1 : 0;
      faceLastPose = result.pose;
    }

    if (matched) {
      if (msg) msg.textContent = `Đúng tư thế "${currentStep.label}" (${facePoseStableCount}/${FACE_AUTO_STABLE_FRAMES}). Giữ yên...`;
      if (facePoseStableCount >= FACE_AUTO_STABLE_FRAMES) {
        facePoseStableCount = 0;
        faceLastPose = null;
        await captureCurrentFaceStep(true);
      }
    } else if (msg) {
      msg.textContent = `Cần: ${currentStep.label}. Hiện tại hệ thống thấy: ${poseLabel(result.pose)}.`;
    }
  } catch (e) {
    if (msg) msg.textContent = e.message || 'Không phân tích được tư thế.';
  } finally {
    faceAnalyzeBusy = false;
  }
}

function poseLabel(pose) {
  const item = FACE_SCAN_STEPS.find((step) => step.key === pose);
  return item ? item.label : pose || 'chưa rõ';
}

async function captureCurrentFaceStep(autoCapture) {
  const msg = document.getElementById('faceRegisterMessage');
  const studentId = document.getElementById('faceStudentSelect').value;
  const video = document.getElementById('faceRegisterVideo');
  const canvas = document.getElementById('faceRegisterCanvas');
  msg.textContent = '';
  if (faceScanBusy) return;
  if (!studentId) {
    msg.textContent = 'Vui lòng chọn sinh viên trước khi quét.';
    return;
  }
  const steps = getFaceScanSteps();
  if (faceScanCompleted.size >= steps.length) {
    if (faceScanUploadComplete) {
      msg.textContent = 'Đã hoàn tất toàn bộ tư thế quét và lưu bộ khuôn mặt.';
      renderFaceScanGuide();
      return;
    }
    faceScanBusy = true;
    renderFaceScanGuide();
    try {
      const uploaded = await uploadCapturedFaceScan(studentId, steps);
      if (uploaded) await refreshFaceRegistrationData(studentId);
    } finally {
      faceScanBusy = false;
      renderFaceScanGuide();
    }
    return;
  }
  if (!faceRegisterStream || !video.srcObject) {
    msg.textContent = 'Vui lòng bật camera đăng ký.';
    return;
  }
  if (video.videoWidth < 2 || video.videoHeight < 2) {
    msg.textContent = 'Camera chưa sẵn sàng, thử lại sau vài giây.';
    return;
  }

  const currentStep = steps[faceScanStepIndex];
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!blob) {
    msg.textContent = 'Không chụp được ảnh từ camera.';
    return;
  }

  faceScanBusy = true;
  msg.textContent = `${autoCapture ? 'Tự chụp' : 'Đã chụp'} bước ${faceScanStepIndex + 1}/${steps.length}: ${currentStep.label}`;
  renderFaceScanGuide();

  try {
    faceScanUploadComplete = false;
    faceScanCaptures.set(currentStep.key, { blob, label: currentStep.label });
    faceScanCompleted.add(currentStep.key);
    const nextIndex = steps.findIndex((step) => !faceScanCompleted.has(step.key));
    if (nextIndex === -1) {
      renderFaceScanGuide();
      const uploaded = await uploadCapturedFaceScan(studentId, steps);
      if (uploaded) await refreshFaceRegistrationData(studentId);
    } else {
      faceScanStepIndex = nextIndex;
      msg.textContent = `Đã lưu "${currentStep.label}". Giữ tư thế tiếp theo: ${steps[nextIndex].label}`;
    }
  } finally {
    faceScanBusy = false;
    renderFaceScanGuide();
  }
}

async function uploadCapturedFaceScan(studentId, steps) {
  const msg = document.getElementById('faceRegisterMessage');
  const form = new FormData();
  const missing = [];

  for (const step of steps) {
    const capture = faceScanCaptures.get(step.key);
    if (!capture) {
      missing.push(step.label);
      continue;
    }
    const file = new File([capture.blob], `capture_${step.key}_${Date.now()}.jpg`, { type: 'image/jpeg' });
    form.append('files', file);
  }

  if (missing.length) {
    msg.textContent = `Chưa có ảnh cho: ${missing.join(', ')}`;
    faceScanUploadComplete = false;
    return false;
  }

  msg.textContent = `Đã chụp đủ ${steps.length}/${steps.length}. Đang cập nhật bộ khuôn mặt mới...`;
  try {
    const res = await fetch(`/api/students/${studentId}/faces/scan`, { method: 'POST', body: form, credentials: 'same-origin', cache: 'no-store', headers: csrfHeaders() });
    if (res.status === 401) {
      window.location.href = '/login';
      return false;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(apiErrorMessage(data.detail) || 'Không cập nhật được bộ khuôn mặt.');
    }
    updateFaceSampleSummary(data.face_count, data.max_faces);
    msg.textContent = `Hoàn tất ${data.face_count}/${steps.length} tư thế. Đã thay thế bộ khuôn mặt cũ.`;
    const duplicateText = duplicateWarningsText(data.duplicate_warnings || []);
    if (duplicateText) {
      msg.textContent += ` Cảnh báo trùng khuôn mặt với: ${duplicateText}`;
    }
    faceScanUploadComplete = true;
    stopFacePoseAnalyzer();
    return true;
  } catch (e) {
    faceScanUploadComplete = false;
    msg.textContent = e.message || 'Không cập nhật được bộ khuôn mặt.';
    return false;
  }
}
