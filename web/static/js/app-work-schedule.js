let workScheduleMonth = new Date().getMonth() + 1;
let workScheduleYear = new Date().getFullYear();
let workScheduleExceptions = [];

const WORK_SCHEDULE_WEEKDAYS = [
  'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
];

function workScheduleDateText(value) {
  return attendanceDateText(value);
}

function isWorkScheduleAdmin() {
  return typeof isAdmin === 'function' && isAdmin();
}

function setWorkScheduleMessage(id, message, isError = false) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = message || '';
  element.classList.toggle('error-text', Boolean(isError));
}

function fillWorkScheduleSettings(settings) {
  const effectiveInput = document.getElementById('workScheduleEffectiveFrom');
  effectiveInput.value = todayText();
  WORK_SCHEDULE_WEEKDAYS.forEach((name) => {
    const input = document.getElementById(`workSchedule${name}`);
    if (input) input.checked = Boolean(Number(settings[`${name.toLowerCase()}_enabled`]));
  });
  document.getElementById('workScheduleStartTime').value = settings.start_time || '08:00';
  document.getElementById('workScheduleEndTime').value = settings.end_time || '17:00';
  document.getElementById('workScheduleLateMinutes').value = settings.late_allowed_minutes ?? 5;
  document.getElementById('workScheduleEarlyMinutes').value = settings.early_leave_allowed_minutes ?? 10;
  document.getElementById('workScheduleCutoffTime').value = settings.checkout_cutoff_time || '20:00';
}

function renderWorkScheduleToday(policy) {
  document.getElementById('workScheduleTodayDate').textContent = workScheduleDateText(policy.date);
  document.getElementById('workScheduleTodayWeekday').textContent = policy.weekday_label || '';
  document.getElementById('workScheduleTodayStatus').textContent = policy.label || '--';
  document.getElementById('workScheduleTodayNote').textContent = policy.note || (policy.is_working_day ? 'Có yêu cầu điểm danh' : 'Không yêu cầu điểm danh');
  const config = policy.config || {};
  document.getElementById('workScheduleTodayHours').textContent = policy.is_working_day
    ? `${config.start_time || '--:--'} - ${config.end_time || '--:--'}`
    : 'Không áp dụng';
  document.getElementById('workScheduleTodayGrace').textContent = policy.is_working_day
    ? `Muộn ${config.late_allowed_minutes || 0} phút · Về sớm ${config.early_leave_allowed_minutes || 0} phút`
    : 'Không tính chuyên cần';
}

function applyWorkSchedulePermission() {
  const editable = isWorkScheduleAdmin();
  document.querySelectorAll('#workSchedule .work-schedule-config-card input, #workSchedule .work-schedule-exceptions-card input').forEach((input) => {
    input.disabled = !editable;
  });
  document.getElementById('saveWorkScheduleBtn').hidden = !editable;
  document.getElementById('saveWorkScheduleExceptionBtn').hidden = !editable;
  document.getElementById('cancelWorkScheduleExceptionBtn').hidden = true;
}

function renderWorkScheduleExceptions() {
  const rows = document.getElementById('workScheduleExceptionRows');
  if (!workScheduleExceptions.length) {
    rows.innerHTML = '<tr><td colspan="4">Chưa có ngày nghỉ đặc biệt.</td></tr>';
    return;
  }
  rows.innerHTML = workScheduleExceptions.map((item) => {
    const action = isWorkScheduleAdmin()
      ? `<div class="account-row-actions"><button class="secondary" type="button" onclick="editWorkScheduleException(${item.id})">Sửa</button><button class="secondary" type="button" onclick="deleteWorkScheduleException(${item.id})">Xóa</button></div>`
      : '-';
    return `<tr><td>${escapeHtml(workScheduleDateText(item.exception_date))}</td><td>${escapeHtml(item.holiday_name)}</td><td>${escapeHtml(item.note || '-')}</td><td>${action}</td></tr>`;
  }).join('');
}

function renderWorkScheduleCalendar(data) {
  const title = document.getElementById('workScheduleCalendarTitle');
  title.textContent = `Tháng ${String(data.month).padStart(2, '0')}/${data.year}`;
  const firstDay = (new Date(data.year, data.month - 1, 1).getDay() + 6) % 7;
  const days = data.days || [];
  const emptyCells = Array.from({ length: firstDay }, () => '<div class="schedule-calendar-day empty"></div>');
  const today = todayText();
  const cells = days.map((day) => {
    const classes = ['schedule-calendar-day', day.status.replaceAll('_', '-')];
    if (day.date === today) classes.push('today');
    const detail = day.holiday_name ? `<small>${escapeHtml(day.holiday_name)}</small>` : '';
    return `<div class="${classes.join(' ')}" title="${escapeHtml(day.label || '')}"><span>${day.day}</span>${detail}</div>`;
  });
  document.getElementById('workScheduleCalendarGrid').innerHTML = [...emptyCells, ...cells].join('');
}

async function loadWorkSchedulePage() {
  try {
    const [today, settingsData, exceptions, calendar] = await Promise.all([
      api('/api/work-schedule/today'),
      api('/api/work-schedule/settings'),
      api('/api/work-schedule/exceptions'),
      api(`/api/work-schedule/calendar?year=${workScheduleYear}&month=${workScheduleMonth}`),
    ]);
    renderWorkScheduleToday(today);
    fillWorkScheduleSettings(settingsData);
    workScheduleExceptions = exceptions.items || [];
    renderWorkScheduleExceptions();
    renderWorkScheduleCalendar(calendar);
    applyWorkSchedulePermission();
  } catch (error) {
    setWorkScheduleMessage('workScheduleMessage', `Không tải được lịch làm việc: ${error.message}`, true);
  }
}

