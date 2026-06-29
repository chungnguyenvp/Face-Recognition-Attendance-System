const studentReportTypeLabels = {
  weekly: 'Báo cáo tuần', monthly: 'Báo cáo tháng', project_progress: 'Tiến độ đề tài',
  research: 'Tài liệu nghiên cứu', demo: 'Demo hệ thống', other: 'Khác',
};
const studentReportStatusLabels = {
  submitted: 'Chờ giáo viên xem', revision_requested: 'Cần chỉnh sửa', approved: 'Đã duyệt',
};
let activeStudentReportId = null;

function studentReportBadge(status) {
  const tone = status === 'approved' ? 'badge-success' : status === 'revision_requested' ? 'badge-denied' : 'badge-neutral';
  return `<span class="badge ${tone}">${escapeHtml(studentReportStatusLabels[status] || status || '-')}</span>`;
}

function studentReportDownloadUrl(reportId, versionNo) {
  return `/api/student/reports/${encodeURIComponent(reportId)}/versions/${encodeURIComponent(versionNo)}/download`;
}

function renderStudentReportRow(item) {
  const feedback = Number(item.feedback_count || 0);
  return `<tr>
    <td><strong>${escapeHtml(item.title)}</strong><br><span class="table-subtext">${item.current_original_filename ? escapeHtml(item.current_original_filename) : 'Nộp bằng link'}</span></td>
    <td>${escapeHtml(item.reviewer_username || '-')}</td>
    <td>${escapeHtml(studentReportTypeLabels[item.report_type] || item.report_type)}</td>
    <td>v${Number(item.current_version)}<br><span class="table-subtext">${escapeHtml(fmtDateTime(item.current_submitted_at))}</span></td>
    <td>${studentReportBadge(item.status)}${item.current_viewed_at ? '<br><span class="table-subtext">Đã xem</span>' : ''}</td>
    <td>${feedback ? `${feedback} phản hồi` : '-'}</td>
    <td><button class="secondary" type="button" onclick="openStudentReportDetail(${Number(item.id)})">Xem</button></td>
  </tr>`;
}

async function loadStudentReportReviewers() {
  const select = document.getElementById('studentReportReviewer');
  if (!select) return;
  const data = await api('/api/student/reports/reviewers');
  const items = data?.items || [];
  select.innerHTML = items.length
    ? `${items.length > 1 ? '<option value="">Chọn giáo viên</option>' : ''}${items.map((item) => `<option value="${Number(item.id)}">${escapeHtml(item.username)}</option>`).join('')}`
    : '<option value="">Chưa có giáo viên/lab manager hoạt động</option>';
}

