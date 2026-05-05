import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import settings


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


def _route_for_task(task_type: str) -> List[ProviderConfig]:
    db_route = _db_route_for_task(task_type)
    if db_route is not None:
        return db_route

    configs = _provider_configs()
    route = settings.AI_TASK_ROUTES.get(task_type) or settings.AI_TASK_ROUTES.get("default") or []
    names = [name.strip() for name in route if name.strip()]
    if settings.AI_DEFAULT_PROVIDER and settings.AI_DEFAULT_PROVIDER not in names:
        names.insert(0, settings.AI_DEFAULT_PROVIDER)
    names.extend(["sensenova", "zhipu", "deepseek", "qwen", "doubao", "openai", "legacy"])

    result = []
    seen = set()
    for name in names:
        if name in configs and name not in seen:
            seen.add(name)
            result.append(configs[name])
    return result


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
                    chunks = []
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
            continue

    if last_error:
        raise last_error
    raise RuntimeError("No AI provider configured")


async def generate_tags(content: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    if not content.strip():
        return [], None, None

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
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()][:5], provider, model
    return [], provider, model


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

    data, provider, model = await _chat_json(
        "material_analysis",
        [{"role": "user", "content": prompt}],
        temperature=0.35,
    )
    if not isinstance(data, dict):
        raise ValueError("AI analysis response is not an object")

    return data, provider, model
