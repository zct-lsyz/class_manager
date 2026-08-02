/**
 * 「下拉列表内复选框多选学生」组件
 *
 * 交互：点击按钮展开下拉面板（最多约 10 行，可滚动），在列表内勾选多个学生，
 *       点「确认」一次性选中并收起面板。
 *
 * opts:
 *   buttonId    : 触发按钮 id（显示「选择学生」+ 已选数）
 *   panelId     : 下拉面板容器 id
 *   summaryId   : 已选显示区 id（确认后展示 ☑️学生A ☑️学生B）
 *   studentsName: 隐藏输入 name（默认 'students'）
 *   staticStudents: [{id,name}] 静态学生列表
 *   studentsByRoom: {roomId: [{id,name}]}（可选，宿舍联动）
 *   roomSelectId : 宿舍下拉 id（可选）
 *   allLabel     : 可选「全体学生」选项文本；提供则列表中首行含全体复选框
 *   initialSelected: [{id,name}] 编辑回显
 *   modeId       : 可选，student_mode 隐藏输入 id
 */
function initStudentCheckboxSelect(opts) {
    var btn = document.getElementById(opts.buttonId);
    var panel = document.getElementById(opts.panelId);
    var summary = opts.summaryId ? document.getElementById(opts.summaryId) : null;
    var studentsName = opts.studentsName || 'students';
    var modeInput = opts.modeId ? document.getElementById(opts.modeId) : null;
    if (!btn || !panel) return;

    var currentStudents = opts.staticStudents || [];
    var selected = new Set();
    var selectedNames = {};
    (opts.initialSelected || []).forEach(function (s) { selected.add(String(s.id)); selectedNames[String(s.id)] = s.name; });

    function renderList() {
        panel.innerHTML = '';
        var scroll = document.createElement('div');
        scroll.style.maxHeight = '260px'; // 约 10 行
        scroll.style.overflowY = 'auto';

        if (opts.allLabel) {
            var allWrap = document.createElement('div');
            allWrap.className = 'form-check';
            allWrap.innerHTML = '<input class="form-check-input scs-check-all" type="checkbox" value="all"><label class="form-check-label text-danger fw-bold">' + opts.allLabel + '</label>';
            var allCb = allWrap.querySelector('input');
            if (selected.has('all')) allCb.checked = true;
            scroll.appendChild(allWrap);
            var hr = document.createElement('hr');
            hr.className = 'my-1';
            scroll.appendChild(hr);
        }

        currentStudents.forEach(function (s) {
            var wrap = document.createElement('div');
            wrap.className = 'form-check';
            wrap.innerHTML = '<input class="form-check-input scs-check" type="checkbox" value="' + s.id + '"><label class="form-check-label">' + s.name + '</label>';
            var cb = wrap.querySelector('input');
            if (selected.has(String(s.id))) cb.checked = true;
            scroll.appendChild(wrap);
        });
        if (!currentStudents.length) {
            var empty = document.createElement('div');
            empty.className = 'text-muted small px-2';
            empty.textContent = '（无学生可选）';
            scroll.appendChild(empty);
        }
        panel.appendChild(scroll);

        var confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.className = 'btn btn-primary btn-sm w-100 mt-2';
        confirmBtn.textContent = '确认选择';
        confirmBtn.addEventListener('click', function () {
            applySelection();
            panel.classList.add('d-none');
        });
        panel.appendChild(confirmBtn);
    }

    function applySelection() {
        var checkAll = panel.querySelector('.scs-check-all');
        var checks = Array.from(panel.querySelectorAll('.scs-check'));
        selected.clear();
        selectedNames = {};
        if (checkAll && checkAll.checked) {
            selected.add('all');
            selectedNames['all'] = opts.allLabel || '全体学生';
        } else {
            checks.forEach(function (cb) {
                if (cb.checked) {
                    selected.add(cb.value);
                    // 从当前列表取姓名
                    var label = cb.parentElement.querySelector('.form-check-label');
                    if (label) selectedNames[cb.value] = label.textContent;
                }
            });
        }
        syncHidden();
        updateBtn();
        renderSummary();
    }

    function renderSummary() {
        if (!summary) return;
        summary.innerHTML = '';
        selected.forEach(function (id) {
            var name = selectedNames[id] || id;
            var wrap = document.createElement('label');
            wrap.className = 'form-check form-check-inline mb-0 me-2';
            wrap.innerHTML = '<input class="form-check-input" type="checkbox" checked disabled><span class="form-check-label">' + name + '</span>';
            summary.appendChild(wrap);
        });
    }

    function syncHidden() {
        // 移除旧隐藏输入（在表单内任意位置）
        document.querySelectorAll('input[name="' + studentsName + '"]').forEach(function (h) { h.remove(); });
        selected.forEach(function (id) {
            var hid = document.createElement('input');
            hid.type = 'hidden';
            hid.name = studentsName;
            hid.value = id;
            panel.appendChild(hid);
        });
        if (modeInput) {
            modeInput.value = selected.has('all') ? 'all' : (selected.size ? 'selected' : 'one');
        }
    }

    function updateBtn() {
        if (selected.has('all')) {
            btn.textContent = '选择学生（全体）';
        } else if (selected.size) {
            btn.textContent = '选择学生（已选 ' + selected.size + '）';
        } else {
            btn.textContent = '选择学生';
        }
    }

    // 宿舍联动
    if (opts.roomSelectId) {
        var roomSel = document.getElementById(opts.roomSelectId);
        if (roomSel) {
            roomSel.addEventListener('change', function () {
                currentStudents = (opts.studentsByRoom || {})[roomSel.value] || [];
                selected.clear();
                renderList();
                syncHidden();
                updateBtn();
            });
        }
    }

    btn.addEventListener('click', function () {
        if (panel.classList.contains('d-none')) {
            renderList();
            syncHidden();
            updateBtn();
            panel.classList.remove('d-none');
        } else {
            panel.classList.add('d-none');
        }
    });

    renderList();
    syncHidden();
    updateBtn();
    renderSummary();
}
