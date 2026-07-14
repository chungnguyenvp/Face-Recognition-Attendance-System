function copyAttendanceExportFilter(sourceId, targetId) {
  const source = document.getElementById(sourceId);
  const target = document.getElementById(targetId);
  if (target) target.value = source?.value || '';
}

function setAttendanceExportMessage(message, isError = false) {
  const element = document.getElementById('attendanceExportMessage');
  if (!element) return;
  element.textContent = message || '';
  element.classList.toggle('error-message', Boolean(isError));
}

function openAttendanceExportModal() {
  copyAttendanceExportFilter('attendanceDateFrom', 'exportAttendanceDateFrom');
  copyAttendanceExportFilter('attendanceDateTo', 'exportAttendanceDateTo');
  copyAttendanceExportFilter('attendanceStatusFilter', 'exportAttendanceStatus');
  setInputValue('exportAttendanceQuery', '');
  setAttendanceExportMessage('');
  const modal = document.getElementById('attendanceExportModal');
  if (modal) modal.classList.remove('hidden');
}

function closeAttendanceExportModal() {
  const modal = document.getElementById('attendanceExportModal');
  if (modal) modal.classList.add('hidden');
}

function attendanceExportPayload() {
  const status = getInputValue('exportAttendanceStatus');
  const query = getInputValue('exportAttendanceQuery');
  return {
    date_from: getInputValue('exportAttendanceDateFrom'),
    date_to: getInputValue('exportAttendanceDateTo'),
    status: status || null,
    q: query || null,
    include_summary: Boolean(document.getElementById('exportIncludeSummary')?.checked),
    include_details: Boolean(document.getElementById('exportIncludeDetails')?.checked),
  };
}

function attendanceExportFilename(response) {
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || 'bao_cao_cham_cong.xlsx';
}

async function exportAttendanceXlsx() {
  const button = document.getElementById('attendanceExportSubmit');
  const payload = attendanceExportPayload();
  if (!payload.date_from || !payload.date_to) {
    setAttendanceExportMessage('Vui lòng chọn đầy đủ Từ ngày và Đến ngày.', true);
    return;
  }
  if (!payload.include_summary && !payload.include_details) {
    setAttendanceExportMessage('Vui lòng chọn ít nhất một trang báo cáo.', true);
    return;
  }

  setAttendanceExportMessage('Đang tạo file Excel...');
  if (button) button.disabled = true;
  try {
    const response = await fetch('/api/exports/attendance', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
      body: JSON.stringify(payload),
    });
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(apiErrorMessage(data.detail));
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = attendanceExportFilename(response);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setAttendanceExportMessage('Đã tạo file Excel thành công.');
  } catch (error) {
    setAttendanceExportMessage(error.message || 'Không thể xuất báo cáo.', true);
  } finally {
    if (button) button.disabled = false;
  }
}
