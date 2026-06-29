let students = [];
let settings = {};
let currentUser = null;
let cameraDevices = [];
let faceRegisterStream = null;
let faceScanBusy = false;
let faceScanCaptures = new Map();
let faceAnalyzeTimer = null;
let faceAnalyzeBusy = false;
let facePoseStableCount = 0;
let faceLastPose = null;
let faceMaxEmbeddings = 10;
let faceRegisterMode = 'append';
let reopenFaceGalleryAfterEvidence = false;
const shownRealtimeNotices = new Set();

const FACE_ANALYZE_INTERVAL_MS = 650;
const FACE_AUTO_STABLE_FRAMES = 2;
const REALTIME_FRAME_MAX_WIDTH = 640;
const REALTIME_SEND_INTERVAL_MS = 160;
const REALTIME_JPEG_QUALITY = 0.62;

const realtimeSessions = {
  check_in: { stream: null, ws: null, sendTimer: null, busy: false, stopping: false },
  check_out: { stream: null, ws: null, sendTimer: null, busy: false, stopping: false },
};

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

function todayText() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

const FACE_SCAN_STEPS = [
  { key: 'front', label: 'Nhìn thẳng vào camera' },
  { key: 'left', label: 'Quay mặt sang trái khoảng 25°' },
  { key: 'right', label: 'Quay mặt sang phải khoảng 25°' },
  { key: 'up', label: 'Ngẩng nhẹ cằm lên' },
  { key: 'down', label: 'Cúi nhẹ cằm xuống' },
];

let faceScanStepIndex = 0;
let faceScanCompleted = new Set();
let faceScanUploadComplete = false;

const pages = {
  dashboard: ['Tổng quan', 'Tổng quan hệ thống nhận diện ra/vào lab'],
  students: ['Sinh viên', 'Quản lý thông tin sinh viên'],
  'face-register': ['Đăng ký khuôn mặt', 'Thêm mẫu hoặc quét lại bộ khuôn mặt'],
  camera: ['Camera realtime', 'Nhận diện realtime bằng camera trình duyệt'],
  logs: ['Lịch sử ra/vào', 'Theo dõi check-in/check-out'],
  attendance: ['Điểm danh', 'Tổng hợp đúng giờ, đi muộn, vắng và thời gian trong lab'],
  workSchedule: ['Lịch làm việc', 'Quản lý ngày làm việc, giờ làm việc và ngày nghỉ của lab'],
  leaveRequests: ['Duyệt nghỉ phép', 'Xem và xử lý đơn nghỉ phép của sinh viên'],
  studentReports: ['Báo cáo sinh viên', 'Xem, phản hồi và duyệt báo cáo sinh viên gửi cho bạn'],
  alerts: ['Cảnh báo', 'Các sự kiện bất thường'],
  accounts: ['Tài khoản', 'Quản lý tài khoản đăng nhập theo vai trò'],
  settings: ['Cài đặt hệ thống', 'Threshold, cooldown, frame skip và chế độ camera'],
  audit: ['Nhật ký hoạt động', 'Theo dõi ai đã thực hiện hoạt động gì trong hệ thống'],
};

function roleLabel(role) {
  if (role === 'admin') return 'Admin';
  if (role === 'lab_manager') return 'Quản lý phòng lab';
  if (role === 'student') return 'Sinh viên';
  return role || 'User';
}

function isAdmin() {
  return currentUser?.role === 'admin';
}

function isLabManager() {
  return currentUser?.role === 'lab_manager';
}

function canManageSystemSettings() {
  return isAdmin();
}

function canViewAuditLogs() {
  return isAdmin();
}

function canDeleteSystemData() {
  return isAdmin();
}

function canEditUserAccount(user) {
  if (!user) return false;
  if (isLabManager()) return user.role === 'student';
  return isAdmin();
}

function canLockUserAccount(user) {
  if (!canEditUserAccount(user)) return false;
  if (Number(user.id) === Number(currentUser?.id)) return false;
  if (user.role === 'admin') return false;
  return true;
}

