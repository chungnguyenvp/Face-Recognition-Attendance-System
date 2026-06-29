const leaveTypeLabels = {
  sick: 'Nghỉ ốm',
  personal: 'Việc cá nhân',
  study: 'Bận học / thi',
  family: 'Việc gia đình',
  other: 'Khác',
};

const leaveStatusLabels = {
  pending: 'Chờ duyệt',
  approved: 'Đã duyệt',
  rejected: 'Từ chối',
  cancelled: 'Đã hủy',
  revoked: 'Đã thu hồi',
};

function leaveStatusBadge(status) {
  const tone = status === 'approved' ? 'badge-success' : status === 'rejected' || status === 'revoked' ? 'badge-denied' : 'badge-neutral';
  return `<span class="badge ${tone}">${escapeHtml(leaveStatusLabels[status] || status || '-')}</span>`;
}

function renderStudentLeaveRow(item) {
  const cancelButton = item.status === 'pending'
    ? `<button class="secondary" onclick="cancelLeaveRequest(${Number(item.id)})">Hủy đơn</button>`
    : '-';
  return `<tr>
    <td>${escapeHtml(fmtDate(item.start_date))}</td>
    <td>${escapeHtml(fmtDate(item.end_date))}</td>
    <td>${escapeHtml(leaveTypeLabels[item.leave_type] || item.leave_type)}</td>
    <td>${escapeHtml(item.reason)}</td>
    <td>${leaveStatusBadge(item.status)}</td>
    <td>${escapeHtml(item.reviewer_note || '-')}</td>
    <td>${cancelButton}</td>
  </tr>`;
}

async function loadStudentLeaveRequests() {
  const data = await api('/api/student/leave-requests?limit=200');
  const items = data?.items || [];
  const rows = document.getElementById('studentLeaveRows');
  if (rows) rows.innerHTML = items.map(renderStudentLeaveRow).join('') || '<tr><td colspan="7">Chưa có đơn nghỉ phép.</td></tr>';
}

async function createLeaveRequest() {
  const message = document.getElementById('studentLeaveMessage');
  const payload = {
    leave_type: getInputValue('leaveType'),
    start_date: getInputValue('leaveStartDate'),
    end_date: getInputValue('leaveEndDate'),
    reason: getInputValue('leaveReason'),
  };
  if (!payload.start_date || !payload.end_date || !payload.reason.trim()) {
    if (message) message.textContent = 'Vui lòng nhập đầy đủ thông tin.';
    return;
  }
  try {
    await api('/api/student/leave-requests', { method: 'POST', body: JSON.stringify(payload) });
    if (message) message.textContent = 'Đã gửi đơn nghỉ phép, đang chờ xử lý.';
    document.getElementById('leaveReason').value = '';
    await loadStudentLeaveRequests();
    await loadStudentOverview();
  } catch (err) {
    if (message) message.textContent = err.message;
  }
}

async function cancelLeaveRequest(leaveId) {
  if (!window.confirm('Bạn có chắc muốn hủy đơn đang chờ duyệt?')) return;
  const message = document.getElementById('studentLeaveMessage');
  try {
    await api(`/api/student/leave-requests/${encodeURIComponent(leaveId)}/cancel`, { method: 'PATCH' });
    if (message) message.textContent = 'Đã hủy đơn nghỉ phép.';
    await loadStudentLeaveRequests();
    await loadStudentOverview();
  } catch (err) {
    if (message) message.textContent = err.message;
  }
}
