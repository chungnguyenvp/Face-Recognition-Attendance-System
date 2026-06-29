const staffReportTypeLabels = {
  weekly: 'Báo cáo tuần', monthly: 'Báo cáo tháng', project_progress: 'Tiến độ đề tài',
  research: 'Tài liệu nghiên cứu', demo: 'Demo hệ thống', other: 'Khác',
};
const staffReportStatusLabels = { submitted: 'Chờ xem', revision_requested: 'Cần chỉnh sửa', approved: 'Đã duyệt' };
let activeStaffReportId = null;

function staffReportDateTime(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
  }
  return String(value).replace('T', ' ');
}

function staffReportBadge(status) {
  const tone = status === 'approved' ? 'badge-success' : status === 'revision_requested' ? 'badge-denied' : 'badge-neutral';
  return `<span class="badge ${tone}">${escapeHtml(staffReportStatusLabels[status] || status || '-')}</span>`;
}

function staffReportDownloadUrl(reportId, versionNo) {
  return `/api/reports/${encodeURIComponent(reportId)}/versions/${encodeURIComponent(versionNo)}/download`;
}

function renderStaffReportRow(item) {
  return `<tr>
    <td><strong>${escapeHtml(item.student_code)}</strong><br><span class="table-subtext">${escapeHtml(item.full_name)}</span></td>
    <td><strong>${escapeHtml(item.title)}</strong>${item.current_original_filename ? `<br><span class="table-subtext">${escapeHtml(item.current_original_filename)}</span>` : ''}</td>
    <td>${escapeHtml(staffReportTypeLabels[item.report_type] || item.report_type)}</td>
    <td>v${Number(item.current_version)}<br><span class="table-subtext">${escapeHtml(staffReportDateTime(item.current_submitted_at))}</span></td>
    <td>${staffReportBadge(item.status)}${item.current_viewed_at ? '<br><span class="table-subtext">Đã xem</span>' : ''}</td>
    <td>${Number(item.feedback_count || 0) || '-'}</td>
    <td><button class="secondary" type="button" onclick="openStaffReportDetail(${Number(item.id)})">Xem</button></td>
  </tr>`;
}

async function loadStaffReports() {
  const rows = document.getElementById('staffReportRows');
  if (!rows) return;
  const params = new URLSearchParams({ limit: '300' });
  appendFilter(params, 'staffReportSearch', 'q');
  appendFilter(params, 'staffReportStatus', 'status');
  appendFilter(params, 'staffReportType', 'report_type');
  try {
    const data = await api(`/api/reports?${params.toString()}`);
    const items = data?.items || [];
    rows.innerHTML = items.map(renderStaffReportRow).join('') || '<tr><td colspan="7">Chưa có báo cáo phù hợp.</td></tr>';
    document.getElementById('staffReportCount').textContent = `Tìm thấy ${data?.count ?? items.length} báo cáo`;
  } catch (err) {
    rows.innerHTML = `<tr><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderStaffReportDetail(item) {
  const versions = item.versions || [];
  const feedbacks = item.feedbacks || [];
  const versionsHtml = versions.map((version) => `<li><strong>Phiên bản ${Number(version.version_no)}</strong> · ${escapeHtml(staffReportDateTime(version.submitted_at))}
    ${version.original_filename ? ` · <a href="${escapeHtml(staffReportDownloadUrl(item.id, version.version_no))}">${escapeHtml(version.original_filename)}</a>` : ''}
    ${version.external_link ? ` · <a href="${escapeHtml(version.external_link)}" target="_blank" rel="noopener noreferrer">Mở link</a>` : ''}
    ${version.description ? `<div class="student-report-note">${escapeHtml(version.description)}</div>` : ''}</li>`).join('');
  const feedbackHtml = feedbacks.length ? feedbacks.map((feedback) => `<li><strong>${escapeHtml(feedback.reviewer_username)}</strong> · ${staffReportBadge(feedback.status)} · ${escapeHtml(staffReportDateTime(feedback.created_at))}${feedback.comment ? `<div class="student-report-note">${escapeHtml(feedback.comment)}</div>` : ''}</li>`).join('') : '<li>Chưa có phản hồi.</li>';
  return `<div class="student-report-detail-grid">
    <div><span>Sinh viên</span><strong>${escapeHtml(item.student_code)} · ${escapeHtml(item.full_name)}</strong></div>
    <div><span>Giáo viên nhận</span><strong>${escapeHtml(item.reviewer_username)}</strong></div>
    <div><span>Loại</span><strong>${escapeHtml(staffReportTypeLabels[item.report_type] || item.report_type)}</strong></div>
    <div><span>Trạng thái</span><strong>${staffReportBadge(item.status)}</strong></div>
  </div>
  <h4>Phiên bản đã nộp</h4><ul class="student-report-history">${versionsHtml}</ul>
  <h4>Lịch sử phản hồi</h4><ul class="student-report-history">${feedbackHtml}</ul>`;
}

async function openStaffReportDetail(reportId) {
  try {
    const data = await api(`/api/reports/${encodeURIComponent(reportId)}`);
    const item = data.item;
    activeStaffReportId = Number(item.id);
    document.getElementById('staffReportDetailTitle').textContent = item.title;
    document.getElementById('staffReportDetailMeta').textContent = `${item.student_code} · ${item.full_name}`;
    document.getElementById('staffReportDetailBody').innerHTML = renderStaffReportDetail(item);
    document.getElementById('staffReportReviewPanel').classList.toggle('hidden', item.status !== 'submitted');
    document.getElementById('staffReportReviewNote').value = '';
    document.getElementById('staffReportDetailMessage').textContent = currentUser?.role === 'admin'
      ? 'Admin đang xem ở chế độ giám sát; phản hồi sẽ được ghi nhận là xử lý thay giáo viên.' : '';
    document.getElementById('staffReportDetailModal').classList.remove('hidden');
    await loadStaffReports();
  } catch (err) {
    alert(err.message);
  }
}

function closeStaffReportDetail() {
  document.getElementById('staffReportDetailModal').classList.add('hidden');
  activeStaffReportId = null;
}

async function submitStaffReportReview(status) {
  const message = document.getElementById('staffReportDetailMessage');
  const comment = document.getElementById('staffReportReviewNote').value.trim();
  if (!activeStaffReportId) return;
  if (status === 'revision_requested' && comment.length < 3) {
    message.textContent = 'Nhập nhận xét ít nhất 3 ký tự khi yêu cầu chỉnh sửa.';
    return;
  }
  try {
    await api(`/api/reports/${encodeURIComponent(activeStaffReportId)}/review`, {
      method: 'POST', body: JSON.stringify({ status, comment: comment || null }),
    });
    closeStaffReportDetail();
    await loadStaffReports();
  } catch (err) {
    message.textContent = err.message;
  }
}
