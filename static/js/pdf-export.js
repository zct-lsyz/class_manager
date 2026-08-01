/**
 * 页面内容一键导出 PDF（html2canvas + jsPDF）
 * 依赖全局: html2canvas, window.jspdf（在模板中通过 CDN 引入）
 */
function exportPageToPdf(options) {
    var opts = Object.assign({
        containerId: null,
        buttonId: null,
        filename: 'export.pdf',
        title: '',
        orientation: 'portrait',   // portrait | landscape
        scale: 2,
    }, options || {});

    var container = document.getElementById(opts.containerId);
    if (!container) {
        alert('未找到可导出的内容区域。');
        return;
    }
    var btn = opts.buttonId ? document.getElementById(opts.buttonId) : null;
    var originalHtml = btn ? btn.innerHTML : '';
    var originalDisabled = btn ? btn.disabled : false;

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>生成中...';
    }

    var isLandscape = opts.orientation === 'landscape';
    var pageWidth = isLandscape ? 297 : 210;   // mm
    var pageHeight = isLandscape ? 210 : 297;  // mm
    var margin = 8;
    var contentWidth = pageWidth - margin * 2;

    function restoreBtn() {
        if (btn) {
            btn.disabled = originalDisabled;
            btn.innerHTML = originalHtml;
        }
    }

    html2canvas(container, {
        scale: opts.scale,
        useCORS: true,
        backgroundColor: '#ffffff',
        logging: false,
        scrollX: 0,
        scrollY: -window.scrollY,
        windowWidth: container.scrollWidth,
        onclone: function (doc) {
            // 隐藏所有标注为 no-export 的元素（筛选表单、工具栏、按钮、折叠面板等）
            doc.querySelectorAll('.no-export').forEach(function (el) {
                el.style.display = 'none';
            });
            // 强制展开 Bootstrap 折叠区域（如默认收起的班级总成绩表）。
            // 跳过 no-export 与移动端菜单，避免覆盖上面的隐藏逻辑。
            doc.querySelectorAll('[id].collapse').forEach(function (el) {
                if (el.classList.contains('no-export')) return;
                if (el.id === 'mobileMenu') return;
                el.classList.remove('collapse');
                el.style.display = '';
                el.style.height = 'auto';
            });
        },
    }).then(function (canvas) {
        var imgData = canvas.toDataURL('image/jpeg', 0.95);
        var imgHeight = canvas.height * contentWidth / canvas.width;
        var usablePageHeight = pageHeight - margin * 2;

        var pdf = new window.jspdf.jsPDF({
            orientation: isLandscape ? 'l' : 'p',
            unit: 'mm',
            format: 'a4',
        });

        var pageIndex = 0;
        if (opts.title) {
            pdf.setFontSize(13);
            pdf.text(opts.title, pageWidth / 2, margin + 4, { align: 'center' });
            pageIndex = 1; // 标题占首行，从第二行开始内容偏移（简单起见直接叠印）
        }

        // 整图分页：通过负偏移让每页显示对应切片（addImage 自动裁剪页外内容）
        var yOffset = margin - usablePageHeight * pageIndex;
        pdf.addImage(imgData, 'JPEG', margin, yOffset, contentWidth, imgHeight);

        var remaining = imgHeight - usablePageHeight * (pageIndex + 1);
        while (remaining > 0) {
            pageIndex += 1;
            pdf.addPage();
            pdf.addImage(imgData, 'JPEG', margin, margin - usablePageHeight * pageIndex, contentWidth, imgHeight);
            remaining -= usablePageHeight;
        }

        pdf.save(opts.filename);
        restoreBtn();
    }).catch(function (err) {
        console.error('PDF 导出失败:', err);
        alert('PDF 导出失败：' + err);
        restoreBtn();
    });
}
