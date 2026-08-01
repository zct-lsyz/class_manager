"""
覆盖 zh-hans 的日期输入格式。

原因：zh-hans 默认 DATE_INPUT_FORMATS 第一位是 "%Y/%m/%d"（斜杠），
而 HTML5 <input type="date"> 只接受 ISO 横杠格式 "%Y-%m-%d"。
当浏览器提交日期时也是 ISO 格式，因此将 ISO 放到第一位，
编辑表单时已存日期才能正确回显到日期选择框。
"""

DATE_INPUT_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y年%m月%d日",
]