function canDeleteUserAccount(user) {
  if (!canEditUserAccount(user)) return false;
  if (Number(user.id) === Number(currentUser?.id)) return false;
  if (user.role === 'admin') return false;
  return true;
}

async function loadCurrentUser() {
  const data = await api('/api/auth/me');
  currentUser = data.user;
  applyCurrentUserUi();
}

function applyCurrentUserUi() {
  document.body.dataset.role = currentUser?.role || '';
  if (isLabManager()) {
    pages.dashboard = ['Tổng quan', 'Camera, điểm danh, cảnh báo và log ra/vào cần theo dõi'];
    pages.accounts = ['Tài khoản sinh viên', 'Quản lý tài khoản đăng nhập của sinh viên'];
  } else if (isAdmin()) {
    pages.dashboard = ['Tổng quan', 'Tổng quan hệ thống nhận diện ra/vào lab'];
    pages.accounts = ['Tài khoản hệ thống', 'Quản lý tài khoản đăng nhập theo vai trò'];
  }
  const pill = document.getElementById('currentUserPill');
  if (pill && currentUser) {
    pill.textContent = `${currentUser.username} · ${roleLabel(currentUser.role)}`;
    pill.className = `admin-pill role-${currentUser.role}`;
  }
  const accountsNav = document.getElementById('userManageBtn');
  if (accountsNav) {
    accountsNav.textContent = isLabManager() ? 'Tài khoản sinh viên' : 'Tài khoản';
  }
  const settingsNav = document.getElementById('settingsNavBtn');
  if (settingsNav && !canManageSystemSettings()) {
    settingsNav.hidden = true;
  }
  const workScheduleNav = document.getElementById('workScheduleNavBtn');
  if (workScheduleNav && !currentUser) {
    workScheduleNav.hidden = true;
  }
  const auditNav = document.getElementById('auditNavBtn');
  if (auditNav && !canViewAuditLogs()) {
    auditNav.hidden = true;
  }
  renderRoleHints();
}

function renderRoleHints() {
  const studentsHint = document.getElementById('studentsRoleHint');
  if (studentsHint) {
    studentsHint.textContent = isAdmin()
      ? 'Admin có thể thêm sinh viên, chỉnh giờ làm việc, đăng ký khuôn mặt và xóa sinh viên khi cần.'
      : 'Lab Manager có thể thêm sinh viên, chỉnh giờ làm việc và đăng ký khuôn mặt; thao tác xóa chỉ dành cho admin.';
  }
  renderAccountRoleHint();
}


function actionLabel(action) {
  if (action === 'check_in') return 'Check-in';
  if (action === 'check_out') return 'Check-out';
  if (action === 'unknown') return 'Unknown';
  return action || '';
}

function itemDisplayStatus(item) {
  return item.display_status || item.session_state || item.decision || 'pending';
}

function itemDisplayName(item) {
  return item.display_full_name || item.full_name || 'Unknown';
}

function itemDisplayStudentCode(item) {
  return item.display_student_code || item.student_code || 'Unknown';
}

function statusColor(status, recognized) {
  if (status === 'success') return '#22c55e';
  if (status === 'denied') return '#f97316';
  if (status === 'warning') return '#ef4444';
  if (status === 'secondary') return recognized ? '#38bdf8' : '#ef4444';
  return recognized ? '#f59e0b' : '#64748b';
}

function itemOverlayText(item) {
  const status = itemDisplayStatus(item);
  const confidence = item.confidence ?? '';
  if (status === 'success') return `${itemDisplayName(item)} ${confidence}`;
  if (status === 'denied') return item.spoof_detected ? `${itemDisplayName(item)} nghi giả mạo` : `${itemDisplayName(item)} không ghi nhận`;
  if (status === 'warning') return 'Khuôn mặt lạ';
  if (status === 'secondary') return item.recognized ? `${itemDisplayName(item)} ${confidence}` : 'Unknown';
  return `${itemDisplayName(item)} đang xác minh`;
}

