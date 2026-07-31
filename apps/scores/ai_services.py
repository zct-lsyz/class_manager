"""
AI 分析服务：调用 OpenAI 兼容 Chat Completions API（DeepSeek 等）
"""
import json
import os
import time
import urllib.request
import urllib.error
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


class AIAnalysisError(Exception):
    pass


def get_effective_api_key(config):
    """获取有效的 API Key（环境变量优先，其次数据库配置）"""
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    return config.get_api_key() if config else ""


def call_chat_completion(base_url, api_key, model, messages, temperature=0.5, timeout=120):
    """
    调用 OpenAI 兼容 Chat Completions API
    base_url: 如 https://api.deepseek.com
    返回: (文本内容, 耗时ms)
    """
    if not api_key:
        raise AIAnalysisError("未配置 API Key，请先在「AI 分析设置」中填写。")

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            duration = int((time.time() - start) * 1000)
            result = json.loads(body)
            content = result["choices"][0]["message"]["content"].strip()
            return content, duration
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise AIAnalysisError(f"API 请求失败 (HTTP {exc.code}): {err_body}")
    except urllib.error.URLError as exc:
        raise AIAnalysisError(f"无法连接 API 服务: {exc.reason}")
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise AIAnalysisError(f"API 响应解析失败: {exc}")
    except Exception as exc:
        raise AIAnalysisError(f"请求异常: {exc}")


def generate_subject_analysis(config, subject_name, data_context):
    """
    生成单科分析
    data_context: dict，包含统计信息（dict 会被转成 JSON 注入提示词）
    """
    prompts = config.prompts or {}
    prompt = prompts.get(subject_name, "")
    if not prompt:
        from apps.scores.ai_prompts import DEFAULT_PROMPTS
        prompt = DEFAULT_PROMPTS.get(subject_name, "请分析以下成绩数据。")

    messages = [
        {"role": "system", "content": "你是一位严谨、专业的中学班主任，擅长班级成绩分析和教学诊断。"},
        {"role": "user", "content": f"{prompt}\n\n成绩数据如下：\n{json.dumps(data_context, ensure_ascii=False, indent=2)}"},
    ]
    api_key = get_effective_api_key(config)
    content, duration = call_chat_completion(
        config.base_url, api_key, config.model_name, messages, config.temperature,
    )
    return content, duration, prompt


def generate_comprehensive_analysis(config, data_context):
    """生成全科综合分析"""
    from apps.scores.ai_prompts import COMPREHENSIVE_PROMPT
    messages = [
        {"role": "system", "content": "你是一位严谨、专业的中学班主任，擅长班级成绩分析和班级管理。"},
        {"role": "user", "content": f"{COMPREHENSIVE_PROMPT}\n\n班级成绩数据如下：\n{json.dumps(data_context, ensure_ascii=False, indent=2)}"},
    ]
    api_key = get_effective_api_key(config)
    content, duration = call_chat_completion(
        config.base_url, api_key, config.model_name, messages, config.temperature,
    )
    return content, duration, COMPREHENSIVE_PROMPT


def generate_student_analysis(config, data_context):
    """生成学生个人分析"""
    from apps.scores.ai_prompts import STUDENT_PROMPT
    messages = [
        {"role": "system", "content": "你是一位关心学生、善于激励的中学班主任。"},
        {"role": "user", "content": f"{STUDENT_PROMPT}\n\n学生历次成绩数据如下：\n{json.dumps(data_context, ensure_ascii=False, indent=2)}"},
    ]
    api_key = get_effective_api_key(config)
    content, duration = call_chat_completion(
        config.base_url, api_key, config.model_name, messages, config.temperature,
    )
    return content, duration, STUDENT_PROMPT
