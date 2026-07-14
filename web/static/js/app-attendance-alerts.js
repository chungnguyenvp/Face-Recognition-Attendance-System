function todayDateValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function setInputValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value;
}

function getInputValue(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function appendFilter(params, id, key) {
  const value = getInputValue(id);
  if (value) params.set(key, value);
}

function initListFilters() {
  const today = todayDateValue();
  ['logDateFrom', 'logDateTo', 'attendanceDateFrom', 'attendanceDateTo', 'alertDateFrom', 'alertDateTo'].forEach((id) => {
    if (!getInputValue(id)) setInputValue(id, today);
  });
}

function resetLogFilters() {
  const today = todayDateValue();
  setInputValue('logSearch', '');
  setInputValue('logActionFilter', '');
  setInputValue('logResultFilter', '');
  setInputValue('logDateFrom', today);
  setInputValue('logDateTo', today);
  loadLogs();
}

function resetAlertFilters() {
  const today = todayDateValue();
  setInputValue('alertSearch', '');
  setInputValue('alertTypeFilter', '');
  setInputValue('alertStatusFilter', '');
  setInputValue('alertDateFrom', today);
  setInputValue('alertDateTo', today);
  loadAlerts();
}

function resetAttendanceFilters() {
  const today = todayDateValue();
  setInputValue('attendanceSearch', '');
  setInputValue('attendanceClassFilter', '');
  setInputValue('attendanceStatusFilter', '');
  setInputValue('attendanceDateFrom', today);
  setInputValue('attendanceDateTo', today);
  loadAttendanceRecords();
}

async function loadLogs() {
  const params = new URLSearchParams({ limit: '200' });
  appendFilter(params, 'logDateFrom', 'date_from');
  appendFilter(params, 'logDateTo', 'date_to');
  appendFilter(params, 'logActionFilter', 'action');
  appendFilter(params, 'logResultFilter', 'result');
  appendFilter(params, 'logSearch', 'q');
  const data = await api(`/api/access-logs?${params.toString()}`);
  document.getElementById('logsTimeline').innerHTML =
    data.items.map(renderLogTimelineItem).join('') || '<div class="empty-state">Chưa có dữ liệu lịch sử.</div>';
  const count = document.getElementById('logsCount');
  if (count) count.textContent = `Tìm thấy ${data.count ?? data.items.length} bản ghi`;
}

async function deleteAccessLog(logId) {
  if (!canDeleteSystemData()) return;
  if (!confirm('Bạn có chắc muốn xóa bản ghi lịch sử này không? Hành động này sẽ xóa khỏi dữ liệu và không thể hoàn tác.')) return;
  await api(`/api/access-logs/${logId}`, { method: 'DELETE' });
  await loadLogs();
  await loadDashboard();
  if (document.getElementById('attendance').classList.contains('active-page')) await loadAttendanceRecords();
}

function renderAttendanceRow(record) {
  return `<tr>
    <td>${attendanceDateText(record.attendance_date)}</td>
    <td><strong>${escapeHtml(record.full_name || 'Unknown')}</strong><span class="table-subtext">${escapeHtml(record.student_code || '')}</span></td>
    <td>${attendanceTimeText(record.first_check_in_at)}</td>
    <td>${attendanceTimeText(record.last_check_out_at)}</td>
    <td>${attendanceStatusBadge(record.status)}</td>
    <td>${attendancePresenceBadge(record.presence_status)}</td>
    <td>${minutesText(record.late_minutes)}</td>
    <td>${minutesText(record.early_leave_minutes)}</td>
    <td>${totalMinutesText(record.total_minutes)}</td>
    <td>${escapeHtml(record.note || '')}</td>
    <td><button class="secondary detail-btn" onclick="openAttendanceDetail(${record.id})">Chi tiết</button></td>
  </tr>`;
}

async function loadAttendanceRecords() {
  const params = new URLSearchParams({ limit: '500' });
  appendFilter(params, 'attendanceDateFrom', 'date_from');
  appendFilter(params, 'attendanceDateTo', 'date_to');
  appendFilter(params, 'attendanceStatusFilter', 'status');
  appendFilter(params, 'attendanceSearch', 'q');
  appendFilter(params, 'attendanceClassFilter', 'class_name');
  const data = await api(`/api/attendance-records?${params.toString()}`);
  document.getElementById('attendanceTable').innerHTML =
    data.items.map(renderAttendanceRow).join('') ||
    '<tr><td colspan="11">Chưa có dữ liệu điểm danh.</td></tr>';
  const count = document.getElementById('attendanceCount');
  if (count) count.textContent = `Tìm thấy ${data.count ?? data.items.length} bản ghi`;
}

function attendanceActionText(action) {
  if (action === 'check_in') return 'Vào';
  if (action === 'check_out') return 'Ra';
  return actionLabel(action) || '-';
}

function detailDurationText(minutes) {
  return totalMinutesText(minutes).replace('-', '0p');
}

function renderAttendanceDetailList(items, emptyText, renderer) {
  if (!items || !items.length) return `<div class="detail-empty">${escapeHtml(emptyText)}</div>`;
  return `<div class="detail-list">${items.map(renderer).join('')}</div>`;
}

function isMissingCheckoutResolvable(record) {
  return record.status === 'missing_checkout'
    || ['auto_work_end', 'work_end', 'manual_time', 'keep_zero'].includes(record.missing_checkout_resolution);
}

function resolutionText(record) {
  const labels = {
    auto_work_end: 'Đã tự chốt theo giờ kết thúc ca',
    work_end: 'Admin đã chốt theo giờ kết thúc ca',
    manual_time: 'Admin đã nhập giờ ra',
    keep_zero: 'Đang giữ thiếu check-out, tính 0h',
  };
  return labels[record.missing_checkout_resolution] || 'Chưa xử lý';
}

function timeInputValue(value) {
  if (!value) return '';
  const time = attendanceTimeText(value);
  return time === '--:--' ? '' : time;
}

function renderMissingCheckoutActions(record) {
  if (!isMissingCheckoutResolvable(record)) return '';
  return `<div class="missing-checkout-panel">
    <h4>Xử lý thiếu check-out</h4>
    <div class="resolution-current">${escapeHtml(resolutionText(record))}</div>
    <label>Lý do xử lý</label>
    <textarea id="missingCheckoutReason" rows="3" placeholder="Ví dụ: Sinh viên quên check-out, admin xác minh lại.">${escapeHtml(record.resolution_reason || '')}</textarea>
    <div class="missing-checkout-custom">
      <label>Giờ ra thực tế</label>
      <input id="missingCheckoutTime" type="time" value="${escapeHtml(timeInputValue(record.resolution_checkout_at))}" />
    </div>
    <div class="missing-checkout-actions">
      <button onclick="resolveMissingCheckout(${record.id}, 'work_end')">Chốt theo giờ kết thúc ca</button>
      <button class="secondary" onclick="resolveMissingCheckout(${record.id}, 'manual_time')">Nhập giờ ra</button>
      <button class="secondary danger-lite" onclick="resolveMissingCheckout(${record.id}, 'keep_zero')">Giữ thiếu check-out, tính 0h</button>
    </div>
  </div>`;
}

function renderAttendanceDetail(detail) {
  const record = detail.record || {};
  const summary = detail.summary || {};
  const logs = summary.logs || [];
  const sessions = summary.sessions || [];
  const outsidePeriods = summary.outside_periods || [];
  const currentOutSince = summary.current_out_since_at;
  const currentOutItem = currentOutSince
    ? [{ start_at: currentOutSince, end_at: null, minutes: null, current: true }]
    : [];
  const outsideItems = outsidePeriods.concat(currentOutItem);

  return `<div class="attendance-detail">
    <div class="detail-person">
      <strong>${escapeHtml(record.full_name || 'Unknown')}</strong>
      <span>${escapeHtml(record.student_code || '')} · ${attendanceDateText(record.attendance_date)}</span>
    </div>
    <div class="detail-summary-grid">
      <div><span>Trạng thái</span>${attendanceStatusBadge(record.status)}</div>
      <div><span>Hiện diện</span>${attendancePresenceBadge(summary.presence_status)}</div>
      <div><span>Tổng trong lab</span><strong>${totalMinutesText(record.total_minutes)}</strong></div>
      <div><span>Tổng ra ngoài</span><strong>${detailDurationText(summary.outside_minutes)}</strong></div>
    </div>
    <div class="detail-section">
      <h4>Log ra/vào</h4>
      ${renderAttendanceDetailList(logs, 'Chưa có log ra/vào.', (item) => `
        <div class="detail-row">
          <strong>${attendanceTimeText(item.created_at)}</strong>
          <span>${escapeHtml(attendanceActionText(item.action))}${item.note ? `<small>${escapeHtml(item.note)}</small>` : ''}</span>
        </div>`)}
    </div>
    <div class="detail-section">
      <h4>Phiên trong lab</h4>
      ${renderAttendanceDetailList(sessions, 'Chưa có phiên check-in/check-out hoàn chỉnh.', (item) => `
        <div class="detail-row">
          <strong>${attendanceTimeText(item.start_at)} - ${attendanceTimeText(item.end_at)}</strong>
          <span>${detailDurationText(item.minutes)}</span>
        </div>`)}
    </div>
    <div class="detail-section">
      <h4>Ra ngoài</h4>
      ${renderAttendanceDetailList(outsideItems, 'Không có khoảng ra ngoài giữa ca.', (item) => `
        <div class="detail-row">
          <strong>${attendanceTimeText(item.start_at)} - ${item.end_at ? attendanceTimeText(item.end_at) : '...'}</strong>
          <span>${item.current ? 'Đã ra ngoài từ lúc này' : detailDurationText(item.minutes)}</span>
        </div>`)}
    </div>
    ${renderMissingCheckoutActions(record)}
    ${record.note ? `<div class="detail-note">${escapeHtml(record.note)}</div>` : ''}
  </div>`;
}

async function openAttendanceDetail(recordId) {
  const modal = document.getElementById('attendanceDetailModal');
  const body = document.getElementById('attendanceDetailBody');
  const message = document.getElementById('attendanceDetailMessage');
  if (!modal || !body) return;
  body.innerHTML = '<div class="detail-empty">Đang tải chi tiết...</div>';
  if (message) message.textContent = '';
  modal.classList.remove('hidden');
  try {
    const detail = await api(`/api/attendance-records/${recordId}/details`);
    body.innerHTML = renderAttendanceDetail(detail);
  } catch (e) {
    body.innerHTML = '';
    if (message) message.textContent = e.message || 'Không tải được chi tiết điểm danh.';
  }
}

function closeAttendanceDetailModal() {
  const modal = document.getElementById('attendanceDetailModal');
  if (modal) modal.classList.add('hidden');
}

async function resolveMissingCheckout(recordId, resolutionType) {
  const reasonInput = document.getElementById('missingCheckoutReason');
  const timeInput = document.getElementById('missingCheckoutTime');
  const message = document.getElementById('attendanceDetailMessage');
  const reason = (reasonInput?.value || '').trim();
  if (!reason) {
    if (message) message.textContent = 'Vui lòng nhập lý do xử lý thiếu check-out.';
    return;
  }
  if (resolutionType === 'manual_time' && !timeInput?.value) {
    if (message) message.textContent = 'Vui lòng nhập giờ ra thực tế.';
    return;
  }
  if (resolutionType === 'keep_zero' && !confirm('Giữ thiếu check-out và tính tổng giờ ngày này là 0h?')) return;
  if (message) message.textContent = '';
  const payload = {
    resolution_type: resolutionType,
    reason,
  };
  if (resolutionType === 'manual_time') payload.checkout_time = timeInput.value;
  try {
    await api(`/api/attendance-records/${recordId}/resolve-missing-checkout`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    await loadAttendanceRecords();
    await loadDashboard();
    await openAttendanceDetail(recordId);
  } catch (e) {
    if (message) message.textContent = e.message || 'Không xử lý được thiếu check-out.';
  }
}

function renderAlertActions(alert) {
  const imagePath = protectedAlertEvidenceUrl(alert);
  const imageArg = escapeHtml(JSON.stringify(imagePath));
  return `<div class="alert-actions">
    <button class="icon-btn" title="Đổi trạng thái" onclick="toggleAlertStatusMenu(event, ${alert.id})">&#8942;</button>
    <button class="icon-btn" title="Xem ảnh" onclick="openEvidenceModal(${imageArg})">&#9635;</button>
    ${canDeleteSystemData() ? `<button class="icon-btn danger" title="Xóa cảnh báo" onclick="deleteAlert(${alert.id})">X</button>` : ''}
    <div id="alertStatusMenu-${alert.id}" class="status-menu hidden">
      <button onclick="updateAlertStatus(${alert.id}, 'new')">Chưa xử lí</button>
      <button onclick="updateAlertStatus(${alert.id}, 'resolved')">Đã xử lí</button>
      <button onclick="updateAlertStatus(${alert.id}, 'ignored')">Bỏ qua</button>
    </div>
  </div>`;
}

function renderAlertRow(alert) {
  return `<tr id="alertRow-${alert.id}">
    <td>${alertTimeCell(alert.created_at, alert.event_date)}</td>
    <td><span class="alert-type ${alertTypeClass(alert.type)}">${escapeHtml(alertTypeLabel(alert.type))}</span></td>
    <td>${escapeHtml(prettyAlertMessage(alert))}</td>
    <td><span id="alertStatusBadge-${alert.id}" class="alert-status-badge ${alertStatusClass(alert.status)}">${escapeHtml(alertStatusLabel(alert.status))}</span></td>
    <td>${renderAlertActions(alert)}</td>
  </tr>`;
}

async function loadAlerts() {
  const params = new URLSearchParams({ limit: '200' });
  appendFilter(params, 'alertDateFrom', 'date_from');
  appendFilter(params, 'alertDateTo', 'date_to');
  appendFilter(params, 'alertTypeFilter', 'type');
  appendFilter(params, 'alertStatusFilter', 'status');
  appendFilter(params, 'alertSearch', 'q');
  const data = await api(`/api/alerts?${params.toString()}`);
  document.getElementById('alertsTable').innerHTML =
    data.items.map(renderAlertRow).join('') ||
    '<tr><td colspan="5">Chưa có cảnh báo</td></tr>';
  const count = document.getElementById('alertsCount');
  if (count) count.textContent = `Tìm thấy ${data.count ?? data.items.length} cảnh báo`;
}

function setAlertsMessage(text) {
  const msg = document.getElementById('alertsMessage');
  if (msg) msg.textContent = text || '';
}

async function scanMissingCheckouts() {
  const data = await api('/api/alerts/scan-missing-checkouts', { method: 'POST' });
  setAlertsMessage(data.created ? `Đã tạo ${data.created} cảnh báo thiếu check-out.` : 'Không có ca thiếu check-out mới.');
  await loadAlerts();
  await loadDashboard();
}

function toggleAlertStatusMenu(event, alertId) {
  event?.stopPropagation();
  document.querySelectorAll('.status-menu').forEach((menu) => {
    if (menu.id !== `alertStatusMenu-${alertId}`) menu.classList.add('hidden');
  });
  const menu = document.getElementById(`alertStatusMenu-${alertId}`);
  if (!menu) return;
  const willOpen = menu.classList.contains('hidden');
  menu.classList.toggle('hidden');
  if (!willOpen) return;

  const button = event?.currentTarget;
  if (!button) return;
  const rect = button.getBoundingClientRect();
  const menuWidth = 150;
  const menuHeight = 128;
  const gap = 8;
  const left = Math.min(Math.max(12, rect.right - menuWidth), window.innerWidth - menuWidth - 12);
  let top = rect.bottom + gap;
  if (top + menuHeight > window.innerHeight - 12) {
    top = Math.max(12, rect.top - menuHeight - gap);
  }
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

async function updateAlertStatus(alertId, status) {
  const data = await api(`/api/alerts/${alertId}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  });
  const nextStatus = data.item?.status || status;
  const badge = document.getElementById(`alertStatusBadge-${alertId}`);
  if (badge) {
    badge.className = `alert-status-badge ${alertStatusClass(nextStatus)}`;
    badge.textContent = alertStatusLabel(nextStatus);
  }
  const menu = document.getElementById(`alertStatusMenu-${alertId}`);
  if (menu) menu.classList.add('hidden');
  setInputValue('alertStatusFilter', '');
  setAlertsMessage('Đã cập nhật trạng thái cảnh báo.');
  await loadDashboard();
}

function openEvidenceModal(src, title = 'Ảnh bằng chứng') {
  if (!src) {
    setAlertsMessage('Cảnh báo này chưa có ảnh bằng chứng.');
    return;
  }
  const modal = document.getElementById('evidenceModal');
  const titleEl = document.getElementById('evidenceModalTitle');
  const image = document.getElementById('evidenceModalImage');
  const msg = document.getElementById('evidenceModalMessage');
  if (!modal || !image) return;
  if (titleEl) titleEl.textContent = title;
  image.src = src;
  if (msg) msg.textContent = '';
  modal.classList.add('evidence-modal-active');
  modal.classList.remove('hidden');
}

function closeEvidenceModal() {
  const modal = document.getElementById('evidenceModal');
  const titleEl = document.getElementById('evidenceModalTitle');
  const image = document.getElementById('evidenceModalImage');
  const shouldReopenFaceGallery = reopenFaceGalleryAfterEvidence;
  reopenFaceGalleryAfterEvidence = false;
  if (image) image.removeAttribute('src');
  if (titleEl) titleEl.textContent = 'Ảnh bằng chứng';
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('evidence-modal-active');
  }
  if (shouldReopenFaceGallery) openFaceGallery();
}

async function deleteAlert(alertId) {
  if (!canDeleteSystemData()) return;
  if (!confirm('Bạn có chắc muốn xóa cảnh báo này không? Hành động này sẽ xóa khỏi dữ liệu và không thể hoàn tác.')) return;
  await api(`/api/alerts/${alertId}`, { method: 'DELETE' });
  setAlertsMessage('Đã xóa cảnh báo.');
  await loadAlerts();
  await loadDashboard();
}

const AUDIT_ACTIONS = {
  'auth.login_success': ['Đăng nhập thành công', 'success'],
  'auth.login_failed': ['Đăng nhập thất bại', 'danger'],
  'auth.login_rate_limited': ['Tạm khóa đăng nhập', 'danger'],
  'auth.login_blocked': ['Tài khoản bị khóa', 'danger'],
  'auth.logout': ['Đăng xuất', 'neutral'],
  'users.create': ['Tạo tài khoản', 'success'],
  'users.update': ['Cập nhật tài khoản', 'warning'],
  'users.delete': ['Xóa tài khoản', 'danger'],
  'students.create': ['Thêm sinh viên', 'success'],
  'students.update': ['Cập nhật sinh viên', 'warning'],
  'students.delete': ['Xóa sinh viên', 'danger'],
  'students.work_time.update': ['Cập nhật giờ làm việc', 'warning'],
  'students.work_time.reset': ['Đặt lại giờ làm việc', 'warning'],
  'faces.upload': ['Thêm ảnh khuôn mặt', 'success'],
  'faces.scan_replace': ['Thay bộ ảnh khuôn mặt', 'warning'],
  'faces.delete': ['Xóa ảnh khuôn mặt', 'danger'],
  'face_requests.submit': ['Gửi yêu cầu FaceID', 'neutral'],
  'face_requests.approve': ['Duyệt yêu cầu FaceID', 'success'],
  'face_requests.reject': ['Từ chối yêu cầu FaceID', 'danger'],
  'face_requests.cancel': ['Hủy yêu cầu FaceID', 'warning'],
  'settings.update': ['Cập nhật cấu hình', 'warning'],
  'work_schedule.settings.update': ['Cập nhật lịch làm việc', 'warning'],
  'work_schedule.exception.create': ['Thêm ngày nghỉ đặc biệt', 'success'],
  'work_schedule.exception.update': ['Cập nhật ngày nghỉ đặc biệt', 'warning'],
  'work_schedule.exception.delete': ['Xóa ngày nghỉ đặc biệt', 'danger'],
  'alerts.scan_missing_checkouts': ['Quét thiếu check-out', 'neutral'],
  'alerts.status.update': ['Cập nhật cảnh báo', 'warning'],
  'alerts.delete': ['Xóa cảnh báo', 'danger'],
  'access_logs.delete': ['Xóa log ra vào', 'danger'],
  'attendance.missing_checkout.resolve': ['Xử lý thiếu check-out', 'warning'],
  'attendance.recalculate': ['Tính lại chấm công', 'neutral'],
  'leave_requests.create': ['Gửi đơn nghỉ phép', 'neutral'],
  'leave_requests.approved': ['Duyệt đơn nghỉ phép', 'success'],
  'leave_requests.rejected': ['Từ chối đơn nghỉ phép', 'danger'],
  'leave_requests.cancel': ['Hủy đơn nghỉ phép', 'warning'],
  'leave_requests.revoke': ['Thu hồi đơn nghỉ phép', 'danger'],
};

const AUDIT_FIELD_LABELS = {
  status: 'Trạng thái',
  student_id: 'Sinh viên',
  student_code: 'Mã sinh viên',
  full_name: 'Họ tên',
  class_name: 'Lớp',
  work_start_time: 'Giờ bắt đầu',
  work_end_time: 'Giờ kết thúc',
  face_threshold: 'Ngưỡng nhận diện',
  check_cooldown_seconds: 'Thời gian chống ghi trùng',
  frame_skip: 'Số khung hình bỏ qua',
  liveness_enabled: 'Kiểm tra giả mạo',
  liveness_threshold: 'Ngưỡng chống giả mạo',
  liveness_real_class_index: 'Lớp ảnh thật',
  liveness_crop_scale: 'Tỷ lệ vùng khuôn mặt',
  liveness_min_face_size: 'Kích thước khuôn mặt tối thiểu',
  liveness_min_brightness: 'Độ sáng tối thiểu',
  liveness_min_blur: 'Độ nét tối thiểu',
  missing_checkout_cutoff_time: 'Giờ chốt thiếu check-out',
  work_start_time: 'Giờ làm việc bắt đầu',
  work_end_time: 'Giờ làm việc kết thúc',
  late_grace_minutes: 'Số phút cho phép đi trễ',
  early_leave_grace_minutes: 'Số phút cho phép về sớm',
  leave_type: 'Loại nghỉ',
  request_type: 'Loại yêu cầu FaceID',
  image_count: 'Số ảnh mới',
  face_count_at_submit: 'Số mẫu khi gửi',
  planned_remove_count: 'Số ảnh cũ dự kiến thay',
  face_count_before: 'Số mẫu trước khi duyệt',
  removed_face_count: 'Số ảnh cũ đã thay',
  face_count_after: 'Số mẫu sau khi duyệt',
  reason: 'Lý do từ chối',
  start_date: 'Từ ngày',
  end_date: 'Đến ngày',
  reviewer_note: 'Ghi chú xử lý',
  effective_from: 'Áp dụng từ ngày',
  monday_enabled: 'Thứ 2',
  tuesday_enabled: 'Thứ 3',
  wednesday_enabled: 'Thứ 4',
  thursday_enabled: 'Thứ 5',
  friday_enabled: 'Thứ 6',
  saturday_enabled: 'Thứ 7',
  sunday_enabled: 'Chủ nhật',
  start_time: 'Giờ bắt đầu',
  end_time: 'Giờ kết thúc',
  late_allowed_minutes: 'Cho phép đi muộn',
  early_leave_allowed_minutes: 'Cho phép về sớm',
  checkout_cutoff_time: 'Giờ chốt thiếu check-out',
};

function parseAuditDetails(value) {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return { raw: String(value) };
  }
}

function auditTimeHtml(createdAt) {
  const parsed = new Date(createdAt);
  if (!Number.isNaN(parsed.getTime())) {
    const pad = (value) => String(value).padStart(2, '0');
    const time = `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`;
    const date = `${pad(parsed.getDate())}/${pad(parsed.getMonth() + 1)}/${parsed.getFullYear()}`;
    return `<div class="audit-time"><strong>${escapeHtml(time)}</strong><span>${escapeHtml(date)}</span></div>`;
  }
  const [date = '', time = ''] = String(createdAt || '').split('T');
  return `<div class="audit-time"><strong>${escapeHtml(time.slice(0, 8) || '--:--:--')}</strong><span>${escapeHtml(date.split('-').reverse().join('/') || '--/--/----')}</span></div>`;
}

function auditActorHtml(item) {
  if (!item.actor_username) {
    return '<div class="audit-person"><strong>Chưa xác thực</strong><span>Chưa đăng nhập</span></div>';
  }
  const role = item.actor_role ? roleLabel(item.actor_role) : '';
  return `<div class="audit-person"><strong>${escapeHtml(item.actor_username)}</strong>${role ? `<span>${escapeHtml(role)}</span>` : ''}</div>`;
}

function auditActionHtml(action) {
  const [label, tone] = AUDIT_ACTIONS[action] || [`Thao tác: ${action || 'không rõ'}`, 'neutral'];
  return `<span class="audit-event audit-event-${tone}">${escapeHtml(label)}</span>`;
}

function auditRelatedText(item, details) {
  if (item.entity_label) {
    if (item.entity_type === 'user') {
      return item.entity_label.replace(/\s+\((admin|lab_manager|student)\)$/i, '');
    }
    return item.entity_label;
  }
  if (item.action === 'settings.update') return 'Cấu hình hệ thống';
  if (item.action === 'alerts.scan_missing_checkouts') return 'Cảnh báo thiếu check-out';
  if (item.action === 'attendance.recalculate') {
    if (details.date_from || details.date_to) {
      return `Chấm công ${details.date_from || '...'} đến ${details.date_to || '...'}`;
    }
    return 'Dữ liệu chấm công';
  }
  if (item.entity_type === 'user') return details.username || 'Tài khoản';
  if (item.entity_type === 'student') return 'Sinh viên';
  if (item.entity_type === 'student_face') return 'Ảnh khuôn mặt sinh viên';
  if (item.entity_type === 'alert') return 'Cảnh báo';
  if (item.entity_type === 'access_log') return 'Log ra vào';
  if (item.entity_type === 'attendance_record') return 'Bản ghi chấm công';
  if (item.entity_type === 'face_registration_request') return 'Yêu cầu đăng ký FaceID';
  if (item.entity_type === 'work_schedule') return 'Lịch làm việc';
  if (item.entity_type === 'work_schedule_exception') return 'Ngoại lệ lịch làm việc';
  if (item.entity_type === 'settings') return 'Cấu hình hệ thống';
  return item.entity_type ? `Đối tượng: ${item.entity_type}` : `Thao tác: ${item.action || 'không rõ'}`;
}

function auditRelatedHtml(item, details) {
  const text = auditRelatedText(item, details);
  const pending = item.entity_type === 'user' && !item.entity_id && String(item.action || '').startsWith('auth.');
  return `<div class="audit-related"><strong>${escapeHtml(text)}</strong>${pending ? '<span>Chưa xác thực</span>' : ''}</div>`;
}

function auditValueText(value) {
  if (value === null || value === undefined || value === '') return 'trống';
  if (value === true || value === 'true') return 'Bật';
  if (value === false || value === 'false') return 'Tắt';
  if (value === 'active') return 'Hoạt động';
  if (value === 'inactive') return 'Đã khóa';
  if (value === 'new') return 'Mới';
  if (value === 'resolved') return 'Đã xử lý';
  if (value === 'ignored') return 'Bỏ qua';
  if (value === 'pending') return 'Chờ duyệt';
  if (value === 'approved') return 'Đã duyệt';
  if (value === 'rejected') return 'Từ chối';
  if (value === 'cancelled') return 'Đã hủy';
  if (value === 'revoked') return 'Đã thu hồi';
  return String(value);
}

function auditLeaveTypeText(value) {
  const labels = {
    sick: 'nghỉ ốm',
    personal: 'việc cá nhân',
    study: 'bận học / thi',
    family: 'việc gia đình',
    other: 'lý do khác',
  };
  return labels[value] || 'nghỉ phép';
}

function auditDateText(value) {
  const [year, month, day] = String(value || '').split('-');
  return year && month && day ? `${day}/${month}/${year}` : (value || 'không rõ ngày');
}

function auditLeaveRangeText(details) {
  if (!details.start_date || !details.end_date) return 'trong khoảng thời gian đã ghi nhận';
  const start = auditDateText(details.start_date);
  const end = auditDateText(details.end_date);
  return start === end ? `ngày ${start}` : `từ ${start} đến ${end}`;
}

function auditFaceRequestTypeText(value) {
  if (value === 'update') return 'cập nhật / bổ sung FaceID';
  if (value === 'initial') return 'đăng ký FaceID lần đầu';
  return 'FaceID';
}

function auditFaceRequestCapacityText(details, actual = false) {
  const removed = actual ? details.removed_face_count : details.planned_remove_count;
  const after = actual ? details.face_count_after : null;
  if (Number(removed || 0) > 0) {
    return ` Thay ${removed} ảnh FaceID cũ nhất${after != null ? `, còn ${after}/10 mẫu` : ''}.`;
  }
  if (after != null) return ` Không thay ảnh cũ, còn ${after}/10 mẫu.`;
  return '';
}

function auditAlertTypeText(value) {
  const labels = {
    unknown_face: 'khuôn mặt lạ',
    spoof_detected: 'nghi giả mạo',
    missing_checkout: 'thiếu check-out',
  };
  return labels[value] || value || 'không rõ loại';
}

function auditAttendanceResolutionText(value) {
  const labels = {
    check_out_now: 'ghi nhận check-out tại thời điểm xử lý',
    set_checkout_time: 'đặt giờ check-out thủ công',
    mark_absent: 'đánh dấu vắng',
    keep_missing: 'giữ trạng thái thiếu check-out',
  };
  return labels[value] || value || 'xử lý thiếu check-out';
}

function auditScheduleExceptionText(details) {
  const item = details.exception || details.after || details.before || {};
  const type = item.exception_type === 'working' ? 'ngày làm bù' : 'ngày nghỉ';
  const name = item.holiday_name ? ` “${item.holiday_name}”` : '';
  const date = item.exception_date ? ` ngày ${auditDateText(item.exception_date)}` : '';
  return `${type}${name}${date}`;
}

function auditActionDisplayText(action) {
  return AUDIT_ACTIONS[action]?.[0] || action || 'thao tác không xác định';
}

function auditFallbackContent(item, details) {
  const changes = auditChangesText(details.changes);
  if (changes) return `${changes}.`;
  const target = item.entity_label ? ` cho ${item.entity_label}` : '';
  const reason = details.reason || details.reviewer_note || details.note;
  return `Đã thực hiện “${auditActionDisplayText(item.action)}”${target}${reason ? `. Ghi chú: ${reason}` : '.'}`;
}

function auditChangesText(changes) {
  const entries = Object.entries(changes || {})
    .filter(([key]) => !['password_changed', 'sessions_revoked'].includes(key));
  if (!entries.length) return '';
  return entries.slice(0, 4).map(([key, change]) => {
    const label = AUDIT_FIELD_LABELS[key] || key;
    if (change && typeof change === 'object' && ('old' in change || 'new' in change)) {
      return `${label}: ${auditValueText(change.old)} → ${auditValueText(change.new)}`;
    }
    return `${label}: ${auditValueText(change)}`;
  }).join('; ');
}

function auditContentText(item, details) {
  switch (item.action) {
    case 'auth.login_success':
      return `Đăng nhập thành công${details.role ? ` với quyền ${roleLabel(details.role)}` : ''}.`;
    case 'auth.login_failed':
      return `Sai thông tin đăng nhập lần thứ ${details.failed_attempts ?? '?'}. Còn ${details.remaining_attempts ?? '?'} lần thử.`;
    case 'auth.login_rate_limited':
      return `Đã vượt quá số lần đăng nhập cho phép. Thử lại sau ${details.retry_after_seconds ?? '?'} giây.`;
    case 'auth.login_blocked':
      return 'Không thể đăng nhập vì tài khoản đang bị khóa.';
    case 'auth.logout':
      return 'Đã đăng xuất khỏi hệ thống.';
    case 'users.create':
      return `Đã tạo tài khoản ${item.entity_label || details.username || ''}${details.role ? ` với quyền ${roleLabel(details.role)}` : ''}.`.replace('  ', ' ');
    case 'users.update': {
      const changes = auditChangesText(details.changes);
      const notes = [];
      if (changes) notes.push(changes);
      if (details.changes?.password_changed || details.password_changed) notes.push('Đã đổi mật khẩu');
      if (details.changes?.sessions_revoked || details.sessions_revoked) notes.push('Đã thu hồi các phiên đăng nhập');
      return notes.length ? notes.join('. ') + '.' : 'Đã cập nhật thông tin tài khoản.';
    }
    case 'users.delete':
      return `Đã xóa tài khoản ${item.entity_label || details.username || ''} khỏi hệ thống.`.replace('  ', ' ');
    case 'students.create':
      return `Đã thêm hồ sơ sinh viên${details.class_name ? `, lớp ${details.class_name}` : ''}.`;
    case 'students.update': {
      const changes = auditChangesText(details.changes);
      return changes ? `${changes}.` : 'Đã cập nhật hồ sơ sinh viên.';
    }
    case 'students.delete':
      return `Đã xóa hồ sơ sinh viên${details.deleted_face_count ? ` và ${details.deleted_face_count} ảnh khuôn mặt` : ''}.`;
    case 'students.work_time.update': {
      const changes = auditChangesText(details.changes);
      return changes ? `${changes}.` : 'Đã cập nhật giờ làm việc.';
    }
    case 'students.work_time.reset':
      return details.previous
        ? `Đã đưa giờ làm việc về cấu hình mặc định (trước đó: ${details.previous.work_start_time || '--:--'} - ${details.previous.work_end_time || '--:--'}).`
        : 'Đã đưa giờ làm việc về cấu hình mặc định.';
    case 'faces.upload':
      return `Đã thêm một ảnh khuôn mặt. Hiện có ${details.face_count ?? '?'} ảnh.`;
    case 'faces.scan_replace':
      return `Đã thay bộ ảnh khuôn mặt bằng ${details.new_face_count ?? '?'} ảnh mới.`;
    case 'faces.delete':
      return 'Đã xóa một ảnh khuôn mặt.';
    case 'face_requests.submit':
      return `Đã gửi yêu cầu ${auditFaceRequestTypeText(details.request_type)} với ${details.image_count ?? 5} ảnh.${auditFaceRequestCapacityText(details)}`;
    case 'face_requests.approve':
      return `Đã duyệt yêu cầu ${auditFaceRequestTypeText(details.request_type)} và thêm ${details.image_count ?? 5} ảnh mới.${auditFaceRequestCapacityText(details, true)}`;
    case 'face_requests.reject':
      return `Đã từ chối yêu cầu ${auditFaceRequestTypeText(details.request_type)}${details.reason ? `. Lý do: ${details.reason}` : ''}.`;
    case 'face_requests.cancel':
      return `Sinh viên đã hủy yêu cầu ${auditFaceRequestTypeText(details.request_type)} khi đang chờ duyệt.`;
    case 'settings.update': {
      const changes = auditChangesText(details.changes);
      return changes ? `${changes}.` : 'Đã cập nhật cấu hình hệ thống.';
    }
    case 'work_schedule.settings.update': {
      const changes = auditChangesText(details.changes);
      const date = details.effective_from ? ` (áp dụng từ ngày ${auditDateText(details.effective_from)})` : '';
      const recalculated = Number(details.attendance_recalculated || 0);
      return `${changes || 'Đã cập nhật lịch làm việc'}${date}.${recalculated ? ` Đã tính lại ${recalculated} bản ghi chấm công.` : ''}`;
    }
    case 'work_schedule.exception.create':
      return `Đã thêm ${auditScheduleExceptionText(details)}.${Number(details.attendance_recalculated || 0) ? ` Đã tính lại ${details.attendance_recalculated} bản ghi chấm công.` : ''}`;
    case 'work_schedule.exception.update':
      return `Đã cập nhật ${auditScheduleExceptionText(details)}.${Number(details.attendance_recalculated || 0) ? ` Đã tính lại ${details.attendance_recalculated} bản ghi chấm công.` : ''}`;
    case 'work_schedule.exception.delete':
      return `Đã xóa ${auditScheduleExceptionText(details)}.${Number(details.attendance_recalculated || 0) ? ` Đã tính lại ${details.attendance_recalculated} bản ghi chấm công.` : ''}`;
    case 'alerts.scan_missing_checkouts':
      return `Đã quét thiếu check-out và tạo ${details.created ?? 0} cảnh báo mới.`;
    case 'alerts.status.update': {
      const changes = auditChangesText(details.changes);
      return changes ? `Cảnh báo ${auditAlertTypeText(details.type)}: ${changes}.` : `Đã cập nhật cảnh báo ${auditAlertTypeText(details.type)}.`;
    }
    case 'alerts.delete':
      return `Đã xóa cảnh báo ${auditAlertTypeText(details.type)}${details.status ? ` ở trạng thái ${auditValueText(details.status)}` : ''}.`;
    case 'access_logs.delete':
      return `Đã xóa log ${details.action === 'check_out' ? 'check-out' : 'check-in'}${details.attendance_date ? ` ngày ${auditDateText(details.attendance_date)}` : ''}${details.result ? ` (${auditValueText(details.result)})` : ''} và tính lại chấm công liên quan.`;
    case 'attendance.missing_checkout.resolve':
      return `Đã xử lý thiếu check-out bằng cách ${auditAttendanceResolutionText(details.resolution_type)}${details.checkout_time ? ` lúc ${details.checkout_time}` : ''}${details.reason ? `. Lý do: ${details.reason}` : ''}.`;
    case 'attendance.recalculate':
      return `Đã tính lại ${details.updated ?? 0} bản ghi chấm công.`;
    case 'leave_requests.create':
      return `Đã gửi đơn ${auditLeaveTypeText(details.leave_type)} ${auditLeaveRangeText(details)} để chờ duyệt.`;
    case 'leave_requests.approved':
      return `Đã duyệt đơn ${auditLeaveTypeText(details.leave_type)} ${auditLeaveRangeText(details)}${details.reviewer_note ? `. Ghi chú: ${details.reviewer_note}` : ''}.`;
    case 'leave_requests.rejected':
      return `Đã từ chối đơn ${auditLeaveTypeText(details.leave_type)} ${auditLeaveRangeText(details)}${details.reviewer_note ? `. Lý do: ${details.reviewer_note}` : ''}.`;
    case 'leave_requests.cancel':
      return `Sinh viên đã hủy đơn ${auditLeaveTypeText(details.leave_type)} ${auditLeaveRangeText(details)} khi đơn còn chờ duyệt.`;
    case 'leave_requests.revoke':
      return `Admin đã thu hồi đơn ${auditLeaveTypeText(details.leave_type)} ${auditLeaveRangeText(details)}${details.reviewer_note ? `. Lý do: ${details.reviewer_note}` : ''}.`;
    default:
      return auditFallbackContent(item, details);
  }
}

function auditTechnicalDetailsHtml(item, details) {
  const technical = {
    action: item.action || null,
    entity_type: item.entity_type || null,
    entity_id: item.entity_id || null,
    details,
  };
  return `<details class="audit-technical">
    <summary>Xem chi tiết kỹ thuật</summary>
    <pre class="audit-details">${escapeHtml(JSON.stringify(technical, null, 2))}</pre>
  </details>`;
}

function renderAuditRow(item) {
  const details = parseAuditDetails(item.details_json);
  return `<tr>
    <td>${auditTimeHtml(item.created_at)}</td>
    <td>${auditActorHtml(item)}</td>
    <td>${auditActionHtml(item.action)}</td>
    <td>${auditRelatedHtml(item, details)}</td>
    <td><div class="audit-content">${escapeHtml(auditContentText(item, details))}${auditTechnicalDetailsHtml(item, details)}</div></td>
    <td><span class="audit-ip">${escapeHtml(item.ip_address || '-')}</span></td>
  </tr>`;
}

async function loadAuditLogs() {
  if (!isAdmin()) return;
  const params = new URLSearchParams({ limit: '300' });
  appendFilter(params, 'auditDateFrom', 'date_from');
  appendFilter(params, 'auditDateTo', 'date_to');
  appendFilter(params, 'auditActor', 'actor');
  appendFilter(params, 'auditAction', 'action');
  appendFilter(params, 'auditEntityType', 'entity_type');
  appendFilter(params, 'auditSearch', 'q');
  const data = await api(`/api/audit-logs?${params.toString()}`);
  const body = document.getElementById('auditRows');
  if (body) {
    body.innerHTML = data.items?.length
      ? data.items.map(renderAuditRow).join('')
      : '<tr><td colspan="6">Chưa có audit log.</td></tr>';
  }
  const count = document.getElementById('auditCount');
  if (count) count.textContent = `Tìm thấy ${data.count ?? data.items?.length ?? 0} bản ghi`;
}

function resetAuditFilters() {
  setInputValue('auditSearch', '');
  setInputValue('auditActor', '');
  setInputValue('auditAction', '');
  setInputValue('auditEntityType', '');
  const today = todayText();
  setInputValue('auditDateFrom', today);
  setInputValue('auditDateTo', today);
  loadAuditLogs();
}