function livenessStatusText(status) {
  if (status === 'live') return 'Mặt thật';
  if (status === 'fake') return 'Nghi giả mạo';
  if (status === 'uncertain') return 'Chưa đủ điều kiện kiểm tra';
  return status || '';
}

function qualityStatusText(status) {
  const labels = {
    ok: 'ảnh đạt',
    face_too_small: 'mặt quá nhỏ',
    face_near_edge: 'mặt sát mép khung',
    empty_crop: 'không cắt được mặt',
    too_dark: 'ảnh quá tối',
    too_blurry: 'ảnh bị mờ',
  };
  return labels[status] || status || '';
}

function realtimeResultHtml(item, actionText) {
  const status = itemDisplayStatus(item);
  const liveScore = item.liveness && item.liveness.real_score !== null ? `<p>Điểm mặt thật: ${escapeHtml(item.liveness.real_score)}</p>` : '';
  const liveStatus = item.liveness_status
    ? `<p>Trạng thái: ${escapeHtml(livenessStatusText(item.liveness_status))}${item.quality_status ? ` / ${escapeHtml(qualityStatusText(item.quality_status))}` : ''}</p>`
    : '';
  const confidence = escapeHtml(item.confidence ?? '');
  const name = escapeHtml(itemDisplayName(item));
  const code = escapeHtml(itemDisplayStudentCode(item));
  const note = escapeHtml(item.note || '');
  const action = escapeHtml(actionText);

  if (status === 'pending') {
    return `<p><b>Đang xác minh...</b></p><p>${name}</p><p>Độ tin cậy: ${confidence}</p>${liveStatus}${liveScore}${note ? `<p>${note}</p>` : ''}`;
  }
  if (status === 'denied') {
    if (item.note && !item.spoof_detected) {
      return `<p><b>Không ghi nhận</b></p><p>${name}</p><p>${note}</p><p>${action}: không ghi nhận thành công.</p>`;
    }
    return `<p><b>Phát hiện giả mạo</b></p>${liveStatus}${liveScore}<p>${note || 'Phiên nhận diện đã bị khóa. Đưa mặt/ảnh ra khỏi khung khoảng 2 giây để thử lại.'}</p><p>${action}: không ghi nhận thành công.</p>`;
  }
  if (status === 'warning') {
    return `<p><b>Khuôn mặt lạ</b></p><p>Độ tin cậy: ${confidence}</p>${liveStatus}${liveScore}<p>${note || 'Khuôn mặt lạ'}</p>`;
  }
  return `<p><b>${name}</b></p><p>Mã SV: ${code}</p><p>Hành động: ${action}</p><p>Độ tin cậy: ${confidence}</p>${liveStatus}${liveScore}<p>${item.logged ? 'Đã ghi log' : note || 'Đã xác minh'}</p>`;
}

function shouldShowBlockingNotice(item) {
  const note = String(item?.note || '').toLowerCase();
  return itemDisplayStatus(item) === 'denied'
    && !item.spoof_detected
    && (note.includes('đã check-in') || note.includes('chưa check-in') || note.includes('không thể check-out'));
}

function maybeShowRealtimeNotice(action, item) {
  if (!shouldShowBlockingNotice(item)) return;
  const key = `${action}:${item.student_id || item.student_code || 'unknown'}:${item.note}`;
  if (shownRealtimeNotices.has(key)) return;
  shownRealtimeNotices.add(key);
  window.alert(item.note);
  setTimeout(() => shownRealtimeNotices.delete(key), 10000);
}

function realtimeFrameSize(video) {
  const scale = Math.min(1, REALTIME_FRAME_MAX_WIDTH / video.videoWidth);
  return {
    width: Math.round(video.videoWidth * scale),
    height: Math.round(video.videoHeight * scale),
  };
}

function isSpoofDenied(log) {
  const note = String(log.note || '').toLowerCase();
  return log.result === 'denied' && (note.includes('giả mạo') || note.includes('gia mao') || note.includes('spoof'));
}

