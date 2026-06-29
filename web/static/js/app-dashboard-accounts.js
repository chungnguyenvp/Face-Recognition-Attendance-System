async function loadDashboard() {
  const data = await api('/api/dashboard');
  const s = data.stats;
  const adminOnlyItems = canManageSystemSettings()
    ? [
        ['Chưa đăng ký', s.not_registered],
        ['Cảnh báo hôm nay', s.alerts_today],
      ]
    : [];
  const items = [
    ['Tổng sinh viên', s.total_students],
    ['Đã đăng ký khuôn mặt', s.face_registered],
    ['Sinh viên active', s.active_students],
    ['Check-in hôm nay', s.checkin_today],
    ['Check-out hôm nay', s.checkout_today],
    ['Đúng giờ hôm nay', s.on_time_today],
    ['Đi muộn hôm nay', s.late_today],
    ['Thiếu check-out', s.missing_checkout_today],
    ...adminOnlyItems,
    ['Trạng thái camera', 'Sẵn sàng'],
  ];
  document.getElementById('statsGrid').innerHTML = items
    .map((i) => `<div class="stat-card"><div class="label">${i[0]}</div><div class="value">${i[1]}</div></div>`)
    .join('');
  document.getElementById('recentLogs').innerHTML =
    data.recent_logs.map((l) => `<tr><td>${escapeHtml(l.created_at)}</td><td>${escapeHtml(l.full_name || 'Unknown')}</td><td>${escapeHtml(actionLabel(l.action))}</td><td>${resultBadge(l.result, l)}</td></tr>`).join('') ||
    '<tr><td colspan="4">Chưa có lịch sử</td></tr>';
  const notice = document.getElementById('quickNotice');
  if (notice) {
    notice.textContent = canManageSystemSettings()
      ? 'Admin có thể cấu hình hệ thống và xử lý dữ liệu vận hành.'
      : 'Lab Manager đang ở chế độ vận hành: camera, sinh viên, điểm danh và cảnh báo.';
  }
  await loadSettings(false);
}

function renderAccountRoleHint() {
  const hint = document.getElementById('accountRoleHint');
  if (!hint || !currentUser) return;
  hint.textContent = isAdmin()
    ? 'Admin có thể tạo student và lab manager. Tài khoản admin được bảo vệ: không khóa/xóa trực tiếp trên giao diện.'
    : 'Lab Manager chỉ tạo và quản lý tài khoản student; không thấy và không sửa tài khoản quản trị.';
}

function renderAccountRoleOptions() {
  const select = document.getElementById('accountRole');
  if (!select) return;
  const roles = isAdmin()
    ? [
        ['student', 'student - Sinh viên'],
        ['lab_manager', 'lab_manager - Quản lý phòng lab'],
      ]
    : [['student', 'student - Sinh viên']];
  select.innerHTML = roles.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
  select.disabled = isLabManager();
  toggleAccountStudentSelect();
}

function toggleAccountStudentSelect() {
  const role = document.getElementById('accountRole')?.value;
  const box = document.getElementById('accountStudentBox');
  if (box) box.style.display = role === 'student' ? 'block' : 'none';
}

async function loadAccountStudents() {
  const select = document.getElementById('accountStudentId');
  if (!select) return;
  const data = await api('/api/students');
  select.innerHTML = data.items.length
    ? data.items.map((student) => `<option value="${student.id}">${escapeHtml(student.student_code)} - ${escapeHtml(student.full_name)}</option>`).join('')
    : '<option value="">Chưa có sinh viên active</option>';
}

function accountStatusLabel(status) {
  if (status === 'active') return 'Đang hoạt động';
  if (status === 'inactive') return 'Đã khóa';
  return status || '-';
}

function renderAccountActions(user) {
  if (!canEditUserAccount(user)) return '<span class="muted">Không có quyền</span>';
  const actions = [];
  if (canLockUserAccount(user)) {
    const nextStatus = user.status === 'active' ? 'inactive' : 'active';
    const label = user.status === 'active' ? 'Khóa' : 'Mở';
    actions.push(`<button class="secondary" title="Khóa sẽ chặn tài khoản này đăng nhập, dữ liệu vẫn được giữ nguyên." onclick="toggleAccountStatus(${user.id}, '${nextStatus}')">${label}</button>`);
  }
  actions.push(`<button class="secondary" onclick="resetAccountPassword(${user.id})">Đặt mật khẩu</button>`);
  if (canDeleteUserAccount(user)) {
    actions.push(`<button class="danger-lite" onclick="deleteAccountUser(${user.id})">Xóa</button>`);
  }
  return `<div class="account-row-actions">${actions.join('')}</div>`;
}

async function loadAccountUsers() {
  const body = document.getElementById('accountRows');
  if (!body) return;
  const data = await api('/api/users');
  body.innerHTML = data.items.length ? data.items.map((user) => {
    const linkedStudent = user.student_code ? `${user.student_code} - ${user.full_name || ''}` : '-';
    return `<tr>
      <td>${escapeHtml(user.id)}</td>
      <td><strong>${escapeHtml(user.username)}</strong>${Number(user.id) === Number(currentUser?.id) ? '<span class="table-subtext">Bạn đang đăng nhập</span>' : ''}</td>
      <td><span class="role-pill">${escapeHtml(roleLabel(user.role))}</span></td>
      <td>${escapeHtml(linkedStudent)}</td>
      <td><span class="account-status account-status-${escapeHtml(user.status)}">${escapeHtml(accountStatusLabel(user.status))}</span></td>
      <td>${escapeHtml(user.created_at || '-')}</td>
      <td>${renderAccountActions(user)}</td>
    </tr>`;
  }).join('') : '<tr><td colspan="7">Chưa có tài khoản.</td></tr>';
}

async function loadAccountsPage() {
  renderAccountRoleHint();
  renderAccountRoleOptions();
  await loadAccountStudents();
  await loadAccountUsers();
}

function setAccountMessage(text) {
  const msg = document.getElementById('accountMessage');
  if (msg) msg.textContent = text || '';
}

async function createAccountUser() {
  const role = document.getElementById('accountRole')?.value || 'student';
  const payload = {
    username: document.getElementById('accountUsername')?.value.trim() || '',
    password: document.getElementById('accountPassword')?.value || '',
    role,
    student_id: role === 'student' ? Number(document.getElementById('accountStudentId')?.value || 0) : null,
  };
  setAccountMessage('');
  try {
    await api('/api/users', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('accountPassword').value = '';
    setAccountMessage('Đã tạo tài khoản.');
    await loadAccountUsers();
  } catch (e) {
    setAccountMessage(e.message);
  }
}

async function toggleAccountStatus(id, status) {
  await api(`/api/users/${id}`, { method: 'PUT', body: JSON.stringify({ status }) });
  await loadAccountUsers();
}

async function resetAccountPassword(id) {
  const password = prompt('Nhập mật khẩu mới, tối thiểu 6 ký tự:');
  if (!password) return;
  try {
    await api(`/api/users/${id}`, { method: 'PUT', body: JSON.stringify({ password }) });
    setAccountMessage('Đã đặt lại mật khẩu.');
  } catch (e) {
    setAccountMessage(e.message);
  }
}

async function deleteAccountUser(id) {
  if (!confirm('Xóa tài khoản này? Hồ sơ sinh viên và lịch sử ra/vào không bị xóa.')) return;
  await api(`/api/users/${id}`, { method: 'DELETE' });
  await loadAccountUsers();
}

