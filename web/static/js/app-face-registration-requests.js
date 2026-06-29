let activeFaceRegistrationRequest = null;

function setFaceRegistrationTab(tab) {
  const showingRequests = tab === 'requests';
  document.getElementById('manualFaceRegistrationPanel')?.classList.toggle('hidden', showingRequests);
  document.getElementById('faceRequestReviewPanel')?.classList.toggle('hidden', !showingRequests);
  document.getElementById('manualFaceRegistrationTab')?.classList.toggle('active', !showingRequests);
  document.getElementById('faceRequestReviewTab')?.classList.toggle('active', showingRequests);
  if (showingRequests) {
    stopFaceRegisterCamera(false);
    loadFaceRegistrationRequests();
  }
}

function faceRequestStatusText(status) {
  const labels = {
    pending: 'Chờ duyệt',
    approved: 'Đã duyệt',
    rejected: 'Từ chối',
    cancelled: 'Đã hủy',
  };
  return labels[status] || status || '-';
}

function faceRequestStatusBadge(status) {
  const className = status === 'approved'
    ? 'badge-success'
    : status === 'rejected'
      ? 'badge-denied'
      : status === 'pending'
        ? 'badge-warning'
        : 'badge-neutral';
  return `<span class="badge ${className}">${escapeHtml(faceRequestStatusText(status))}</span>`;
}

function faceRequestTypeText(type) {
  return type === 'update' ? 'Cập nhật / bổ sung' : 'Đăng ký lần đầu';
}

function faceRequestDateText(value) {
  return value ? String(value).replace('T', ' ') : '-';
}

async function loadFaceRegistrationRequests() {
  const rows = document.getElementById('faceRequestRows');
  const count = document.getElementById('faceRequestCount');
  if (!rows) return;
  rows.innerHTML = '<tr><td colspan="7">Đang tải...</td></tr>';
  try {
    const status = document.getElementById('faceRequestStatusFilter')?.value || '';
    const q = document.getElementById('faceRequestSearch')?.value.trim() || '';
    const params = new URLSearchParams({ limit: '200' });
    if (status) params.set('status', status);
    if (q) params.set('q', q);
    const data = await api(`/api/face-registration-requests?${params.toString()}`);
    const items = data?.items || [];
    rows.innerHTML = items.map((item) => `
      <tr>
        <td><strong>${escapeHtml(item.student_code || '-')}</strong><br /><span class="muted">${escapeHtml(item.full_name || '')}</span></td>
        <td>${escapeHtml(faceRequestTypeText(item.request_type))}</td>
        <td>${escapeHtml(item.class_name || '-')}</td>
        <td>${escapeHtml(faceRequestDateText(item.created_at))}</td>
        <td>${faceRequestStatusBadge(item.status)}</td>
        <td>${escapeHtml(item.note || '-')}</td>
        <td><button type="button" onclick="openFaceRequestDetail(${Number(item.id)})">Xem</button></td>
      </tr>
    `).join('') || '<tr><td colspan="7">Không có yêu cầu phù hợp.</td></tr>';
    if (count) count.textContent = `Tìm thấy ${data?.count ?? items.length} yêu cầu`;
  } catch (error) {
    rows.innerHTML = `<tr><td colspan="7">${escapeHtml(error.message || 'Không tải được yêu cầu.')}</td></tr>`;
    if (count) count.textContent = '';
  }
}

function faceRequestImageUrl(requestId, position) {
  return `/api/face-registration-requests/${encodeURIComponent(requestId)}/images/${encodeURIComponent(position)}`;
}

async function openFaceRequestDetail(requestId) {
  const modal = document.getElementById('faceRequestDetailModal');
  const body = document.getElementById('faceRequestDetailBody');
  const message = document.getElementById('faceRequestDetailMessage');
  if (!modal || !body) return;
  modal.classList.remove('hidden');
  body.innerHTML = '<div class="detail-empty">Đang tải chi tiết yêu cầu...</div>';
  if (message) message.textContent = '';
  document.getElementById('faceRequestRejectPanel')?.classList.add('hidden');
  const reason = document.getElementById('faceRequestRejectReason');
  if (reason) reason.value = '';
  document.getElementById('faceRequestDetailActions').innerHTML = '';
  try {
    const data = await api(`/api/face-registration-requests/${requestId}`);
    activeFaceRegistrationRequest = data.item;
    renderFaceRequestDetail();
  } catch (error) {
    body.innerHTML = `<div class="detail-empty">${escapeHtml(error.message || 'Không tải được chi tiết.')}</div>`;
  }
}