function resultBadge(result, log = null) {
  let cls = result === 'success' ? 'badge-success' : 'badge-neutral';
  let text = result === 'success' ? 'Thành công' : result;
  if (result === 'denied') {
    const spoof = log && isSpoofDenied(log);
    cls = spoof ? 'badge-spoof' : 'badge-denied';
    text = spoof ? 'Giả mạo' : 'Không ghi nhận';
  } else if (result === 'warning') {
    cls = 'badge-warning';
    text = 'Cảnh báo';
  } else if (result === 'success' && log?.action === 'check_out') {
    cls = 'badge-checkout';
  }
  return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
}

function attendanceStatusLabel(status) {
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
  return labels[status] || status || '';
}

function attendanceStatusClass(status) {
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

function attendanceStatusBadge(status) {
  return `<span class="attendance-status ${attendanceStatusClass(status)}">${escapeHtml(attendanceStatusLabel(status))}</span>`;
}

function attendancePresenceLabel(status) {
  if (status === 'in_lab') return 'Trong lab';
  if (status === 'out_of_lab') return 'Ngoài lab';
  return '-';
}

function attendancePresenceClass(status) {
  if (status === 'in_lab') return 'presence-in';
  if (status === 'out_of_lab') return 'presence-out';
  return 'presence-none';
}

function attendancePresenceBadge(status) {
  return `<span class="presence-status ${attendancePresenceClass(status)}">${escapeHtml(attendancePresenceLabel(status))}</span>`;
}

function attendanceDateText(value) {
  if (!value) return '--/--/----';
  const [year, month, day] = String(value).split('-');
  return day && month && year ? `${day}/${month}/${year}` : escapeHtml(value);
}

function attendanceTimeText(value) {
  if (!value) return '--:--';
  return logTimeParts(value).time;
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

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  })[char]);
}

function logTimeParts(createdAt) {
  const parsed = new Date(createdAt);
  if (!Number.isNaN(parsed.getTime())) {
    return {
      time: parsed.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
      date: parsed.toLocaleDateString('vi-VN'),
    };
  }

  const [date = '', time = ''] = String(createdAt || '').split('T');
  return {
    time: time.slice(0, 5) || '--:--',
    date: date.split('-').reverse().join('/') || '--/--/----',
  };
}

function logTone(log) {
  if (log.result === 'success') return log.action === 'check_out' ? 'tone-checkout' : 'tone-success';
  if (log.result === 'denied') return isSpoofDenied(log) ? 'tone-spoof' : 'tone-denied';
  if (log.result === 'warning') return 'tone-warning';
  return 'tone-neutral';
}

function logTitle(log) {
  if (log.result === 'success' && log.action === 'check_in') return 'Đã ghi nhận vào';
  if (log.result === 'success' && log.action === 'check_out') return 'Đã ghi nhận ra';
  if (log.result === 'denied') return isSpoofDenied(log) ? 'Nghi ngờ giả mạo' : 'Không ghi nhận';
  if (log.result === 'warning') return 'Khuôn mặt lạ';
  return actionLabel(log.action) || 'Sự kiện';
}

function prettyLogNote(note) {
  const visibleNote = String(note || '').split(' | Frames:', 1)[0].trim();
  const normalized = visibleNote.toLowerCase();
  const replacements = {
    'nghi ngo gia mao khuon mat': 'Nghi ngờ giả mạo khuôn mặt',
    'unknown face': 'Khuôn mặt lạ',
    'realtime camera': 'Camera realtime',
    'sinh vien da check-in, chua check-out.': 'Sinh viên đã check-in, chưa check-out.',
    'sinh vien chua check-in, khong the check-out.': 'Sinh viên chưa check-in, không thể check-out.',
  };
  return replacements[normalized] || visibleNote || '';
}

function alertTypeLabel(type) {
  const labels = {
    unknown_face: 'Khuôn mặt lạ',
    spoof_detected: 'Nghi giả mạo',
    missing_checkout: 'Thiếu check-out',
  };
  return labels[type] || type || 'Cảnh báo';
}

function alertTypeClass(type) {
  if (type === 'spoof_detected') return 'alert-type-spoof';
  if (type === 'unknown_face') return 'alert-type-unknown';
  if (type === 'missing_checkout') return 'alert-type-missing-checkout';
  return 'alert-type-default';
}

