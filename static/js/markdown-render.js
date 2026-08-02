/**
 * 自动将 class="ai-markdown" 的元素内容渲染为 Markdown。
 * 依赖：marked（markdown → HTML）+ DOMPurify（XSS 消毒），通过模板 CDN 引入。
 * 使用 textContent 取原始文本，避免服务端 HTML 注入；再经 DOMPurify 消毒后写入。
 */
(function () {
    function renderAll() {
        document.querySelectorAll('.ai-markdown').forEach(function (el) {
            if (el.dataset.mdRendered) return;
            if (typeof marked === 'undefined') return;
            var raw = el.textContent;
            var html = marked.parse(raw);
            if (window.DOMPurify) {
                html = DOMPurify.sanitize(html);
            }
            el.innerHTML = html;
            el.dataset.mdRendered = '1';
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderAll);
    } else {
        renderAll();
    }
})();