async function saveWorkSchedule() {
  if (!isWorkScheduleAdmin()) return;
  const payload = {
    effective_from: document.getElementById('workScheduleEffectiveFrom').value || todayText(),
    monday_enabled: document.getElementById('workScheduleMonday').checked,
    tuesday_enabled: document.getElementById('workScheduleTuesday').checked,
    wednesday_enabled: document.getElementById('workScheduleWednesday').checked,
    thursday_enabled: document.getElementById('workScheduleThursday').checked,
    friday_enabled: document.getElementById('workScheduleFriday').checked,
    saturday_enabled: document.getElementById('workScheduleSaturday').checked,
    sunday_enabled: document.getElementById('workScheduleSunday').checked,
    start_time: document.getElementById('workScheduleStartTime').value,
    end_time: document.getElementById('workScheduleEndTime').value,
    late_allowed_minutes: Number(document.getElementById('workScheduleLateMinutes').value),
    early_leave_allowed_minutes: Number(document.getElementById('workScheduleEarlyMinutes').value),
    checkout_cutoff_time: document.getElementById('workScheduleCutoffTime').value,
  };
  try {
    const result = await api('/api/work-schedule/settings', { method: 'PUT', body: JSON.stringify(payload) });
    setWorkScheduleMessage('workScheduleMessage', `Đã lưu lịch làm việc. Đã tính lại ${result.attendance_recalculated || 0} bản ghi hôm nay.`);
    await loadWorkSchedulePage();
  } catch (error) {
    setWorkScheduleMessage('workScheduleMessage', `Không lưu được: ${apiErrorMessage(error.message)}`, true);
  }
}

function resetWorkScheduleExceptionForm() {
  document.getElementById('workScheduleExceptionId').value = '';
  document.getElementById('workScheduleExceptionDate').value = '';
  document.getElementById('workScheduleExceptionName').value = '';
  document.getElementById('workScheduleExceptionNote').value = '';
  document.getElementById('saveWorkScheduleExceptionBtn').textContent = 'Thêm ngày nghỉ';
  document.getElementById('cancelWorkScheduleExceptionBtn').hidden = true;
  setWorkScheduleMessage('workScheduleExceptionMessage', '');
}

function editWorkScheduleException(id) {
  const item = workScheduleExceptions.find((entry) => Number(entry.id) === Number(id));
  if (!item || !isWorkScheduleAdmin()) return;
  document.getElementById('workScheduleExceptionId').value = item.id;
  document.getElementById('workScheduleExceptionDate').value = item.exception_date;
  document.getElementById('workScheduleExceptionName').value = item.holiday_name;
  document.getElementById('workScheduleExceptionNote').value = item.note || '';
  document.getElementById('saveWorkScheduleExceptionBtn').textContent = 'Lưu thay đổi';
  document.getElementById('cancelWorkScheduleExceptionBtn').hidden = false;
  setWorkScheduleMessage('workScheduleExceptionMessage', 'Đang sửa ngày nghỉ đã chọn.');
}

async function saveWorkScheduleException() {
  if (!isWorkScheduleAdmin()) return;
  const id = document.getElementById('workScheduleExceptionId').value;
  const payload = {
    exception_date: document.getElementById('workScheduleExceptionDate').value,
    exception_type: 'off',
    holiday_name: document.getElementById('workScheduleExceptionName').value.trim(),
    note: document.getElementById('workScheduleExceptionNote').value.trim() || null,
  };
  try {
    const result = await api(id ? `/api/work-schedule/exceptions/${id}` : '/api/work-schedule/exceptions', {
      method: id ? 'PUT' : 'POST', body: JSON.stringify(payload),
    });
    resetWorkScheduleExceptionForm();
    setWorkScheduleMessage('workScheduleExceptionMessage', `Đã lưu ngày nghỉ. Đã tính lại ${result.attendance_recalculated || 0} bản ghi.`);
    await loadWorkSchedulePage();
  } catch (error) {
    setWorkScheduleMessage('workScheduleExceptionMessage', `Không lưu được: ${apiErrorMessage(error.message)}`, true);
  }
}

async function deleteWorkScheduleException(id) {
  const item = workScheduleExceptions.find((entry) => Number(entry.id) === Number(id));
  if (!item || !isWorkScheduleAdmin()) return;
  if (!window.confirm(`Xóa ngày nghỉ “${item.holiday_name}” (${workScheduleDateText(item.exception_date)})?`)) return;
  try {
    const result = await api(`/api/work-schedule/exceptions/${id}`, { method: 'DELETE' });
    resetWorkScheduleExceptionForm();
    setWorkScheduleMessage('workScheduleExceptionMessage', `Đã xóa ngày nghỉ. Đã tính lại ${result.attendance_recalculated || 0} bản ghi.`);
    await loadWorkSchedulePage();
  } catch (error) {
    setWorkScheduleMessage('workScheduleExceptionMessage', `Không xóa được: ${apiErrorMessage(error.message)}`, true);
  }
}

async function moveWorkScheduleMonth(delta) {
  const next = new Date(workScheduleYear, workScheduleMonth - 1 + delta, 1);
  workScheduleYear = next.getFullYear();
  workScheduleMonth = next.getMonth() + 1;
  try {
    renderWorkScheduleCalendar(await api(`/api/work-schedule/calendar?year=${workScheduleYear}&month=${workScheduleMonth}`));
  } catch (error) {
    setWorkScheduleMessage('workScheduleMessage', `Không tải được lịch tháng: ${error.message}`, true);
  }
}