function alertStatusLabel(status) {
  const labels = {
    new: 'Chưa xử lí',
    resolved: 'Đã xử lí',
    ignored: 'Bỏ qua',
  };
  return labels[status] || status || '';
}

function alertStatusClass(status) {
  if (status === 'resolved') return 'alert-status-resolved';
  if (status === 'ignored') return 'alert-status-ignored';
  return 'alert-status-new';
}

function prettyAlertMessage(alert) {
  const raw = String(alert.message || '').trim();
  const [visiblePart, framePart = ''] = raw.split(' | Frames:', 2);
  const normalized = visiblePart.toLowerCase();
  const replacements = {
    'phat hien khuon mat la tu camera realtime.': 'Phát hiện khuôn mặt lạ từ camera realtime.',
    'nghi ngo gia mao khuon mat': 'Nghi ngờ giả mạo khuôn mặt.',
    'dua mat lai gan camera hon.': 'Khuôn mặt quá nhỏ. Vui lòng đưa mặt lại gần camera hơn.',
    'sinh vien da check-in nhung chua check-out.': 'Sinh viên đã check-in nhưng chưa check-out.',
  };

  let message = replacements[normalized] || visiblePart || alertTypeLabel(alert.type);
  if (framePart.includes('quality=face_near_edge')) {
    message += ' Khuôn mặt ở sát mép khung hình trong nhiều frame.';
  } else if (framePart.includes('quality=face_too_small')) {
    message += ' Khuôn mặt quá nhỏ trong nhiều frame.';
  } else if (framePart.includes('quality=too_dark')) {
    message += ' Ảnh quá tối trong nhiều frame.';
  } else if (framePart.includes('quality=too_blurry')) {
    message += ' Ảnh bị mờ trong nhiều frame.';
  } else if (framePart.includes('vote=fake')) {
    message += ' Model báo giả ở nhiều frame liên tiếp.';
  }
  return message;
}

function alertTimeCell(createdAt, eventDate = null) {
  const parts = logTimeParts(createdAt);
  const dateText = eventDate ? attendanceDateText(eventDate) : parts.date;
  return `<div class="log-time"><strong>${escapeHtml(parts.time)}</strong><span>${escapeHtml(dateText)}</span></div>`;
}

function protectedFaceUrl(face) {
  return face?.id ? `/api/files/face/${encodeURIComponent(face.id)}` : '';
}

function protectedAccessLogEvidenceUrl(log) {
  const hasEvidence = log?.evidence_image_path || log?.evidence_url || log?.image_path || log?.evidence;
  return hasEvidence && log?.id ? `/api/files/evidence/access-log/${encodeURIComponent(log.id)}` : '';
}

function protectedAlertEvidenceUrl(alert) {
  return alert?.evidence_image_path && alert?.id ? `/api/files/evidence/alert/${encodeURIComponent(alert.id)}` : '';
}

function evidencePreview(log) {
  const src = protectedAccessLogEvidenceUrl(log);
  if (src) {
    return `<img class="log-evidence-img" src="${escapeHtml(src)}" alt="Ảnh bằng chứng" loading="lazy" />`;
  }
  return '<div class="log-evidence-empty"><span>Chưa có ảnh</span></div>';
}

function renderLogEvidenceActions(log) {
  const deleteBtn = canDeleteSystemData() ? `<button class="icon-btn danger" title="Xóa lịch sử" onclick="deleteAccessLog(${log.id})">X</button>` : '';
  return `<div class="log-evidence-actions">
    ${evidencePreview(log)}
    ${deleteBtn}
  </div>`;
}

