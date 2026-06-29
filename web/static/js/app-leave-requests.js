const staffLeaveTypeLabels = { sick: 'Nghỉ ốm', personal: 'Việc cá nhân', study: 'Bận học / thi', family: 'Việc gia đình', other: 'Khác' };
const staffLeaveStatusLabels = { pending: 'Chờ duyệt', approved: 'Đã duyệt', rejected: 'Từ chối', cancelled: 'Đã hủy', revoked: 'Đã thu hồi' };
let leaveReviewAction = null;
let leaveReviewId = null;

function staffLeaveStatusBadge(status) {
  const tone = status === 'approved' ? 'badge-success' : status === 'rejected' || status === 'revoked' ? 'badge-denied' : 'badge-neutral';
  return `<span class="badge ${tone}">${escapeHtml(staffLeaveStatusLabels[status] || status || '-')}</span>`;
}

function leaveActionButtons(item) {
  if (item.status === 'pending') {
    return `<button onclick="openLeaveReviewModal(${Number(item.id)}, 'approve')">Duyệt</button>
      <button class="secondary" onclick="openLeaveReviewModal(${Number(item.id)}, 'reject')">Từ chối</button>`;
  }
  if (item.status === 'approved' && isAdmin()) {
    return `<button class="secondary" onclick="openLeaveReviewModal(${Number(item.id)}, 'revoke')">Thu hồi</button>`;
  }
  return '-';
}

function renderLeaveRow(item) {
  const reviewer = item.reviewer_username ? `${item.reviewer_username}${item.reviewer_note ? `: ${item.reviewer_note}` : ''}` : (item.reviewer_note || '-');
  return `<tr>
    <td><strong>${escapeHtml(item.student_code || '')}</strong><br><span class="table-subtext">${escapeHtml(item.full_name || '')}</span></td>
    <td>${escapeHtml(staffLeaveTypeLabels[item.leave_type] || item.leave_type)}</td>
    <td>${escapeHtml(attendanceDateText(item.start_date))}</td>
    <td>${escapeHtml(attendanceDateText(item.end_date))}</td>
    <td>${escapeHtml(item.reason)}</td>
    <td>${staffLeaveStatusBadge(item.status)}</td>
    <td>${escapeHtml(reviewer)}</td>
    <td>${leaveActionButtons(item)}</td>
  </tr>`;
}

async function loadLeaveRequests() {
  const params = new URLSearchParams({ limit: '300' });
  appendFilter(params, 'leaveSearch', 'q');
  appendFilter(params, 'leaveStatusFilter', 'status');
  appendFilter(params, 'leaveTypeFilter', 'leave_type');
  appendFilter(params, 'leaveDateFrom', 'date_from');
  appendFilter(params, 'leaveDateTo', 'date_to');
  const data = await api(`/api/leave-requests?${params.toString()}`);
  const items = data?.items || [];
  const table = document.getElementById('leaveTable');
  if (table) table.innerHTML = items.map(renderLeaveRow).join('') || '<tr><td colspan="8">Chưa có đơn nghỉ phép.</td></tr>';
  const count = document.getElementById('leaveCount');
  if (count) count.textContent = `Tìm thấy ${data?.count ?? items.length} đơn`;
}

function openLeaveReviewModal(leaveId, action) {
  leaveReviewId = leaveId;
  leaveReviewAction = action;
  const title = document.getElementById('leaveReviewTitle');
  const hint = document.getElementById('leaveReviewHint');
  const note = document.getElementById('leaveReviewNote');
  const submit = document.getElementById('leaveReviewSubmitBtn');
  const required = action !== 'approve';
  title.textContent = action === 'approve' ? 'Duyệt đơn nghỉ' : action === 'reject' ? 'Từ chối đơn nghỉ' : 'Thu hồi đơn đã duyệt';
  hint.textContent = required ? 'Bạn phải nhập lý do cho thao tác này.' : 'Ghi chú là không bắt buộc.';
  note.value = '';
  note.required = required;
  submit.textContent = action === 'approve' ? 'Xác nhận duyệt' : action === 'reject' ? 'Xác nhận từ chối' : 'Xác nhận thu hồi';
  document.getElementById('leaveReviewMessage').textContent = '';
  document.getElementById('leaveReviewModal').classList.remove('hidden');
}

function closeLeaveReviewModal() {
  document.getElementById('leaveReviewModal').classList.add('hidden');
  leaveReviewAction = null;
  leaveReviewId = null;
}

async function submitLeaveReview() {
  const note = document.getElementById('leaveReviewNote').value.trim();
  const message = document.getElementById('leaveReviewMessage');
  if (!leaveReviewId || !leaveReviewAction) return;
  if (leaveReviewAction !== 'approve' && note.length < 3) {
    message.textContent = 'Vui lòng nhập lý do ít nhất 3 ký tự.';
    return;
  }
  try {
    const endpoint = `/api/leave-requests/${encodeURIComponent(leaveReviewId)}/${leaveReviewAction}`;
    await api(endpoint, { method: 'PATCH', body: JSON.stringify({ reviewer_note: note || null }) });
    closeLeaveReviewModal();
    await loadLeaveRequests();
  } catch (err) {
    message.textContent = err.message;
  }
}
