const studentPages = {
  overview: ['Tổng quan', 'Thông tin cá nhân và trạng thái điểm danh hôm nay'],
  faceImages: ['FaceID của tôi', 'Gửi ảnh đăng ký và theo dõi trạng thái duyệt FaceID'],
  attendance: ['Điểm danh', 'Lọc bản ghi điểm danh theo ngày và trạng thái'],
  leaveRequests: ['Đơn nghỉ phép', 'Tạo đơn và theo dõi trạng thái xử lý'],
  studentReports: ['Báo cáo của tôi', 'Nộp báo cáo cho giáo viên và xem phản hồi'],
  logs: ['Lịch sử ra/vào', 'Lọc lịch sử check-in/check-out theo ngày'],
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  })[char]);
}

function cookieValue(name) {
  return document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=') || '';
}

function csrfHeaders() {
  const token = cookieValue('csrf_token');
  return token ? { 'X-CSRF-Token': decodeURIComponent(token) } : {};
}

async function api(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = {
    ...(method === 'GET' ? {} : csrfHeaders()),
    ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(url, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...options,
    headers,
  });
  if (res.status === 401) {
    location.replace('/login');
    return null;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data.detail));
  return data;
}

function apiErrorMessage(detail) {
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || 'Dữ liệu chưa hợp lệ.').join(' | ');
  }
  if (detail && typeof detail === 'object') return detail.message || 'Có lỗi xảy ra.';
  return detail || 'Có lỗi xảy ra.';
}

function todayDateValue() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function getInputValue(id) {
  return document.getElementById(id)?.value || '';
}

function setInputValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value;
}

function appendFilter(params, id, key) {
  const value = getInputValue(id);
  if (value) params.set(key, value);
}

function fmtDate(value) {
  if (!value) return '-';
  const [year, month, day] = String(value).split('-');
  return day && month && year ? `${day}/${month}/${year}` : value;
}

function fmtDateTime(value) {
  if (!value) return '-';
  return String(value).replace('T', ' ');
}

function timeText(value) {
  if (!value) return '--:--';
  const time = String(value).split('T')[1] || String(value);
  return time.slice(0, 5) || '--:--';
}

function minutesText(value) {
  const minutes = Number(value || 0);
  return minutes > 0 ? `${minutes}p` : '-';
}