function renderLogTimelineItem(log) {
  const time = logTimeParts(log.created_at);
  const tone = logTone(log);
  const confidence = log.confidence ?? '';
  const note = prettyLogNote(log.note);

  return `<article class="log-item ${tone}">
    <div class="log-time">
      <strong>${escapeHtml(time.time)}</strong>
      <span>${escapeHtml(time.date)}</span>
    </div>
    <div class="log-node"></div>
    <div class="log-panel">
      <div class="log-main">
        <div class="log-title">${escapeHtml(logTitle(log))}</div>
        <div class="log-name">${escapeHtml(log.full_name || 'Unknown')}</div>
        <div class="log-meta">
          <span>${escapeHtml(log.student_code || 'Unknown')}</span>
          <span>${escapeHtml(actionLabel(log.action))}</span>
          ${confidence !== '' ? `<span>Độ tin cậy: ${escapeHtml(confidence)}</span>` : ''}
        </div>
        ${note ? `<div class="log-note">${escapeHtml(note)}</div>` : ''}
      </div>
      <div class="log-evidence">${renderLogEvidenceActions(log)}</div>
    </div>
  </article>`;
}

function getFaceScanSteps() {
  return FACE_SCAN_STEPS;
}

function renderFaceScanGuide() {
  const currentEl = document.getElementById('scanGuideCurrent');
  const stepsEl = document.getElementById('scanGuideSteps');
  const captureBtn = document.getElementById('captureStepBtn');
  const resetBtn = document.getElementById('resetFaceScanBtn');
  const hintEl = document.getElementById('faceModeHint');
  if (!currentEl || !stepsEl || !captureBtn) return;

  document.getElementById('faceModeAppendBtn')?.classList.toggle('active', faceRegisterMode === 'append');
  document.getElementById('faceModeReplaceBtn')?.classList.toggle('active', faceRegisterMode === 'replace');

  if (faceRegisterMode === 'append') {
    if (hintEl) {
      hintEl.textContent = 'Dùng chế độ này để bổ sung ảnh mới vào bộ mẫu hiện có. Nếu đã đủ 10/10, hệ thống tự giữ 10 mẫu mới nhất.';
    }
    currentEl.textContent = 'Thêm mẫu bằng camera';
    stepsEl.innerHTML = '<span class="scan-step active">Giữ mặt rõ, đủ sáng và nằm giữa khung hình</span><span class="scan-step">Ảnh mới sẽ được thêm vào bộ mẫu hiện có</span>';
    captureBtn.disabled = faceScanBusy;
    captureBtn.textContent = faceScanBusy ? 'Đang xử lý...' : 'Chụp thêm mẫu';
    if (resetBtn) resetBtn.hidden = true;
    return;
  }

  if (hintEl) {
    hintEl.textContent = 'Chế độ này thay thế toàn bộ bộ mẫu hiện tại bằng 5 tư thế mới.';
  }
  if (resetBtn) resetBtn.hidden = false;

  const steps = getFaceScanSteps();
  if (faceScanStepIndex >= steps.length) faceScanStepIndex = 0;
  const done = faceScanCompleted.size;
  const total = steps.length;
  const allDone = done >= total;

  if (allDone) {
    currentEl.textContent = faceScanUploadComplete
      ? `Hoàn tất ${total}/${total} tư thế.`
      : `Đã chụp đủ ${total}/${total} tư thế.`;
  } else {
    const step = steps[faceScanStepIndex];
    currentEl.textContent = `Bước ${faceScanStepIndex + 1}/${total}: ${step.label}`;
  }

  stepsEl.innerHTML = steps
    .map((step, idx) => {
      const doneClass = faceScanCompleted.has(step.key) ? 'done' : '';
      const activeClass = !allDone && idx === faceScanStepIndex ? 'active' : '';
      return `<span class="scan-step ${doneClass} ${activeClass}">${idx + 1}. ${step.label}</span>`;
    })
    .join('');

  captureBtn.disabled = faceScanBusy || (allDone && faceScanUploadComplete);
  captureBtn.textContent = faceScanBusy
    ? 'Đang xử lý...'
    : (allDone ? (faceScanUploadComplete ? 'Đã hoàn tất' : 'Gửi lại 5 ảnh') : 'Chụp thủ công bước này');
}