async function loadStudentReports() {
  const rows = document.getElementById('studentReportRows');
  if (!rows) return;
  try {
    const [reports] = await Promise.all([api('/api/student/reports?limit=200'), loadStudentReportReviewers()]);
    const items = reports?.items || [];
    rows.innerHTML = items.map(renderStudentReportRow).join('') || '<tr><td colspan="7">Bạn chưa nộp báo cáo nào.</td></tr>';
  } catch (err) {
    rows.innerHTML = `<tr><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function submitStudentReport() {
  const message = document.getElementById('studentReportMessage');
  const title = getInputValue('studentReportTitle').trim();
  const reviewerId = getInputValue('studentReportReviewer');
  const attachment = document.getElementById('studentReportAttachment')?.files?.[0];
  const externalLink = getInputValue('studentReportLink').trim();
  if (!title || (!attachment && !externalLink)) {
    message.textContent = 'Nhập tiêu đề và đính kèm ít nhất một file hoặc link.';
    return;
  }
  const form = new FormData();
  form.append('title', title);
  form.append('report_type', getInputValue('studentReportType'));
  form.append('description', getInputValue('studentReportDescription'));
  form.append('external_link', externalLink);
  if (reviewerId) form.append('reviewer_id', reviewerId);
  if (attachment) form.append('attachment', attachment);
  try {
    await api('/api/student/reports', { method: 'POST', body: form });
    message.textContent = 'Đã gửi báo cáo cho giáo viên.';
    ['studentReportTitle', 'studentReportDescription', 'studentReportLink'].forEach((id) => { document.getElementById(id).value = ''; });
    document.getElementById('studentReportAttachment').value = '';
    await loadStudentReports();
  } catch (err) {
    message.textContent = err.message;
  }
}

function renderStudentReportDetail(item) {
  const versions = item.versions || [];
  const feedbacks = item.feedbacks || [];
  const versionRows = versions.map((version) => `<li><strong>Phiên bản ${Number(version.version_no)}</strong> · ${escapeHtml(fmtDateTime(version.submitted_at))}
    ${version.original_filename ? ` · <a href="${escapeHtml(studentReportDownloadUrl(item.id, version.version_no))}">${escapeHtml(version.original_filename)}</a>` : ''}
    ${version.external_link ? ` · <a href="${escapeHtml(version.external_link)}" target="_blank" rel="noopener noreferrer">Mở link</a>` : ''}
    ${version.description ? `<div class="student-report-note">${escapeHtml(version.description)}</div>` : ''}</li>`).join('');
  const feedbackRows = feedbacks.length ? feedbacks.map((feedback) => `<li><strong>${escapeHtml(feedback.reviewer_username || 'Giáo viên')}</strong> · ${studentReportBadge(feedback.status)} · ${escapeHtml(fmtDateTime(feedback.created_at))}${feedback.comment ? `<div class="student-report-note">${escapeHtml(feedback.comment)}</div>` : ''}</li>`).join('') : '<li>Chưa có phản hồi.</li>';
  return `<div class="student-report-detail-grid">
    <div><span>Sinh viên</span><strong>${escapeHtml(item.student_code)} · ${escapeHtml(item.full_name)}</strong></div>
    <div><span>Giáo viên</span><strong>${escapeHtml(item.reviewer_username)}</strong></div>
    <div><span>Loại</span><strong>${escapeHtml(studentReportTypeLabels[item.report_type] || item.report_type)}</strong></div>
    <div><span>Trạng thái</span><strong>${studentReportBadge(item.status)}</strong></div>
  </div>
  <h4>Phiên bản đã nộp</h4><ul class="student-report-history">${versionRows}</ul>
  <h4>Phản hồi của giáo viên</h4><ul class="student-report-history">${feedbackRows}</ul>`;
}

async function openStudentReportDetail(reportId) {
  const modal = document.getElementById('studentReportDetailModal');
  const message = document.getElementById('studentReportDetailMessage');
  try {
    const data = await api(`/api/student/reports/${encodeURIComponent(reportId)}`);
    const item = data.item;
    activeStudentReportId = Number(item.id);
    document.getElementById('studentReportDetailMeta').textContent = item.title;
    document.getElementById('studentReportDetailBody').innerHTML = renderStudentReportDetail(item);
    const panel = document.getElementById('studentReportResubmitPanel');
    panel.classList.toggle('hidden', item.status !== 'revision_requested');
    document.getElementById('studentReportResubmitDescription').value = '';
    document.getElementById('studentReportResubmitLink').value = '';
    document.getElementById('studentReportResubmitAttachment').value = '';
    message.textContent = '';
    modal.classList.remove('hidden');
  } catch (err) {
    alert(err.message);
  }
}

function closeStudentReportDetail() {
  document.getElementById('studentReportDetailModal').classList.add('hidden');
  activeStudentReportId = null;
}

async function resubmitStudentReport() {
  const message = document.getElementById('studentReportDetailMessage');
  const attachment = document.getElementById('studentReportResubmitAttachment')?.files?.[0];
  const externalLink = getInputValue('studentReportResubmitLink').trim();
  if (!activeStudentReportId || (!attachment && !externalLink)) {
    message.textContent = 'Đính kèm file mới hoặc nhập link mới để nộp lại.';
    return;
  }
  const form = new FormData();
  form.append('description', getInputValue('studentReportResubmitDescription'));
  form.append('external_link', externalLink);
  if (attachment) form.append('attachment', attachment);
  try {
    await api(`/api/student/reports/${encodeURIComponent(activeStudentReportId)}/resubmit`, { method: 'POST', body: form });
    closeStudentReportDetail();
    await loadStudentReports();
  } catch (err) {
    message.textContent = err.message;
  }
}