function totalMinutesText(value) {
  const minutes = Number(value || 0);
  if (minutes <= 0) return '-';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest}p`;
  return rest ? `${hours}h ${rest}p` : `${hours}h`;
}

function actionLabel(action) {
  if (action === 'check_in') return 'Check-in';
  if (action === 'check_out') return 'Check-out';
  return action || '-';
}

function resultLabel(result) {
  if (result === 'success') return 'Thành công';
  if (result === 'denied') return 'Không ghi nhận';
  if (result === 'warning') return 'Cảnh báo';
  return result || '-';
}

function resultBadge(result) {
  let cls = result === 'success' ? 'badge-success' : 'badge-neutral';
  if (result === 'denied') cls = 'badge-denied';
  if (result === 'warning') cls = 'badge-warning';
  return `<span class="badge ${cls}">${escapeHtml(resultLabel(result))}</span>`;
}

function statusLabel(status) {
  const labels = {
    present_on_time: 'Đúng giờ',
    late: 'Đi muộn',
    early_leave: 'Về sớm',
    late_and_early_leave: 'Muộn + về sớm',
    missing_checkout: 'Thiếu check-out',
    absent: 'Vắng',
    leave_approved: 'Nghỉ có phép',
    leave_pending: 'Chờ duyệt nghỉ',
    pending: 'Chưa ghi nhận',
    unfinalized: 'Chưa chốt',
    off_day: 'Ngày nghỉ',
  };
  return labels[status] || status || '-';
}

function statusClass(status) {
  if (status === 'present_on_time') return 'attendance-ok';
  if (status === 'late') return 'attendance-late';
  if (status === 'early_leave') return 'attendance-early';
  if (status === 'late_and_early_leave') return 'attendance-mixed';
  if (status === 'missing_checkout') return 'attendance-missing';
  if (status === 'absent') return 'attendance-absent';
  if (status === 'leave_approved') return 'attendance-ok';
  if (status === 'leave_pending') return 'attendance-pending';
  if (status === 'unfinalized') return 'attendance-unfinalized';
  if (status === 'off_day') return 'attendance-off-day';
  return 'attendance-pending';
}

function statusBadge(status) {
  return `<span class="attendance-status ${statusClass(status)}">${escapeHtml(statusLabel(status))}</span>`;
}

function presenceLabel(status) {
  if (status === 'in_lab') return 'Trong lab';
  if (status === 'out_of_lab') return 'Ngoài lab';
  return '-';
}

function presenceClass(status) {
  if (status === 'in_lab') return 'presence-in';
  if (status === 'out_of_lab') return 'presence-out';
  return 'presence-none';
}

function presenceBadge(status) {
  return `<span class="presence-status ${presenceClass(status)}">${escapeHtml(presenceLabel(status))}</span>`;
}

function showStudentPage(id) {
  if (!studentPages[id]) id = 'overview';
  document.querySelectorAll('.page').forEach((page) => page.classList.remove('active-page'));
  document.getElementById(id).classList.add('active-page');
  document.querySelectorAll('.nav-item[data-student-page]').forEach((btn) => btn.classList.toggle('active', btn.dataset.studentPage === id));
  document.getElementById('pageTitle').textContent = studentPages[id][0];
  document.getElementById('pageSubtitle').textContent = studentPages[id][1];
  if (id === 'overview') loadStudentOverview();
  if (id === 'faceImages') loadStudentFaces();
  if (id === 'attendance') loadStudentAttendance();
  if (id === 'leaveRequests') loadStudentLeaveRequests();
  if (id === 'studentReports') loadStudentReports();
  if (id === 'logs') loadStudentLogs();
}

document.querySelectorAll('.nav-item[data-student-page]').forEach((btn) => {
  btn.addEventListener('click', () => showStudentPage(btn.dataset.studentPage));
});

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: csrfHeaders() });
  location.replace('/login');
});

async function loadProfile() {
  const me = await api('/api/student/me');
  if (!me) return;
  const student = me.student || {};
  document.getElementById('studentCode').textContent = student.student_code || '-';
  document.getElementById('fullName').textContent = student.full_name || '-';
  document.getElementById('className').textContent = student.class_name || '-';
  document.getElementById('faceCount').textContent = student.face_count ?? 0;
  document.getElementById('currentStudentPill').textContent = `${student.student_code || me.user?.username || 'student'} · Sinh viên`;
}

function initFilters() {
  const today = todayDateValue();
  ['attendanceDateFrom', 'attendanceDateTo', 'logDateFrom', 'logDateTo', 'leaveStartDate', 'leaveEndDate'].forEach((id) => setInputValue(id, today));
}

function resetStudentAttendanceToday() {
  const today = todayDateValue();
  setInputValue('attendanceDateFrom', today);
  setInputValue('attendanceDateTo', today);
  setInputValue('attendanceStatusFilter', '');
  loadStudentAttendance();
}

function clearStudentAttendanceDates() {
  setInputValue('attendanceDateFrom', '');
  setInputValue('attendanceDateTo', '');
  setInputValue('attendanceStatusFilter', '');
  loadStudentAttendance();
}

function resetStudentLogsToday() {
  const today = todayDateValue();
  setInputValue('logDateFrom', today);
  setInputValue('logDateTo', today);
  setInputValue('logActionFilter', '');
  setInputValue('logResultFilter', '');
  loadStudentLogs();
}

function clearStudentLogDates() {
  setInputValue('logDateFrom', '');
  setInputValue('logDateTo', '');
  setInputValue('logActionFilter', '');
  setInputValue('logResultFilter', '');
  loadStudentLogs();
}

function renderTodayAttendance(item) {
  if (!item) {
    return '<div class="empty-state">Hôm nay chưa có bản ghi điểm danh.</div>';
  }
  return `
    <div class="student-summary-row"><span>Trạng thái</span><strong>${statusBadge(item.status)}</strong></div>
    <div class="student-summary-row"><span>Vào đầu</span><strong>${escapeHtml(timeText(item.first_check_in_at))}</strong></div>
    <div class="student-summary-row"><span>Ra cuối</span><strong>${escapeHtml(timeText(item.last_check_out_at))}</strong></div>
    <div class="student-summary-row"><span>Tổng thời gian</span><strong>${escapeHtml(totalMinutesText(item.total_minutes))}</strong></div>
    ${item.note ? `<div class="student-summary-row"><span>Ghi chú</span><strong>${escapeHtml(item.note)}</strong></div>` : ''}
  `;
}

function renderTodayLogs(items) {
  if (!items.length) return '<div class="empty-state">Hôm nay chưa có lịch sử ra/vào.</div>';
  return items.slice(0, 5).map((item) => `
    <div class="student-summary-row">
      <span>${escapeHtml(timeText(item.created_at))} · ${escapeHtml(actionLabel(item.action))}</span>
      <strong>${resultBadge(item.result)}</strong>
    </div>
  `).join('');
}

async function loadStudentOverview() {
  const today = todayDateValue();
  const attendance = await api(`/api/student/attendance-records?limit=1&date_from=${today}&date_to=${today}`);
  const logs = await api(`/api/student/access-logs?limit=5&date_from=${today}&date_to=${today}`);
  document.getElementById('todayAttendanceSummary').innerHTML = renderTodayAttendance(attendance?.items?.[0]);
  document.getElementById('todayLogSummary').innerHTML = renderTodayLogs(logs?.items || []);
}

function renderStudentFaceItem(face, index) {
  const imagePath = face?.id ? `/api/files/face/${encodeURIComponent(face.id)}` : '';
  const imageArg = escapeHtml(JSON.stringify(imagePath));
  return `<article class="face-gallery-item">
    <img class="face-gallery-thumb" src="${escapeHtml(imagePath)}" alt="Ảnh đăng ký ${index}" loading="lazy" onclick="openStudentFaceModal(${imageArg})" />
    <div class="face-gallery-meta">${escapeHtml(fmtDateTime(face.created_at))}</div>
    <div class="student-face-actions">
      <button type="button" onclick="openStudentFaceModal(${imageArg})">Xem ảnh</button>
    </div>
  </article>`;
}

function openStudentFaceModal(imagePath) {
  const modal = document.getElementById('studentFaceModal');
  const img = document.getElementById('studentFaceModalImg');
  if (!modal || !img || !imagePath) return;
  img.src = imagePath;
  modal.classList.remove('hidden');
}

function closeStudentFaceModal() {
  const modal = document.getElementById('studentFaceModal');
  const img = document.getElementById('studentFaceModalImg');
  if (modal) modal.classList.add('hidden');
  if (img) img.src = '';
}

async function loadStudentFaces() {
  const data = await api('/api/student/faces');
  const items = data?.items || [];
  const count = data?.count ?? items.length;
  const maxFaces = data?.max_faces || 10;
  document.getElementById('studentFaceStatus').textContent = count > 0 ? 'Đã đăng ký' : 'Chưa đăng ký';
  document.getElementById('studentFaceCount').textContent = `${count}/${maxFaces} mẫu`;
  document.getElementById('studentFaceLatest').textContent = data?.latest_update ? fmtDateTime(data.latest_update) : '-';
  document.getElementById('faceCount').textContent = count;
  document.getElementById('studentFaceGallery').innerHTML = items.length
    ? items.map((face, index) => renderStudentFaceItem(face, index + 1)).join('')
    : '<div class="empty-state">Bạn chưa có ảnh đăng ký khuôn mặt.</div>';
  if (window.loadStudentFaceRegistration) await window.loadStudentFaceRegistration(data);
}

function renderAttendanceRow(item) {
  return `<tr>
    <td>${escapeHtml(fmtDate(item.attendance_date))}</td>
    <td>${escapeHtml(timeText(item.first_check_in_at))}</td>
    <td>${escapeHtml(timeText(item.last_check_out_at))}</td>
    <td>${statusBadge(item.status)}</td>
    <td>${presenceBadge(item.presence_status)}</td>
    <td>${escapeHtml(minutesText(item.late_minutes))}</td>
    <td>${escapeHtml(minutesText(item.early_leave_minutes))}</td>
    <td>${escapeHtml(totalMinutesText(item.total_minutes))}</td>
    <td>${escapeHtml(item.note || '')}</td>
  </tr>`;
}

async function loadStudentAttendance() {
  const params = new URLSearchParams({ limit: '300' });
  appendFilter(params, 'attendanceDateFrom', 'date_from');
  appendFilter(params, 'attendanceDateTo', 'date_to');
  appendFilter(params, 'attendanceStatusFilter', 'status');
  const data = await api(`/api/student/attendance-records?${params.toString()}`);
  const items = data?.items || [];
  document.getElementById('attendanceRows').innerHTML = items.map(renderAttendanceRow).join('') || '<tr><td colspan="9">Chưa có dữ liệu điểm danh.</td></tr>';
  document.getElementById('attendanceCount').textContent = `Tìm thấy ${data?.count ?? items.length} bản ghi`;
}

function logTone(item) {
  if (item.result === 'success') return item.action === 'check_out' ? 'tone-checkout' : 'tone-success';
  if (item.result === 'denied') return 'tone-denied';
  if (item.result === 'warning') return 'tone-warning';
  return 'tone-neutral';
}

function renderLogItem(item) {
  return `<article class="log-item ${logTone(item)}">
    <div class="log-time"><strong>${escapeHtml(timeText(item.created_at))}</strong><span>${escapeHtml(fmtDate(String(item.created_at || '').slice(0, 10)))}</span></div>
    <div class="log-node"></div>
    <div class="log-panel">
      <div class="log-main">
        <div class="log-title">${escapeHtml(actionLabel(item.action))}</div>
        <div class="log-name">${resultBadge(item.result)}</div>
        <div class="log-meta">
          <span>${escapeHtml(item.confidence == null ? 'Không có độ tin cậy' : `Độ tin cậy: ${Number(item.confidence).toFixed(3)}`)}</span>
        </div>
        ${item.note ? `<div class="log-note">${escapeHtml(item.note)}</div>` : ''}
      </div>
      <div class="log-evidence">${item.evidence_image_path ? `<img class="log-evidence-img" src="${escapeHtml(item.evidence_image_path)}" alt="Ảnh bằng chứng" loading="lazy" />` : '<div class="log-evidence-empty"><span>Chưa có ảnh</span></div>'}</div>
    </div>
  </article>`;
}

async function loadStudentLogs() {
  const params = new URLSearchParams({ limit: '200' });
  appendFilter(params, 'logDateFrom', 'date_from');
  appendFilter(params, 'logDateTo', 'date_to');
  appendFilter(params, 'logActionFilter', 'action');
  appendFilter(params, 'logResultFilter', 'result');
  const data = await api(`/api/student/access-logs?${params.toString()}`);
  const items = (data?.items || []).map((item) => ({
    ...item,
    evidence_image_path: item?.evidence_image_path && item?.id ? `/api/files/evidence/access-log/${encodeURIComponent(item.id)}` : '',
  }));
  document.getElementById('logsTimeline').innerHTML = items.map(renderLogItem).join('') || '<div class="empty-state">Chưa có dữ liệu lịch sử.</div>';
  document.getElementById('logsCount').textContent = `Tìm thấy ${data?.count ?? items.length} bản ghi`;
}

(async function init() {
  try {
    initFilters();
    await loadProfile();
    await loadStudentOverview();
    if (location.search) history.replaceState({}, '', '/');
  } catch (err) {
    alert(err.message);
  }
})();