function setFaceRegisterMode(mode) {
  faceRegisterMode = mode === 'replace' ? 'replace' : 'append';
  if (faceRegisterMode === 'append') {
    stopFacePoseAnalyzer();
  } else if (faceRegisterStream) {
    startFacePoseAnalyzer();
  }
  renderFaceScanGuide();
  const msg = document.getElementById('faceRegisterMessage');
  if (msg) {
    msg.textContent = faceRegisterMode === 'append'
      ? 'Chế độ thêm mẫu: chụp 1 ảnh mới, không thay thế toàn bộ bộ khuôn mặt.'
      : 'Chế độ quét lại: hoàn tất 5 tư thế để thay thế bộ khuôn mặt hiện tại.';
  }
}

function resetFaceScanProgress(showMessage = true, restartAnalyzer = true) {
  faceScanStepIndex = 0;
  faceScanCompleted = new Set();
  faceScanCaptures = new Map();
  faceScanUploadComplete = false;
  facePoseStableCount = 0;
  faceLastPose = null;
  renderFaceScanGuide();
  if (restartAnalyzer && faceRegisterStream && faceRegisterMode === 'replace') startFacePoseAnalyzer();
  if (showMessage) {
    const msg = document.getElementById('faceRegisterMessage');
    if (msg) msg.textContent = 'Đã làm mới tiến trình quét.';
  }
}

function showPage(id) {
  if (!pages[id]) {
    id = 'dashboard';
  }
  if (id === 'settings' && !canManageSystemSettings()) {
    alert('Chỉ admin được vào phần cài đặt hệ thống.');
    id = 'dashboard';
  }
  if (id === 'workSchedule' && !currentUser) {
    id = 'dashboard';
  }
  if (id === 'audit' && !canViewAuditLogs()) {
    alert('Chỉ admin được xem audit logs.');
    id = 'dashboard';
  }
  if (id !== 'face-register') stopFaceRegisterCamera(false);
  document.querySelectorAll('.page').forEach((p) => p.classList.remove('active-page'));
  document.getElementById(id).classList.add('active-page');
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.page === id));
  document.getElementById('pageTitle').textContent = pages[id][0];
  document.getElementById('pageSubtitle').textContent = pages[id][1];
  if (id === 'dashboard') loadDashboard();
  if (id === 'students') loadStudents();
  if (id === 'face-register') {
    loadStudents();
    renderFaceScanGuide();
  }
  if (id === 'logs') loadLogs();
  if (id === 'attendance') loadAttendanceRecords();
  if (id === 'workSchedule') loadWorkSchedulePage();
  if (id === 'leaveRequests') loadLeaveRequests();
  if (id === 'studentReports') loadStaffReports();
  if (id === 'alerts') loadAlerts();
  if (id === 'accounts') loadAccountsPage();
  if (id === 'settings') loadSettings();
  if (id === 'audit') loadAuditLogs();
}

async function api(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = {
    'Content-Type': 'application/json',
    ...(method === 'GET' ? {} : csrfHeaders()),
    ...(options.headers || {}),
  };
  const res = await fetch(url, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...options,
    headers,
  });
  if (res.status === 401) {
    window.location.href = '/login';
    return;
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Có lỗi xảy ra');
  }
  return res.json();
}

function apiErrorMessage(detail) {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    if (detail.duplicate_warnings && detail.duplicate_warnings.length) {
      return `${detail.message || 'Khuôn mặt bị trùng.'} Trùng với: ${duplicateWarningsText(detail.duplicate_warnings)}`;
    }
    return detail.message || 'Có lỗi xảy ra';
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== 'body').join('.') : '';
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join(' | ');
  }
  return detail || 'Có lỗi xảy ra';
}

document.querySelectorAll('.nav-item[data-page]').forEach((btn) => btn.addEventListener('click', () => showPage(btn.dataset.page)));
document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: csrfHeaders() });
  window.location.replace('/login');
});
document.getElementById('studentSearch').addEventListener('input', () => loadStudents(document.getElementById('studentSearch').value));
document.addEventListener('click', () => {
  document.querySelectorAll('.status-menu').forEach((menu) => menu.classList.add('hidden'));
});
