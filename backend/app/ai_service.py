import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from .config import settings
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str
    timeout: int = 30
    endpoint_path: str = "/chat/completions"


def _clean_json_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()
    return text


def _parse_json(text: str) -> Any:
    text = _clean_json_text(text)
    try:
        return json.loads(text)
    except Exception:
        start = min([idx for idx in [text.find("{"), text.find("[")] if idx != -1], default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _provider_configs() -> Dict[str, ProviderConfig]:
    configs = {
        "sensenova": ProviderConfig(
            "sensenova",
            settings.SENSENOVA_API_KEY,
            settings.SENSENOVA_BASE_URL,
            settings.SENSENOVA_TEXT_MODEL,
        ),
        "zhipu": ProviderConfig("zhipu", settings.ZHIPU_API_KEY, settings.ZHIPU_BASE_URL, settings.ZHIPU_MODEL),
        "openai": ProviderConfig("openai", settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL, settings.OPENAI_MODEL),
        "deepseek": ProviderConfig("deepseek", settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_BASE_URL, settings.DEEPSEEK_MODEL),
        "qwen": ProviderConfig("qwen", settings.QWEN_API_KEY, settings.QWEN_BASE_URL, settings.QWEN_MODEL),
        "doubao": ProviderConfig("doubao", settings.DOUBAO_API_KEY, settings.DOUBAO_BASE_URL, settings.DOUBAO_MODEL),
        "legacy": ProviderConfig("legacy", settings.AI_API_KEY, settings.AI_API_BASE_URL, settings.AI_MODEL),
    }
    return {name: cfg for name, cfg in configs.items() if cfg.api_key and cfg.base_url and cfg.model}


def _db_route_for_task(task_type: str) -> Optional[List[ProviderConfig]]:
    try:
        from .database import SessionLocal
        from .models import AIProvider, AIModel, AITaskRoute
    except Exception:
        return None

    db = SessionLocal()
    try:
        has_routes = db.query(AITaskRoute).filter(AITaskRoute.task_type == task_type).first()
        if not has_routes:
            return None

        rows = db.query(AITaskRoute, AIProvider, AIModel).join(
            AIProvider, AITaskRoute.provider_id == AIProvider.id
        ).join(
            AIModel, AITaskRoute.model_id == AIModel.id
        ).filter(
            AITaskRoute.task_type == task_type,
            AITaskRoute.enabled == 1,
            AIProvider.enabled == 1,
            AIModel.enabled == 1,
            AIProvider.api_key.isnot(None),
            AIProvider.api_key != "",
        ).order_by(AITaskRoute.route_order.asc()).all()

        return [
            ProviderConfig(
                name=provider.provider_key,
                api_key=provider.api_key,
                base_url=provider.base_url,
                model=model.model_key,
                timeout=route.timeout_seconds or settings.AI_REQUEST_TIMEOUT,
                endpoint_path=model.endpoint_path or "/chat/completions",
            )
            for route, provider, model in rows
        ]
    except Exception:
        return None
    finally:
        db.close()


def _db_config_for_model(model_key: str) -> Optional[ProviderConfig]:
    try:
        from .database import SessionLocal
        from .models import AIProvider, AIModel
    except Exception:
        return None

    db = SessionLocal()
    try:
        row = db.query(AIProvider, AIModel).join(
            AIModel, AIModel.provider_id == AIProvider.id
        ).filter(
            AIModel.model_key == model_key,
            AIProvider.enabled == 1,
            AIModel.enabled == 1,
            AIProvider.api_key.isnot(None),
            AIProvider.api_key != "",
        ).order_by(AIProvider.is_default.desc(), AIModel.priority.asc()).first()
        if not row:
            return None
        provider, model = row
        return ProviderConfig(
            name=provider.provider_key,
            api_key=provider.api_key,
            base_url=provider.base_url,
            model=model.model_key,
            timeout=settings.AI_REQUEST_TIMEOUT,
            endpoint_path=model.endpoint_path or "/chat/completions",
        )
    except Exception:
        return None
    finally:
        db.close()


def _route_for_task(task_type: str, preferred_model: Optional[str] = None) -> List[ProviderConfig]:
    db_route = _db_route_for_task(task_type)
    if db_route:
        route = db_route
    else:
        if db_route is not None:
            logger.warning(
                f"任务 {task_type} 在数据库配置了路由，但没有一条可用"
                f"（供应商被禁用或未填 API Key），回退到 .env 路由"
            )
        configs = _provider_configs()
        route_setting = settings.AI_TASK_ROUTES.get(task_type) or settings.AI_TASK_ROUTES.get("default") or []
        names = [name.strip() for name in route_setting if name.strip()]
        if settings.AI_DEFAULT_PROVIDER and settings.AI_DEFAULT_PROVIDER not in names:
            names.insert(0, settings.AI_DEFAULT_PROVIDER)
        names.extend(["sensenova", "zhipu", "deepseek", "qwen", "doubao", "openai", "legacy"])

        route = []
        seen = set()
        for name in names:
            if name in configs and name not in seen:
                seen.add(name)
                route.append(configs[name])

    if preferred_model:
        preferred_config = _db_config_for_model(preferred_model)
        if preferred_config:
            route = [preferred_config] + [item for item in route if item.model != preferred_config.model]
        preferred = [item for item in route if item.model == preferred_model]
        fallback = [item for item in route if item.model != preferred_model]
        return preferred + fallback
    return route


def _write_call_log(task_type: str, provider: Optional[ProviderConfig], status: str, latency_ms: Optional[int], error: Optional[str]):
    try:
        from .database import SessionLocal
        from .models import AICallLog
    except Exception:
        return

    db = SessionLocal()
    try:
        db.add(AICallLog(
            id=str(uuid.uuid4()),
            task_type=task_type,
            provider_key=provider.name if provider else None,
            model_key=provider.model if provider else None,
            status=status,
            latency_ms=latency_ms,
            error_message=error[:1000] if error else None,
        ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def _chat_json(task_type: str, messages: List[Dict[str, str]], temperature: float = 0.3) -> Tuple[Any, str, str]:
    last_error: Optional[Exception] = None
    for provider in _route_for_task(task_type):
        started = time.perf_counter()
        chunks: List[str] = []
        try:
            async with httpx.AsyncClient(timeout=provider.timeout or settings.AI_REQUEST_TIMEOUT, trust_env=False) as client:
                payload = {
                    "model": provider.model,
                    "messages": messages,
                    "temperature": temperature,
                }
                url = f"{provider.base_url.rstrip('/')}{provider.endpoint_path or '/chat/completions'}"
                headers = {"Authorization": f"Bearer {provider.api_key}"}

                if provider.name == "zhipu":
                    payload["stream"] = True
                    async with client.stream("POST", url, headers=headers, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data_line = line[5:].strip()
                            if not data_line or data_line == "[DONE]":
                                continue
                            data = json.loads(data_line)
                            delta = data["choices"][0].get("delta", {})
                            if delta.get("content"):
                                chunks.append(delta["content"])
                    text = "".join(chunks).strip()
                    if not text:
                        raise ValueError("Zhipu stream returned no content")
                else:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]

                _write_call_log(task_type, provider, "success", int((time.perf_counter() - started) * 1000), None)
                return _parse_json(text), provider.name, provider.model
        except Exception as exc:
            last_error = exc
            _write_call_log(task_type, provider, "failed", int((time.perf_counter() - started) * 1000), str(exc))
            if chunks:
                raise exc
            continue

    if last_error:
        raise last_error
    raise RuntimeError("No AI provider configured")


def _extract_stream_delta(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def _extract_message_content(message: Dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return ""


def _empty_response_detail(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return "AI provider returned no choices"
    choice = choices[0] or {}
    finish_reason = choice.get("finish_reason") or choice.get("finishReason")
    message = choice.get("message") or {}
    refusal = message.get("refusal") or message.get("reasoning_content") or message.get("reasoningContent")
    if refusal:
        return f"AI provider returned no answer content: {refusal}"
    if finish_reason:
        return f"AI provider returned no answer content, finish_reason={finish_reason}"
    return "AI provider returned empty answer content"


async def _stream_provider(
    provider: ProviderConfig,
    messages: List[Dict[str, str]],
    temperature: float,
) -> AsyncIterator[str]:
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    url = f"{provider.base_url.rstrip('/')}{provider.endpoint_path or '/chat/completions'}"
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    async with httpx.AsyncClient(timeout=provider.timeout or settings.AI_REQUEST_TIMEOUT, trust_env=False) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                data = json.loads(line)
                delta = _extract_stream_delta(data)
                if delta:
                    yield delta


async def _complete_provider(
    provider: ProviderConfig,
    messages: List[Dict[str, str]],
    temperature: float,
) -> str:
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature,
    }
    url = f"{provider.base_url.rstrip('/')}{provider.endpoint_path or '/chat/completions'}"
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    async with httpx.AsyncClient(timeout=provider.timeout or settings.AI_REQUEST_TIMEOUT, trust_env=False) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError(_empty_response_detail(data))
        message = choices[0].get("message") or {}
        content = _extract_message_content(message).strip()
        if not content:
            raise ValueError(_empty_response_detail(data))
        return content


async def chat_completion_stream(
    messages: List[Dict[str, str]],
    task_type: str = "chat_completion",
    temperature: float = 0.7,
    preferred_model: Optional[str] = None,
) -> AsyncIterator[str]:
    """Stream an OpenAI-compatible chat completion through the configured route."""
    last_error: Optional[Exception] = None
    for provider in _route_for_task(task_type, preferred_model=preferred_model):
        started = time.perf_counter()
        chunks: List[str] = []
        try:
            logger.info(f"AI调用开始: provider={provider.name}, model={provider.model}, task={task_type}")
            if provider.name == "zhipu":
                async for chunk in _stream_provider(provider, messages, temperature):
                    chunks.append(chunk)
                    yield chunk
            else:
                text = await _complete_provider(provider, messages, temperature)
                chunks.append(text)
                yield text
            if not chunks:
                raise ValueError("AI provider returned empty stream")
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.info(f"AI调用成功: provider={provider.name}, model={provider.model}, 耗时={elapsed}ms")
            _write_call_log(task_type, provider, "success", elapsed, None)
            return
        except Exception as exc:
            last_error = exc
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.error(f"AI调用失败: provider={provider.name}, model={provider.model}, error={exc}, 耗时={elapsed}ms")
            _write_call_log(task_type, provider, "failed", elapsed, str(exc))
            if chunks:
                raise exc
            fallback_started = time.perf_counter()
            try:
                logger.info(f"AI降级: provider={provider.name} 失败, 尝试降级调用")
                text = await _complete_provider(provider, messages, temperature)
                yield text
                fallback_elapsed = int((time.perf_counter() - fallback_started) * 1000)
                logger.info(f"AI降级成功: provider={provider.name}, 耗时={fallback_elapsed}ms")
                _write_call_log(task_type, provider, "success", fallback_elapsed, None)
                return
            except Exception as fallback_exc:
                last_error = fallback_exc
                fallback_elapsed = int((time.perf_counter() - fallback_started) * 1000)
                logger.error(f"AI降级失败: provider={provider.name}, error={fallback_exc}, 耗时={fallback_elapsed}ms")
                _write_call_log(task_type, provider, "failed", fallback_elapsed, str(fallback_exc))
            continue

    if last_error:
        raise last_error
    raise RuntimeError("No AI provider configured")


async def chat_completion(
    messages: List[Dict[str, str]],
    task_type: str = "chat_completion",
    temperature: float = 0.7,
    preferred_model: Optional[str] = None,
) -> str:
    chunks = []
    async for chunk in chat_completion_stream(
        messages,
        task_type=task_type,
        temperature=temperature,
        preferred_model=preferred_model,
    ):
        chunks.append(chunk)
    content = "".join(chunks).strip()
    if not content:
        raise ValueError("AI provider returned empty answer content")
    return content


async def generate_tags(content: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    if not content.strip():
        return [], None, None

    logger.info(f"AI生成标签开始: content_length={len(content)}")
    prompt = f"""
请为下面的素材生成 3-5 个中文标签。
要求：
1. 标签应覆盖主题、情绪、场景或写作用途。
2. 每个标签 2-6 个字。
3. 只返回 JSON 数组，不要解释。

素材：
{content[:1500]}
"""
    data, provider, model = await _chat_json(
        "tag_generation",
        [{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    tags = []
    if isinstance(data, list):
        tags = [str(item).strip() for item in data if str(item).strip()][:5]
    logger.info(f"AI生成标签完成: provider={provider}, model={model}, tags={tags}")
    return tags, provider, model


async def analyze_material(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
    selected_text = payload.get("material", {}).get("selected_text") or payload.get("material", {}).get("content") or ""
    if not selected_text.strip():
        raise ValueError("Material text is empty")

    prompt = f"""
你是一个中文阅读理解助手。请基于书籍信息、章节信息、选中的素材和前后文，帮助用户理解这条素材。

任务目标：
1. 说明这段话前后发生了什么。
2. 解释这段素材的核心含义。
3. 判断它和本书主题、章节主题的关系。
4. 推测用户可能为什么想保存它。
5. 给出可修改的个人感悟候选。
6. 给出写作用途和标签。

请严格返回 JSON 对象，字段如下：
{{
  "context_summary": "上下文摘要",
  "interpretation": "素材解读",
  "theme_analysis": "主题关联",
  "possible_feelings": ["可能感受1", "可能感受2", "可能感受3"],
  "personal_insight_candidates": ["感悟候选1", "感悟候选2", "感悟候选3"],
  "writing_topics": ["写作主题1", "写作主题2"],
  "tags": ["标签1", "标签2", "标签3"],
  "questions": ["可以追问用户的问题"]
}}

输入：
{json.dumps(payload, ensure_ascii=False)[:12000]}
"""

    logger.info(f"AI分析素材开始: material_id={payload.get('material', {}).get('id', 'unknown')}")
    data, provider, model = await _chat_json(
        "material_analysis",
        [{"role": "user", "content": prompt}],
        temperature=0.35,
    )
    if not isinstance(data, dict):
        raise ValueError("AI analysis response is not an object")

    logger.info(f"AI分析素材完成: provider={provider}, model={model}")
    return data, provider, model
