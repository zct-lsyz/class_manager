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
    var usablePageHeight = pageHeight - margin * 2;

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
        scrollY: 0,
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
            // 解除表格横向滚动容器的裁切，避免宽表格（如班级总成绩表）右侧列被截断
            doc.querySelectorAll('.table-responsive').forEach(function (el) {
                el.style.overflow = 'visible';
            });
        },
    }).then(function (canvas) {
        var imgData = canvas.toDataURL('image/jpeg', 0.92);
        // 内容在 PDF 中的总高度（按宽度等比换算成 mm）
        var imgHeight = canvas.height * contentWidth / canvas.width;
        var titleHeight = opts.title ? 14 : 0;   // 标题占用的顶部空间（mm）

        var pdf = new window.jspdf.jsPDF({
            orientation: isLandscape ? 'l' : 'p',
            unit: 'mm',
            format: 'a4',
        });

        if (opts.title) {
            pdf.setFontSize(14);
            pdf.setFont('helvetica', 'bold');
            pdf.text(opts.title, pageWidth / 2, margin + 5, { align: 'center' });
        }

        // 第 1 页：标题之后开始内容，可见内容 [0, firstPageContent]
        var firstPageContent = usablePageHeight - titleHeight;
        pdf.addImage(imgData, 'JPEG', margin, margin + titleHeight, contentWidth, imgHeight);
        var drawn = firstPageContent;

        // 后续页：每页把图片整体上移「已绘制高度」，从而显示下一段内容
        var pageIndex = 0;
        while (drawn < imgHeight) {
            pageIndex += 1;
            pdf.addPage();
            pdf.addImage(imgData, 'JPEG', margin, margin - drawn, contentWidth, imgHeight);
            drawn += usablePageHeight;
        }

        pdf.save(opts.filename);
        restoreBtn();
    }).catch(function (err) {
        console.error('PDF 导出失败:', err);
        alert('PDF 导出失败：' + err);
        restoreBtn();
    });
}
