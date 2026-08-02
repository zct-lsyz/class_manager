/**
 * 通用「下拉选择学生 → 已选中[姓名❌]标签」多选组件
 *
 * 用法：
 *   initStudentChipSelect({
 *     pickerId: 'studentPicker',      // 下拉 select 元素 id
 *     chipsId: 'selectedStudents',    // 已选标签容器 id
 *     modeId: 'studentMode',          // 隐藏 student_mode 输入 id
 *     studentsName: 'students',       // 隐藏 students[] 输入的名字
 *     roomSelectId: null,             // 可选：宿舍下拉 id；提供则学生列表随宿舍联动
 *     studentsByRoom: {},             // 可选：{roomId: [{id, name}]}
 *     staticStudents: [],             // 可选：静态学生列表 [{id, name}]
 *     initialSelected: [],            // 可选：编辑时已选学生 [{id, name}]（不含 all）
 *     allLabel: '全体学生（同步给每名学生）',  // 可选：提供则含"全体"选项
 *   });
 */
function initStudentChipSelect(opts) {
    const picker = document.getElementById(opts.pickerId);
    const chipsBox = document.getElementById(opts.chipsId);
    const modeInput = document.getElementById(opts.modeId);
    if (!picker || !chipsBox || !modeInput) return;

    // 当前已选学生 id 集合（有序）
    let selected = [];

    function clearChips() {
        chipsBox.innerHTML = '';
        chipsBox.querySelectorAll('input[type=hidden]').forEach(function (h) { h.remove(); });
        selected = [];
    }

    function addChip(id, label, isAll) {
        if (selected.includes(id)) return;
        if (isAll) {
            // 全体：清掉所有单个学生
            selected = [id];
            chipsBox.querySelectorAll('input[type=hidden]').forEach(function (h) { h.remove(); });
        }
        selected.push(id);
        const span = document.createElement('span');
        span.className = 'badge bg-light border text-dark d-inline-flex align-items-center gap-1 px-2 py-1 mb-1 me-1';
        span.textContent = label;
        const x = document.createElement('button');
        x.type = 'button';
        x.className = 'btn btn-sm btn-outline-danger border-0 p-0 ms-1 fw-bold';
        x.textContent = '✕';
        x.setAttribute('aria-label', '取消选中');
        x.addEventListener('click', function () {
            span.remove();
            selected = selected.filter(function (s) { return s !== id; });
            if (isAll) {
                // 移除全体后重新计算模式
                modeInput.value = selected.length ? 'selected' : 'one';
            } else {
                modeInput.value = selected.length ? 'selected' : 'one';
            }
            // 重建隐藏输入
            rebuildHidden();
        });
        span.appendChild(x);
        chipsBox.appendChild(span);
        rebuildHidden();
    }

    function rebuildHidden() {
        chipsBox.querySelectorAll('input[type=hidden]').forEach(function (h) { h.remove(); });
        selected.forEach(function (id) {
            const hid = document.createElement('input');
            hid.type = 'hidden';
            hid.name = opts.studentsName || 'students';
            hid.value = id;
            chipsBox.appendChild(hid);
        });
        modeInput.value = selected.includes('all') ? 'all' : (selected.length ? 'selected' : 'one');
    }

    function populatePicker(students) {
        picker.innerHTML = '<option value="">— 请选择学生 —</option>';
        if (opts.allLabel) {
            const allOpt = document.createElement('option');
            allOpt.value = 'all';
            allOpt.textContent = opts.allLabel;
            picker.appendChild(allOpt);
        }
        students.forEach(function (s) {
            const opt = document.createElement('option');
            opt.value = String(s.id);
            opt.textContent = s.name;
            picker.appendChild(opt);
        });
        if (!students.length && opts.allLabel) {
            const emptyOpt = document.createElement('option');
            emptyOpt.value = '';
            emptyOpt.textContent = '该宿舍暂无分配学生';
            emptyOpt.disabled = true;
            picker.appendChild(emptyOpt);
        }
    }

    picker.addEventListener('change', function () {
        const val = picker.value;
        if (!val) return;
        const label = picker.options[picker.selectedIndex].textContent;
        if (val === 'all') {
            addChip('all', label, true);
        } else {
            addChip(val, label, false);
        }
        picker.value = '';
    });

    // 宿舍联动：切换宿舍时重建学生列表并清空已选
    if (opts.roomSelectId) {
        const roomSel = document.getElementById(opts.roomSelectId);
        if (roomSel) {
            roomSel.addEventListener('change', function () {
                const students = (opts.studentsByRoom || {})[roomSel.value] || [];
                populatePicker(students);
                clearChips();
                modeInput.value = 'one';
            });
            if (roomSel.value) {
                populatePicker((opts.studentsByRoom || {})[roomSel.value] || []);
            }
        }
    } else if (opts.staticStudents) {
        populatePicker(opts.staticStudents);
    }

    // 编辑回显：初始已选学生渲染为标签
    (opts.initialSelected || []).forEach(function (s) {
        addChip(String(s.id), s.name, false);
    });
}