function renderFaceRequestDetail() {
  const item = activeFaceRegistrationRequest;
  const body = document.getElementById('faceRequestDetailBody');
  const student = document.getElementById('faceRequestDetailStudent');
  const actions = document.getElementById('faceRequestDetailActions');
  if (!item || !body || !actions) return;
  if (student) student.textContent = `${item.student_code || '-'} · ${item.full_name || '-'}${item.class_name ? ` · ${item.class_name}` : ''}`;
  const positions = [
    ['front', 'Chính diện'],
    ['left', 'Nghiêng trái'],
    ['right', 'Nghiêng phải'],
    ['up', 'Nhìn lên'],
    ['down', 'Nhìn xuống'],
  ];
  const currentCount = Number(item.official_face_count_now ?? item.face_count_at_submit ?? 0);
  const replaceCount = Number(item.replace_count_now ?? item.planned_remove_count ?? 0);
  const afterCount = Number(item.face_count_after_approval ?? currentCount - replaceCount + positions.length);
  const capacityText = replaceCount > 0
    ? `Bỏ ${replaceCount} ảnh FaceID cũ nhất, thêm 5 ảnh mới → ${afterCount}/10 mẫu.`
    : `Thêm 5 ảnh mới, không bỏ ảnh cũ → ${afterCount}/10 mẫu.`;
  body.innerHTML = `
    <div class="face-request-detail-meta">
      <div><span>Trạng thái</span><strong>${faceRequestStatusBadge(item.status)}</strong></div>
      <div><span>Loại yêu cầu</span><strong>${escapeHtml(faceRequestTypeText(item.request_type))}</strong></div>
      <div><span>Gửi lúc</span><strong>${escapeHtml(faceRequestDateText(item.created_at))}</strong></div>
      <div><span>Mẫu FaceID hiện tại</span><strong>${currentCount}/10 mẫu</strong></div>
      <div><span>Kết quả khi duyệt</span><strong>${escapeHtml(capacityText)}</strong></div>
      <div><span>Ghi chú</span><strong>${escapeHtml(item.note || '-')}</strong></div>
      ${item.reject_reason ? `<div><span>Lý do từ chối</span><strong>${escapeHtml(item.reject_reason)}</strong></div>` : ''}
    </div>
    <div class="face-request-images">
      ${positions.map(([key, label]) => `<article><span>${label}</span><img src="${faceRequestImageUrl(item.id, key)}" alt="${escapeHtml(label)}" loading="lazy" /></article>`).join('')}
    </div>
  `;
  const rejectPanel = document.getElementById('faceRequestRejectPanel');
  const reason = document.getElementById('faceRequestRejectReason');
  if (item.status === 'pending') {
    rejectPanel?.classList.remove('hidden');
    actions.innerHTML = '<button type="button" onclick="approveFaceRegistrationRequest()">Duyệt yêu cầu</button><button type="button" class="danger-lite" onclick="rejectFaceRegistrationRequest()">Từ chối yêu cầu</button>';
  } else {
    rejectPanel?.classList.add('hidden');
    if (reason) reason.value = '';
    actions.innerHTML = '';
  }
}

async function approveFaceRegistrationRequest() {
  const item = activeFaceRegistrationRequest;
  const message = document.getElementById('faceRequestDetailMessage');
  if (!item || item.status !== 'pending') return;
  const replaceCount = Number(item.replace_count_now ?? item.planned_remove_count ?? 0);
  const confirmation = replaceCount > 0
    ? `Duyệt 5 ảnh mới của ${item.full_name || item.student_code}? ${replaceCount} ảnh FaceID cũ nhất sẽ bị thay.`
    : `Duyệt và thêm 5 ảnh FaceID mới cho ${item.full_name || item.student_code}?`;
  if (!confirm(confirmation)) return;
  if (message) message.textContent = 'Đang kiểm tra và tạo FaceID chính thức...';
  try {
    const data = await api(`/api/face-registration-requests/${item.id}/approve`, { method: 'PATCH' });
    activeFaceRegistrationRequest = data.item;
    closeFaceRequestDetailModal();
    await Promise.all([loadFaceRegistrationRequests(), loadStudents(), loadDashboard()]);
  } catch (error) {
    if (message) message.textContent = error.message || 'Không duyệt được yêu cầu.';
  }
}

async function rejectFaceRegistrationRequest() {
  const item = activeFaceRegistrationRequest;
  const message = document.getElementById('faceRequestDetailMessage');
  const reason = document.getElementById('faceRequestRejectReason')?.value.trim() || '';
  if (!item || item.status !== 'pending') return;
  if (reason.length < 3) {
    if (message) message.textContent = 'Vui lòng nhập lý do từ chối.';
    return;
  }
  if (!confirm(`Xác nhận từ chối yêu cầu FaceID của ${item.full_name || item.student_code}?`)) return;
  if (message) message.textContent = 'Đang từ chối yêu cầu...';
  try {
    const data = await api(`/api/face-registration-requests/${item.id}/reject`, {
      method: 'PATCH',
      body: JSON.stringify({ reason }),
    });
    activeFaceRegistrationRequest = data.item;
    closeFaceRequestDetailModal();
    await loadFaceRegistrationRequests();
  } catch (error) {
    if (message) message.textContent = error.message || 'Không từ chối được yêu cầu.';
  }
}

function closeFaceRequestDetailModal() {
  document.getElementById('faceRequestDetailModal')?.classList.add('hidden');
  document.getElementById('faceRequestRejectPanel')?.classList.add('hidden');
  activeFaceRegistrationRequest = null;
}
