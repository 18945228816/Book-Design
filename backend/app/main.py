from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, EmailStr
from email_validator import validate_email, EmailNotValidError
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import List, Optional
import uuid
import os
import json
import time
import traceback
import httpx

from .database import engine, Base, get_db
from . import chat_models  # noqa: F401 - register chat tables on shared metadata
from .models import (
    User,
    Book,
    Chapter,
    Material,
    ReadingProgress,
    AIProvider,
    AIModel,
    AITaskRoute,
    AICallLog,
    EmailCode,
)
from .config import settings
from .chat_router import router as chat_router
from .ai_service import analyze_material as ai_analyze_material
from .ai_service import generate_tags as ai_generate_tags_multi
from .txt_parser import read_txt_file, parse_book_info, parse_chapters, flatten_chapters
from .email_service import generate_code, save_code, send_verification_code, verify_code
from .logger import get_logger, get_access_logger

# 日志要早于下面的建表/播种逻辑，它们会写 warning
logger = get_logger(__name__)

# 创建数据库表
Base.metadata.create_all(bind=engine)


def ensure_material_ai_columns():
    """Add MVP AI material columns for existing databases without Alembic."""
    additions = {
        "context_before": "TEXT NULL",
        "context_after": "TEXT NULL",
        "user_mood": "VARCHAR(50) NULL",
        "ai_context_summary": "TEXT NULL",
        "ai_interpretation": "MEDIUMTEXT NULL",
        "ai_theme_analysis": "TEXT NULL",
        "ai_possible_feelings": "TEXT NULL",
        "ai_insight_candidates": "TEXT NULL",
        "ai_writing_topics": "TEXT NULL",
        "ai_questions": "TEXT NULL",
        "ai_analysis_provider": "VARCHAR(50) NULL",
        "ai_analysis_model": "VARCHAR(100) NULL",
        "ai_analysis_status": "VARCHAR(20) NOT NULL DEFAULT 'not_started'",
        "ai_analysis_error": "TEXT NULL",
    }
    try:
        inspector = inspect(engine)
        if not inspector.has_table("materials"):
            return
        existing = {col["name"] for col in inspector.get_columns("materials")}
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE materials ADD COLUMN {name} {ddl}"))
    except Exception as exc:
        logger.warning(f"ensure_material_ai_columns skipped: {exc}")


ensure_material_ai_columns()


def ensure_ai_model_columns():
    """Add AI management columns for existing databases without Alembic."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("ai_models"):
            return
        existing = {col["name"] for col in inspector.get_columns("ai_models")}
        with engine.begin() as conn:
            if "endpoint_path" not in existing:
                conn.execute(text("ALTER TABLE ai_models ADD COLUMN endpoint_path VARCHAR(300) NULL"))
    except Exception as exc:
        logger.warning(f"ensure_ai_model_columns skipped: {exc}")


ensure_ai_model_columns()


def ensure_chat_columns():
    """Add chat columns for existing databases without Alembic."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("chat_conversations"):
            return
        existing = {col["name"] for col in inspector.get_columns("chat_conversations")}
        with engine.begin() as conn:
            if "category" not in existing:
                conn.execute(text("ALTER TABLE chat_conversations ADD COLUMN category VARCHAR(50) NULL"))
    except Exception as exc:
        logger.warning(f"ensure_chat_columns skipped: {exc}")


ensure_chat_columns()


_PURPOSE_DISPLAY_NAMES = {"文本理解", "图片生成", "图像理解", "旧版兼容模型"}

_MODEL_DISPLAY_NAMES = {
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-chat": "DeepSeek Chat",
    "sensenova-u1-fast": "SenseNova U1 Fast",
    "sensenova-6.7-flash-lite": "SenseNova 6.7 Flash Lite",
    "qwen-plus": "通义千问 Plus",
    "doubao-pro-32k": "豆包 Pro 32K",
    "glm-5.1": "GLM-5.1",
    "gpt-3.5-turbo": "GPT-3.5 Turbo",
    "gpt-4o-mini": "GPT-4o mini",
}


def _model_display_name(model_key: str) -> str:
    """Human-readable model name. Falls back to the raw key, never a purpose word."""
    if not model_key:
        return ""
    return _MODEL_DISPLAY_NAMES.get(model_key, model_key)


def _pick_default_chat_model(db):
    """Pick an enabled chat model whose provider has an API key, default provider first."""
    return db.query(AIModel).join(AIProvider, AIModel.provider_id == AIProvider.id).filter(
        AIProvider.enabled == 1,
        AIModel.enabled == 1,
        AIModel.model_type == "chat",
        AIProvider.api_key.isnot(None),
        AIProvider.api_key != "",
    ).order_by(AIProvider.is_default.desc(), AIModel.priority.asc()).first()


def seed_ai_model_settings():
    """Seed AI management tables from .env for first-time setup."""
    from .database import SessionLocal

    provider_defs = [
        {
            "provider_key": "sensenova",
            "display_name": "Sensenova",
            "base_url": settings.SENSENOVA_BASE_URL,
            "api_key": settings.SENSENOVA_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "sensenova",
            "models": [
                (settings.SENSENOVA_TEXT_MODEL, "chat", _model_display_name(settings.SENSENOVA_TEXT_MODEL), "/chat/completions"),
                (settings.SENSENOVA_IMAGE_MODEL, "image_generation", _model_display_name(settings.SENSENOVA_IMAGE_MODEL), "/images/generations"),
                (settings.SENSENOVA_VISION_MODEL, "vision", _model_display_name(settings.SENSENOVA_VISION_MODEL), "/chat/completions"),
            ],
        },
        {
            "provider_key": "deepseek",
            "display_name": "DeepSeek 官网",
            "base_url": settings.DEEPSEEK_BASE_URL,
            "api_key": settings.DEEPSEEK_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "deepseek",
            "models": [(settings.DEEPSEEK_MODEL, "chat", _model_display_name(settings.DEEPSEEK_MODEL), "/chat/completions")],
        },
        {
            "provider_key": "qwen",
            "display_name": "Qwen",
            "base_url": settings.QWEN_BASE_URL,
            "api_key": settings.QWEN_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "qwen",
            "models": [(settings.QWEN_MODEL, "chat", _model_display_name(settings.QWEN_MODEL), "/chat/completions")],
        },
        {
            "provider_key": "zhipu",
            "display_name": "智谱",
            "base_url": settings.ZHIPU_BASE_URL,
            "api_key": settings.ZHIPU_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "zhipu",
            "models": [(settings.ZHIPU_MODEL, "chat", _model_display_name(settings.ZHIPU_MODEL), "/chat/completions")],
        },
        {
            "provider_key": "doubao",
            "display_name": "豆包",
            "base_url": settings.DOUBAO_BASE_URL,
            "api_key": settings.DOUBAO_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "doubao",
            "models": [(settings.DOUBAO_MODEL, "chat", _model_display_name(settings.DOUBAO_MODEL), "/chat/completions")],
        },
        {
            "provider_key": "openai",
            "display_name": "OpenAI 兼容接口",
            "base_url": settings.OPENAI_BASE_URL,
            "api_key": settings.OPENAI_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "openai",
            "models": [(settings.OPENAI_MODEL, "chat", _model_display_name(settings.OPENAI_MODEL), "/chat/completions")],
        },
        {
            "provider_key": "legacy",
            "display_name": "XTY 聚合网关",
            "base_url": settings.AI_API_BASE_URL,
            "api_key": settings.AI_API_KEY,
            "is_default": settings.AI_DEFAULT_PROVIDER == "legacy",
            "models": [(settings.AI_MODEL, "chat", _model_display_name(settings.AI_MODEL), "/chat/completions")],
        },
    ]

    db = SessionLocal()
    try:
        for item in provider_defs:
            provider = db.query(AIProvider).filter(AIProvider.provider_key == item["provider_key"]).first()
            if not provider:
                provider = AIProvider(
                    id=str(uuid.uuid4()),
                    provider_key=item["provider_key"],
                    display_name=item["display_name"],
                    base_url=item["base_url"],
                    api_key=item["api_key"],
                    enabled=1 if item["api_key"] else 0,
                    is_default=1 if item["is_default"] else 0,
                )
                db.add(provider)
                db.flush()
            else:
                provider.base_url = provider.base_url or item["base_url"]
                if not provider.api_key and item["api_key"]:
                    provider.api_key = item["api_key"]
                    provider.enabled = 1

            for model_key, model_type, display_name, endpoint_path in item["models"]:
                if not model_key:
                    continue
                model = db.query(AIModel).filter(
                    AIModel.provider_id == provider.id,
                    AIModel.model_key == model_key,
                ).first()
                if not model:
                    db.add(AIModel(
                        id=str(uuid.uuid4()),
                        provider_id=provider.id,
                        model_key=model_key,
                        display_name=display_name,
                        model_type=model_type,
                        endpoint_path=endpoint_path,
                        enabled=1,
                    ))
                elif not model.endpoint_path:
                    model.endpoint_path = endpoint_path

        db.commit()

        if db.query(AITaskRoute).count() == 0:
            model = _pick_default_chat_model(db)
            if model:
                for task_type in ["tag_generation", "material_analysis"]:
                    db.add(AITaskRoute(
                        id=str(uuid.uuid4()),
                        task_type=task_type,
                        provider_id=model.provider_id,
                        model_id=model.id,
                        route_order=1,
                        strategy="quality_first",
                        timeout_seconds=settings.AI_REQUEST_TIMEOUT,
                        enabled=1,
                    ))
                db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"seed_ai_model_settings skipped: {exc}")
    finally:
        db.close()


seed_ai_model_settings()


def repair_ai_display_names():
    """Replace purpose-word display names ('文本理解' etc.) with real model names.

    Only rewrites rows still holding a seeded purpose word, so names the user
    edited themselves are left alone.
    """
    from .database import SessionLocal

    db = SessionLocal()
    try:
        renamed = 0
        for model in db.query(AIModel).filter(AIModel.display_name.in_(_PURPOSE_DISPLAY_NAMES)).all():
            better = _model_display_name(model.model_key)
            if better and better != model.display_name:
                model.display_name = better
                renamed += 1

        legacy = db.query(AIProvider).filter(
            AIProvider.provider_key == "legacy",
            AIProvider.display_name == "Legacy",
        ).first()
        if legacy:
            legacy.display_name = "XTY 聚合网关"
            renamed += 1

        if renamed:
            db.commit()
            logger.info(f"repair_ai_display_names: 修正了 {renamed} 个显示名")
    except Exception as exc:
        db.rollback()
        logger.warning(f"repair_ai_display_names skipped: {exc}")
    finally:
        db.close()


repair_ai_display_names()


def repair_broken_task_routes():
    """Repoint task routes whose provider has no usable API key.

    Routes seeded from .env placeholders point at key-less providers, which makes
    the task silently unroutable. Move those to a provider that can actually run.
    """
    from .database import SessionLocal

    db = SessionLocal()
    try:
        fallback = _pick_default_chat_model(db)
        if not fallback:
            return

        repaired = 0
        rows = db.query(AITaskRoute, AIProvider).join(
            AIProvider, AITaskRoute.provider_id == AIProvider.id
        ).filter(
            (AIProvider.api_key.is_(None)) | (AIProvider.api_key == "")
        ).all()

        for route, provider in rows:
            logger.warning(
                f"任务 {route.task_type} 的路由指向未配置 API Key 的供应商 "
                f"{provider.provider_key}，改指到 {fallback.model_key}"
            )
            route.provider_id = fallback.provider_id
            route.model_id = fallback.id
            repaired += 1

        if repaired:
            db.commit()
            logger.info(f"repair_broken_task_routes: 修复了 {repaired} 条路由")
    except Exception as exc:
        db.rollback()
        logger.warning(f"repair_broken_task_routes skipped: {exc}")
    finally:
        db.close()


repair_broken_task_routes()


def seed_chat_defaults():
    """Seed default chat personas and the chat_completion task route."""
    from .database import SessionLocal
    from .chat_models import ChatRole

    presets = [
        {
            "name": "通用助手",
            "avatar": "✨",
            "description": "日常问答、信息查询和任务处理。",
            "system_prompt": "你是一个可靠、清晰、友好的通用 AI 助手。请用用户使用的语言回答，必要时主动澄清关键约束。",
        },
        {
            "name": "读书助手",
            "avatar": "📖",
            "description": "帮助理解书籍、分析人物和整理读后感。",
            "system_prompt": "你是读书助手，擅长帮助用户理解书籍内容、人物关系、主题和写作手法。回答要有文本意识，避免编造书中没有的信息。",
        },
        {
            "name": "写作教练",
            "avatar": "✍️",
            "description": "提供写作建议、结构梳理和润色。",
            "system_prompt": "你是写作教练，擅长帮助用户梳理结构、打磨表达、改进文风。反馈要具体、温和，并给出可操作的修改示例。",
        },
        {
            "name": "数学老师",
            "avatar": "🧑‍🏫",
            "description": "用循序渐进的方式讲解数学概念和题目。",
            "system_prompt": "你是耐心的数学老师。请先判断用户的理解水平，再用直观例子和分步骤推导解释数学问题。",
        },
        {
            "name": "编程导师",
            "avatar": "💻",
            "description": "代码指导、技术答疑和项目建议。",
            "system_prompt": "你是资深编程导师。请优先定位问题本质，给出简洁可靠的方案，并在需要时补充代码示例和测试建议。",
        },
        {
            "name": "英语外教",
            "avatar": "🌍",
            "description": "英语对话练习、语法纠错和口语提升。",
            "system_prompt": "You are a friendly English tutor. Help the user practice English conversation, correct grammar mistakes, and improve spoken expression. Respond in the user's language when explaining grammar, but encourage English practice during conversation.",
        },
        {
            "name": "创意伙伴",
            "avatar": "💡",
            "description": "头脑风暴、灵感激发和创意写作。",
            "system_prompt": "你是创意伙伴，擅长头脑风暴和灵感激发。请用开放、鼓励的方式帮助用户探索想法，提供多元视角，不急于否定任何创意。在需要时给出具体的创意示例。",
        },
        {
            "name": "生活顾问",
            "avatar": "🌿",
            "description": "日常建议、健康提醒和生活规划。",
            "system_prompt": "你是生活顾问，擅长提供日常建议、时间管理和生活规划。请以温和、实用的方式给出建议，尊重用户的个人选择，不做强迫性推荐。",
        },
    ]

    db = SessionLocal()
    try:
        for item in presets:
            exists = db.query(ChatRole).filter(
                ChatRole.role_type == "preset",
                ChatRole.name == item["name"],
            ).first()
            if exists:
                continue
            db.add(ChatRole(
                user_id=None,
                role_type="preset",
                is_public=1,
                **item,
            ))

        has_chat_route = db.query(AITaskRoute).filter(AITaskRoute.task_type == "chat_completion").first()
        if not has_chat_route:
            model = _pick_default_chat_model(db)
            if model:
                db.add(AITaskRoute(
                    id=str(uuid.uuid4()),
                    task_type="chat_completion",
                    provider_id=model.provider_id,
                    model_id=model.id,
                    route_order=1,
                    strategy="quality_first",
                    timeout_seconds=settings.AI_REQUEST_TIMEOUT,
                    enabled=1,
                ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"seed_chat_defaults skipped: {exc}")
    finally:
        db.close()


seed_chat_defaults()

app = FastAPI(title="智能助手平台")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== 日志 ======
access_logger = get_access_logger()

SENSITIVE_FIELDS = {"password", "passwd", "secret", "token", "authorization", "code"}


def _sanitize_body(body: bytes) -> str:
    """Decode request body and mask sensitive fields."""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in data:
                if key.lower() in SENSITIVE_FIELDS:
                    data[key] = "***"
        return json.dumps(data, ensure_ascii=False)[:2000]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return f"<binary {len(body)} bytes>"


def _extract_user_info(request) -> tuple:
    """Extract user_id and username from JWT token in request."""
    try:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub", "")
            return user_id, "authenticated"
    except Exception:
        pass
    return "", "anonymous"


@app.middleware("http")
async def logging_middleware(request, call_next):
    start = time.time()
    body = b""
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()

    response = await call_next(request)
    elapsed = int((time.time() - start) * 1000)

    user_id, user_label = _extract_user_info(request)
    client_ip = request.client.host if request.client else "unknown"
    path = str(request.url.path)
    if request.url.query:
        path += f"?{request.url.query}"

    log_line = f"{request.method} {path} | {response.status_code} | {elapsed}ms | {user_label}"
    if user_id:
        log_line += f":{user_id}"
    log_line += f" | {client_ip}"

    if response.status_code >= 500:
        logger.error(log_line)
    elif response.status_code >= 400:
        logger.warning(log_line)
    else:
        logger.info(log_line)
        access_logger.info(log_line)

    if body:
        body_str = _sanitize_body(body)
        if response.status_code >= 400:
            logger.warning(f"  Body: {body_str}")
        else:
            logger.info(f"  Body: {body_str}")
            access_logger.info(f"  Body: {body_str}")

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    user_id, user_label = _extract_user_info(request)
    client_ip = request.client.host if request.client else "unknown"
    body = b""
    try:
        body = await request.body()
    except Exception:
        pass

    error_detail = (
        f"Unhandled exception | {request.method} {request.url.path}\n"
        f"  User: {user_label}"
    )
    if user_id:
        error_detail += f":{user_id}"
    error_detail += f" | IP: {client_ip}\n"
    if body:
        error_detail += f"  Body: {_sanitize_body(body)}\n"
    error_detail += f"  {traceback.format_exc()}"

    logger.error(error_detail)

    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请查看日志获取详情"},
    )


# 密码加密
app.include_router(chat_router)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ====== 工具函数 ======
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


# ====== 请求/响应模型 ======
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: str
    code: str


class SendCodeRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    user_id: str
    email: str
    username: str
    token: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str


class ChapterResponse(BaseModel):
    id: str
    title: Optional[str]
    chapter_order: int
    level: int = 1
    parent_title: Optional[str] = None

    class Config:
        from_attributes = True


class ChapterBrief(BaseModel):
    chapter_order: int
    title: Optional[str] = None

    class Config:
        from_attributes = True

class BookResponse(BaseModel):
    id: str
    title: str
    author: Optional[str]
    file_type: str
    chapters_count: int
    created_at: datetime
    chapters: List[ChapterBrief] = []

    class Config:
        from_attributes = True


class BookDetailResponse(BookResponse):
    chapters: List[ChapterResponse] = []


class BookListResponse(BaseModel):
    total: int
    items: List[BookResponse]


class ReadingProgressRequest(BaseModel):
    chapter_order: int
    scroll_top: int = 0
    scroll_ratio: float = 0


class ReadingProgressResponse(BaseModel):
    book_id: str
    chapter_order: Optional[int] = None
    scroll_top: int = 0
    scroll_ratio: float = 0
    updated_at: Optional[datetime] = None


class UpdateBookRequest(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None


class ChapterUpdateItem(BaseModel):
    title: Optional[str] = None
    content: str
    level: int = 1
    parent_title: Optional[str] = None


class ChaptersUpdateRequest(BaseModel):
    chapters: List[ChapterUpdateItem]


# ====== 素材相关模型 ======
class MaterialCreateRequest(BaseModel):
    content: str
    source_type: str  # book摘录, 微信读书, 自己感悟
    book_id: Optional[str] = None
    chapter_order: Optional[int] = None
    note: Optional[str] = None
    status: str = "completed"  # draft / completed
    entry_mode: Optional[str] = None  # home_quick / book_detail / materials_page
    selected_text: Optional[str] = None
    anchor_start: Optional[int] = None
    anchor_end: Optional[int] = None
    locator_text: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    user_mood: Optional[str] = None
    image_data: Optional[str] = None  # base64 截图


class MaterialUpdateRequest(BaseModel):
    content: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    selected_text: Optional[str] = None
    anchor_start: Optional[int] = None
    anchor_end: Optional[int] = None
    chapter_order: Optional[int] = None
    entry_mode: Optional[str] = None
    user_mood: Optional[str] = None


class MaterialResponse(BaseModel):
    id: str
    content: str
    source_type: str
    book_id: Optional[str]
    chapter_order: Optional[int]
    note: Optional[str]
    tags: Optional[List[str]]
    status: str = "completed"
    entry_mode: Optional[str] = None
    selected_text: Optional[str] = None
    anchor_start: Optional[int] = None
    anchor_end: Optional[int] = None
    locator_text: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    user_mood: Optional[str] = None
    ai_context_summary: Optional[str] = None
    ai_interpretation: Optional[str] = None
    ai_theme_analysis: Optional[str] = None
    ai_possible_feelings: List[str] = []
    ai_insight_candidates: List[str] = []
    ai_writing_topics: List[str] = []
    ai_questions: List[str] = []
    ai_analysis_provider: Optional[str] = None
    ai_analysis_model: Optional[str] = None
    ai_analysis_status: str = "not_started"
    ai_analysis_error: Optional[str] = None
    image_data: Optional[str] = None  # base64 截图（仅详情接口返回）
    created_at: datetime
    updated_at: Optional[datetime] = None

    # 可选的关联信息
    book_title: Optional[str] = None
    chapter_title: Optional[str] = None

    class Config:
        from_attributes = True


class MaterialListResponse(BaseModel):
    total: int
    items: List[MaterialResponse]


class AIProviderRequest(BaseModel):
    provider_key: Optional[str] = None
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None


class AIProviderResponse(BaseModel):
    id: str
    provider_key: str
    display_name: str
    base_url: str
    api_key_masked: Optional[str] = None
    has_api_key: bool
    enabled: bool
    is_default: bool
    last_test_status: Optional[str] = None
    last_test_error: Optional[str] = None
    last_test_at: Optional[datetime] = None


class AIModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider_id: Optional[str] = None
    model_key: Optional[str] = None
    display_name: Optional[str] = None
    model_type: Optional[str] = None
    endpoint_path: Optional[str] = None
    context_window: Optional[int] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    notes: Optional[str] = None


class AIModelResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    provider_id: str
    provider_key: Optional[str] = None
    provider_name: Optional[str] = None
    model_key: str
    display_name: str
    model_type: str
    endpoint_path: Optional[str] = None
    context_window: Optional[int] = None
    enabled: bool
    priority: int
    notes: Optional[str] = None


class AITaskRouteItemRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider_id: str
    model_id: str
    route_order: int
    strategy: str = "quality_first"
    timeout_seconds: int = 30
    enabled: bool = True


class AITaskRouteUpdateRequest(BaseModel):
    routes: List[AITaskRouteItemRequest]


class AITaskRouteResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    task_type: str
    provider_id: str
    provider_key: str
    provider_name: str
    model_id: str
    model_key: str
    model_name: str
    route_order: int
    strategy: str
    timeout_seconds: int
    enabled: bool


class AIModelTestRequest(BaseModel):
    prompt: str = "请只返回 JSON 数组：[\"测试\"]"
    task_type: str = "tag_generation"


class AIModelTestResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ok: bool
    provider_key: str
    model_key: str
    latency_ms: Optional[int] = None
    response: Optional[str] = None
    error: Optional[str] = None


class AICallLogResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    task_type: str
    provider_key: Optional[str]
    model_key: Optional[str]
    status: str
    latency_ms: Optional[int]
    error_message: Optional[str]
    created_at: Optional[datetime]


# ====== AI 自动标签 ======
async def ai_generate_tags(content: str) -> List[str]:
    """Generate tags through the multi-model AI gateway."""
    if not settings.AI_ANALYSIS_ENABLED:
        return []
    tags, _, _ = await ai_generate_tags_multi(content)
    return tags


def background_generate_tags(material_id: str, content: str):
    """后台异步生成标签，失败自动重试最多3次"""
    import asyncio
    import time

    async def _do():
        for attempt in range(3):
            try:
                tags = await ai_generate_tags(content)
                # 写入数据库
                from .database import SessionLocal
                db = SessionLocal()
                try:
                    mat = db.query(Material).filter(Material.id == material_id).first()
                    if mat:
                        mat.tags = json.dumps(tags, ensure_ascii=False) if tags else None
                        db.commit()
                finally:
                    db.close()
                return
            except Exception:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))

    asyncio.run(_do())


# ====== AI 模型管理 ======
def _mask_api_key(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:3]}****{api_key[-4:]}"


def _provider_response(provider: AIProvider) -> dict:
    return {
        "id": provider.id,
        "provider_key": provider.provider_key,
        "display_name": provider.display_name,
        "base_url": provider.base_url,
        "api_key_masked": _mask_api_key(provider.api_key),
        "has_api_key": bool(provider.api_key),
        "enabled": bool(provider.enabled),
        "is_default": bool(provider.is_default),
        "last_test_status": provider.last_test_status,
        "last_test_error": provider.last_test_error,
        "last_test_at": provider.last_test_at,
    }


def _model_response(model: AIModel, provider: Optional[AIProvider] = None) -> dict:
    provider = provider or model.provider
    return {
        "id": model.id,
        "provider_id": model.provider_id,
        "provider_key": provider.provider_key if provider else None,
        "provider_name": provider.display_name if provider else None,
        "model_key": model.model_key,
        "display_name": model.display_name,
        "model_type": model.model_type,
        "endpoint_path": model.endpoint_path,
        "context_window": model.context_window,
        "enabled": bool(model.enabled),
        "priority": model.priority or 100,
        "notes": model.notes,
    }


def _route_response(route: AITaskRoute) -> dict:
    return {
        "id": route.id,
        "task_type": route.task_type,
        "provider_id": route.provider_id,
        "provider_key": route.provider.provider_key,
        "provider_name": route.provider.display_name,
        "model_id": route.model_id,
        "model_key": route.model.model_key,
        "model_name": route.model.display_name,
        "route_order": route.route_order,
        "strategy": route.strategy,
        "timeout_seconds": route.timeout_seconds,
        "enabled": bool(route.enabled),
    }


@app.get("/api/v1/admin/ai/providers", response_model=List[AIProviderResponse])
async def get_ai_providers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    providers = db.query(AIProvider).order_by(AIProvider.is_default.desc(), AIProvider.display_name.asc()).all()
    return [_provider_response(provider) for provider in providers]


@app.post("/api/v1/admin/ai/providers", response_model=AIProviderResponse)
async def create_ai_provider(
    req: AIProviderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not req.provider_key or not req.display_name or not req.base_url:
        raise HTTPException(status_code=400, detail="provider_key, display_name and base_url are required")
    exists = db.query(AIProvider).filter(AIProvider.provider_key == req.provider_key).first()
    if exists:
        raise HTTPException(status_code=400, detail="Provider already exists")
    if req.is_default:
        db.query(AIProvider).update({AIProvider.is_default: 0})
    provider = AIProvider(
        id=str(uuid.uuid4()),
        provider_key=req.provider_key,
        display_name=req.display_name,
        base_url=req.base_url,
        api_key=req.api_key,
        enabled=1 if req.enabled is not False else 0,
        is_default=1 if req.is_default else 0,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)

    logger.info(f"创建AI Provider成功: provider_key={req.provider_key}, display_name={req.display_name}")
    return _provider_response(provider)


@app.patch("/api/v1/admin/ai/providers/{provider_id}", response_model=AIProviderResponse)
async def update_ai_provider(
    provider_id: str,
    req: AIProviderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if req.display_name is not None:
        provider.display_name = req.display_name
    if req.base_url is not None:
        provider.base_url = req.base_url
    if req.api_key is not None:
        provider.api_key = req.api_key
    if req.enabled is not None:
        provider.enabled = 1 if req.enabled else 0
    if req.is_default is not None:
        if req.is_default:
            db.query(AIProvider).filter(AIProvider.id != provider.id).update({AIProvider.is_default: 0})
        provider.is_default = 1 if req.is_default else 0
    db.commit()
    db.refresh(provider)

    logger.info(f"更新AI Provider成功: provider_id={provider_id}, provider_key={provider.provider_key}")
    return _provider_response(provider)


@app.delete("/api/v1/admin/ai/providers/{provider_id}", status_code=204)
async def delete_ai_provider(
    provider_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    model_ids = [m.id for m in db.query(AIModel).filter(AIModel.provider_id == provider_id).all()]
    if model_ids:
        db.query(AITaskRoute).filter(AITaskRoute.model_id.in_(model_ids)).delete(synchronize_session=False)
    db.query(AIModel).filter(AIModel.provider_id == provider_id).delete()
    db.delete(provider)
    db.commit()

    logger.info(f"删除AI Provider成功: provider_id={provider_id}, provider_key={provider.provider_key}")


@app.get("/api/v1/admin/ai/models", response_model=List[AIModelResponse])
async def get_ai_models(
    provider_id: Optional[str] = None,
    model_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(AIModel)
    if provider_id:
        query = query.filter(AIModel.provider_id == provider_id)
    if model_type:
        query = query.filter(AIModel.model_type == model_type)
    if enabled is not None:
        query = query.filter(AIModel.enabled == (1 if enabled else 0))
    models = query.order_by(AIModel.priority.asc(), AIModel.created_at.asc()).all()
    return [_model_response(model) for model in models]


@app.post("/api/v1/admin/ai/models", response_model=AIModelResponse)
async def create_ai_model(
    req: AIModelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not req.provider_id or not req.model_key or not req.display_name:
        raise HTTPException(status_code=400, detail="provider_id, model_key and display_name are required")
    provider = db.query(AIProvider).filter(AIProvider.id == req.provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    model = AIModel(
        id=str(uuid.uuid4()),
        provider_id=req.provider_id,
        model_key=req.model_key,
        display_name=req.display_name,
        model_type=req.model_type or "chat",
        endpoint_path=req.endpoint_path or "/chat/completions",
        context_window=req.context_window,
        enabled=1 if req.enabled is not False else 0,
        priority=req.priority or 100,
        notes=req.notes,
    )
    db.add(model)
    db.commit()
    db.refresh(model)

    logger.info(f"创建AI Model成功: model_key={req.model_key}, display_name={req.display_name}, provider={provider.provider_key}")
    return _model_response(model, provider)


@app.patch("/api/v1/admin/ai/models/{model_id}", response_model=AIModelResponse)
async def update_ai_model(
    model_id: str,
    req: AIModelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    model = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if req.model_key is not None:
        model.model_key = req.model_key
    if req.display_name is not None:
        model.display_name = req.display_name
    if req.model_type is not None:
        model.model_type = req.model_type
    if req.endpoint_path is not None:
        model.endpoint_path = req.endpoint_path
    if req.context_window is not None:
        model.context_window = req.context_window
    if req.enabled is not None:
        model.enabled = 1 if req.enabled else 0
    if req.priority is not None:
        model.priority = req.priority
    if req.notes is not None:
        model.notes = req.notes
    db.commit()
    db.refresh(model)

    logger.info(f"更新AI Model成功: model_id={model_id}, model_key={model.model_key}")
    return _model_response(model)


@app.delete("/api/v1/admin/ai/models/{model_id}", status_code=204)
async def delete_ai_model(
    model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    model = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    db.query(AITaskRoute).filter(AITaskRoute.model_id == model_id).delete()
    db.delete(model)
    db.commit()

    logger.info(f"删除AI Model成功: model_id={model_id}, model_key={model.model_key}")


@app.get("/api/v1/admin/ai/task-routes", response_model=List[AITaskRouteResponse])
async def get_ai_task_routes(
    task_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(AITaskRoute)
    if task_type:
        query = query.filter(AITaskRoute.task_type == task_type)
    routes = query.order_by(AITaskRoute.task_type.asc(), AITaskRoute.route_order.asc()).all()
    return [_route_response(route) for route in routes]


@app.put("/api/v1/admin/ai/task-routes/{task_type}", response_model=List[AITaskRouteResponse])
async def update_ai_task_route(
    task_type: str,
    req: AITaskRouteUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.query(AITaskRoute).filter(AITaskRoute.task_type == task_type).delete()
    for item in req.routes:
        provider = db.query(AIProvider).filter(AIProvider.id == item.provider_id).first()
        model = db.query(AIModel).filter(AIModel.id == item.model_id).first()
        if not provider or not model:
            raise HTTPException(status_code=400, detail="Invalid provider or model")
        db.add(AITaskRoute(
            id=str(uuid.uuid4()),
            task_type=task_type,
            provider_id=item.provider_id,
            model_id=item.model_id,
            route_order=item.route_order,
            strategy=item.strategy,
            timeout_seconds=item.timeout_seconds,
            enabled=1 if item.enabled else 0,
        ))
    db.commit()
    routes = db.query(AITaskRoute).filter(AITaskRoute.task_type == task_type).order_by(AITaskRoute.route_order.asc()).all()

    logger.info(f"更新AI Task Route成功: task_type={task_type}, 路由数={len(req.routes)}")
    return [_route_response(route) for route in routes]


@app.post("/api/v1/admin/ai/models/{model_id}/test", response_model=AIModelTestResponse)
async def test_ai_model(
    model_id: str,
    req: AIModelTestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    import time

    model = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    provider = db.query(AIProvider).filter(AIProvider.id == model.provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.api_key:
        return AIModelTestResponse(
            ok=False,
            provider_key=provider.provider_key,
            model_key=model.model_key,
            error="API Key not configured",
        )

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            endpoint_path = model.endpoint_path or "/chat/completions"
            url = f"{provider.base_url.rstrip('/')}{endpoint_path}"
            headers = {"Authorization": f"Bearer {provider.api_key}"}
            if model.model_type == "image_generation":
                payload = {
                    "model": model.model_key,
                    "prompt": req.prompt,
                }
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                content = json.dumps(resp.json(), ensure_ascii=False)
            else:
                payload = {
                    "model": model.model_key,
                    "messages": [{"role": "user", "content": req.prompt}],
                    "temperature": 0.2,
                }
            if model.model_type != "image_generation" and provider.provider_key == "zhipu":
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
                content = "".join(chunks).strip()
                if not content:
                    raise ValueError("Zhipu stream returned no content")
            elif model.model_type != "image_generation":
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
            provider.last_test_status = "success"
            provider.last_test_error = None
            provider.last_test_at = datetime.utcnow()
            db.add(AICallLog(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                task_type=req.task_type,
                provider_key=provider.provider_key,
                model_key=model.model_key,
                status="success",
                latency_ms=int((time.perf_counter() - started) * 1000),
            ))
            db.commit()
            return AIModelTestResponse(
                ok=True,
                provider_key=provider.provider_key,
                model_key=model.model_key,
                latency_ms=int((time.perf_counter() - started) * 1000),
                response=content,
            )
    except Exception as exc:
        provider.last_test_status = "failed"
        provider.last_test_error = str(exc)[:1000]
        provider.last_test_at = datetime.utcnow()
        db.add(AICallLog(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            task_type=req.task_type,
            provider_key=provider.provider_key,
            model_key=model.model_key,
            status="failed",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message=str(exc)[:1000],
        ))
        db.commit()
        return AIModelTestResponse(
            ok=False,
            provider_key=provider.provider_key,
            model_key=model.model_key,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc),
        )


@app.get("/api/v1/admin/ai/call-logs", response_model=List[AICallLogResponse])
async def get_ai_call_logs(
    task_type: Optional[str] = None,
    provider_key: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(AICallLog)
    if task_type:
        query = query.filter(AICallLog.task_type == task_type)
    if provider_key:
        query = query.filter(AICallLog.provider_key == provider_key)
    if status_filter:
        query = query.filter(AICallLog.status == status_filter)
    logs = query.order_by(AICallLog.created_at.desc()).limit(min(limit, 200)).all()
    return [
        AICallLogResponse(
            id=log.id,
            task_type=log.task_type,
            provider_key=log.provider_key,
            model_key=log.model_key,
            status=log.status,
            latency_ms=log.latency_ms,
            error_message=log.error_message,
            created_at=log.created_at,
        )
        for log in logs
    ]


# ====== 路由 ======
@app.get("/")
async def root():
    return {"message": "API 运行正常"}


async def _assert_email_deliverable(email: str):
    """检查邮箱域名能否收信。DNS 超时/解析失败时库内部放行，不会误伤正常用户。

    DNS 查询是阻塞 IO，放到线程池执行，避免卡住事件循环。
    """
    try:
        await run_in_threadpool(validate_email, email, check_deliverability=True)
    except EmailNotValidError as e:
        logger.warning(f"邮箱不可用({email}): {e}")
        raise HTTPException(status_code=400, detail="该邮箱域名不存在或无法接收邮件")


@app.post("/api/v1/auth/send-code")
async def send_code(req: SendCodeRequest, db: Session = Depends(get_db)):
    await _assert_email_deliverable(req.email)

    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    # 限流：同一邮箱 N 秒内只能发一次
    recent_after = datetime.utcnow() - timedelta(seconds=settings.CODE_RESEND_SECONDS)
    recent = (
        db.query(EmailCode)
        .filter(EmailCode.email == req.email, EmailCode.created_at >= recent_after)
        .first()
    )
    if recent:
        wait = settings.CODE_RESEND_SECONDS - int(
            (datetime.utcnow() - recent.created_at).total_seconds()
        )
        raise HTTPException(
            status_code=429, detail=f"发送过于频繁，请 {max(wait, 1)} 秒后重试"
        )

    code = generate_code()
    save_code(db, req.email, code)

    # SMTP 发信是阻塞 IO，放到线程池
    try:
        sent = await run_in_threadpool(send_verification_code, req.email, code)
    except Exception:
        raise HTTPException(status_code=500, detail="验证码发送失败，请稍后重试")

    logger.info(f"验证码已生成: email={req.email}, 实际发送={sent}")
    return {
        "message": "验证码已发送" if sent else "验证码已生成（SMTP 未配置，请查看后端日志）",
        "expire_minutes": settings.CODE_EXPIRE_MINUTES,
    }


@app.post("/api/v1/auth/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    await _assert_email_deliverable(req.email)

    # 检查邮箱是否已存在
    if db.query(User).filter(User.email == req.email).first():
        logger.warning(f"用户注册失败: username={req.username}, 原因=邮箱已被注册({req.email})")
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    # 校验邮箱验证码（通过后即标记为已使用，防重放）
    ok, err = verify_code(db, req.email, req.code)
    if not ok:
        logger.warning(f"用户注册失败: email={req.email}, 原因={err}")
        raise HTTPException(status_code=400, detail=err)

    # 创建用户
    user = User(
        id=str(uuid.uuid4()),
        email=req.email,
        username=req.username,
        password_hash=get_password_hash(req.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"用户注册成功: username={req.username}, email={req.email}, user_id={user.id}")
    return TokenResponse(
        user_id=user.id,
        email=user.email,
        username=user.username,
        token=create_token(user.id)
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        logger.warning(f"用户登录失败: email={req.email}, 原因=邮箱或密码错误")
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    logger.info(f"用户登录成功: username={user.username}, user_id={user.id}")
    return TokenResponse(
        user_id=user.id,
        email=user.email,
        username=user.username,
        token=create_token(user.id)
    )


@app.get("/api/v1/user/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username
    )


# ====== 书籍路由 ======
@app.post("/api/v1/books", response_model=BookResponse, status_code=201)
async def upload_book(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上传书籍（支持 txt）"""
    try:
        # 验证文件类型
        filename = file.filename.lower()
        if not filename.endswith('.txt'):
            raise HTTPException(status_code=400, detail="目前只支持 txt 格式")

        # 读取文件内容
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="文件为空")

        if len(file_bytes) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")

        # 解析文件
        content = read_txt_file(file_bytes)

        # 提取书籍信息
        book_info = parse_book_info(content)
        book_title = title or book_info.get("title") or file.filename.replace('.txt', '')
        book_author = author or book_info.get("author")

        # 解析章节（树形结构）
        chapters_tree = parse_chapters(content)

        # 扁平化章节（用于数据库存储）
        chapters_data = flatten_chapters(chapters_tree)

        # 创建书籍记录
        book = Book(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            title=book_title,
            author=book_author,
            file_type="txt",
            chapters_count=len(chapters_data)
        )
        db.add(book)

        # 创建章节记录
        for idx, chapter in enumerate(chapters_data):
            ch = Chapter(
                id=str(uuid.uuid4()),
                book_id=book.id,
                title=chapter["title"],
                content=chapter["content"],
                chapter_order=idx + 1,
                level=chapter.get("level", 1),
                parent_title=chapter.get("parent_title")
            )
            db.add(ch)

        db.commit()
        db.refresh(book)

        logger.info(
            f"上传书籍成功: title={book_title}, author={book_author}, "
            f"filename={file.filename}, file_size={len(file_bytes)}, "
            f"chapters={len(chapters_data)}, user={current_user.username}"
        )
        return book

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"上传书籍失败: filename={file.filename}, user={current_user.username}, error={e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.get("/api/v1/books", response_model=BookListResponse)
async def get_books(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取书籍列表"""
    books = db.query(Book).filter(
        Book.user_id == current_user.id
    ).order_by(Book.created_at.desc()).all()

    items = []
    for book in books:
        chapters = db.query(Chapter).filter(
            Chapter.book_id == book.id
        ).order_by(Chapter.chapter_order).all()
        items.append({
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "file_type": book.file_type,
            "chapters_count": book.chapters_count,
            "created_at": book.created_at,
            "chapters": [{"chapter_order": ch.chapter_order, "title": ch.title} for ch in chapters]
        })

    return BookListResponse(total=len(books), items=items)


@app.get("/api/v1/books/{book_id}", response_model=BookDetailResponse)
async def get_book(
    book_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取书籍详情（含章节）"""
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()

    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    return book


@app.patch("/api/v1/books/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: str,
    req: UpdateBookRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新书籍信息（书名、作者）"""
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()

    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    if req.title is not None:
        book.title = req.title
    if req.author is not None:
        book.author = req.author

    db.commit()
    db.refresh(book)
    return book


def _get_owned_book_or_404(book_id: str, current_user: User, db: Session) -> Book:
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.get("/api/v1/books/{book_id}/reading-progress", response_model=ReadingProgressResponse)
async def get_reading_progress(
    book_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the current user's last reading position for a book."""
    _get_owned_book_or_404(book_id, current_user, db)

    progress = db.query(ReadingProgress).filter(
        ReadingProgress.user_id == current_user.id,
        ReadingProgress.book_id == book_id
    ).first()

    if not progress:
        return ReadingProgressResponse(book_id=book_id)

    return ReadingProgressResponse(
        book_id=book_id,
        chapter_order=progress.chapter_order,
        scroll_top=progress.scroll_top or 0,
        scroll_ratio=progress.scroll_ratio or 0,
        updated_at=progress.updated_at
    )


@app.put("/api/v1/books/{book_id}/reading-progress", response_model=ReadingProgressResponse)
async def save_reading_progress(
    book_id: str,
    req: ReadingProgressRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update the current user's last reading position for a book."""
    _get_owned_book_or_404(book_id, current_user, db)

    chapter = db.query(Chapter).filter(
        Chapter.book_id == book_id,
        Chapter.chapter_order == req.chapter_order
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    scroll_top = max(int(req.scroll_top or 0), 0)
    scroll_ratio = min(max(float(req.scroll_ratio or 0), 0), 1)

    progress = db.query(ReadingProgress).filter(
        ReadingProgress.user_id == current_user.id,
        ReadingProgress.book_id == book_id
    ).first()

    if not progress:
        progress = ReadingProgress(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            book_id=book_id
        )
        db.add(progress)

    progress.chapter_order = req.chapter_order
    progress.scroll_top = scroll_top
    progress.scroll_ratio = scroll_ratio

    db.commit()
    db.refresh(progress)

    return ReadingProgressResponse(
        book_id=book_id,
        chapter_order=progress.chapter_order,
        scroll_top=progress.scroll_top or 0,
        scroll_ratio=progress.scroll_ratio or 0,
        updated_at=progress.updated_at
    )


@app.put("/api/v1/books/{book_id}/chapters")
async def update_chapters(
    book_id: str,
    req: ChaptersUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """批量更新章节（用于章节编辑器保存）"""
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()

    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    # 删除旧章节
    db.query(Chapter).filter(Chapter.book_id == book_id).delete()

    # 创建新章节
    for idx, ch in enumerate(req.chapters):
        chapter = Chapter(
            id=str(uuid.uuid4()),
            book_id=book_id,
            title=ch.title,
            content=ch.content,
            chapter_order=idx + 1,
            level=ch.level,
            parent_title=ch.parent_title
        )
        db.add(chapter)

    book.chapters_count = len(req.chapters)
    db.commit()
    db.refresh(book)

    logger.info(f"更新章节成功: book_id={book_id}, title={book.title}, 章节数={len(req.chapters)}, user={current_user.username}")
    return {"message": "保存成功", "chapters_count": book.chapters_count}


@app.delete("/api/v1/books/{book_id}", status_code=204)
async def delete_book(
    book_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除书籍"""
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()

    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    db.query(ReadingProgress).filter(
        ReadingProgress.book_id == book_id,
        ReadingProgress.user_id == current_user.id
    ).delete()
    # 删除章节
    db.query(Chapter).filter(Chapter.book_id == book_id).delete()
    db.delete(book)
    db.commit()

    logger.info(f"删除书籍成功: book_id={book_id}, title={book.title}, user={current_user.username}")


@app.put("/api/v1/books/{book_id}/chapters")
async def update_chapters(
    book_id: str,
    req: ChaptersUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """批量更新章节（编辑器保存）"""
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()

    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    try:
        # 删除旧章节
        db.query(Chapter).filter(Chapter.book_id == book_id).delete()

        # 创建新章节
        for idx, ch in enumerate(req.chapters):
            chapter = Chapter(
                id=str(uuid.uuid4()),
                book_id=book_id,
                title=ch.title,
                content=ch.content,
                chapter_order=idx + 1,
                level=ch.level,
                parent_title=ch.parent_title
            )
            db.add(chapter)

        book.chapters_count = len(req.chapters)
        db.commit()
        db.refresh(book)
        return book

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@app.get("/api/v1/books/{book_id}/chapters/{chapter_order}")
async def get_chapter(
    book_id: str,
    chapter_order: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取指定章节内容"""
    book = db.query(Book).filter(
        Book.id == book_id,
        Book.user_id == current_user.id
    ).first()

    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    chapter = db.query(Chapter).filter(
        Chapter.book_id == book_id,
        Chapter.chapter_order == chapter_order
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    return {
        "id": chapter.id,
        "title": chapter.title,
        "content": chapter.content,
        "chapter_order": chapter.chapter_order
    }


# ====== 素材路由 ======
def _json_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(item) for item in data if str(item).strip()]
    except Exception:
        pass
    return []


def _dump_list(items) -> Optional[str]:
    if not items:
        return None
    if isinstance(items, list):
        return json.dumps([str(item).strip() for item in items if str(item).strip()], ensure_ascii=False)
    return None


def _extract_material_context(mat: Material, chapter: Optional[Chapter], window: int = 600) -> tuple:
    if mat.context_before or mat.context_after or not chapter:
        return mat.context_before, mat.context_after

    content = chapter.content or ""
    start = mat.anchor_start
    end = mat.anchor_end
    selected = mat.selected_text or mat.content or ""
    if (start is None or end is None) and selected:
        idx = content.find(selected)
        if idx >= 0:
            start = idx
            end = idx + len(selected)

    if start is None or end is None:
        return None, None

    start = max(int(start), 0)
    end = min(max(int(end), start), len(content))
    before = content[max(0, start - window):start].strip()
    after = content[end:min(len(content), end + window)].strip()
    return before, after


def _build_ai_payload(mat: Material, db: Session) -> dict:
    book = db.query(Book).filter(Book.id == mat.book_id).first() if mat.book_id else None
    chapter = None
    if mat.book_id and mat.chapter_order:
        chapter = db.query(Chapter).filter(
            Chapter.book_id == mat.book_id,
            Chapter.chapter_order == mat.chapter_order
        ).first()

    context_before, context_after = _extract_material_context(mat, chapter)
    mat.context_before = context_before
    mat.context_after = context_after

    return {
        "book": {
            "title": book.title if book else None,
            "author": book.author if book else None,
        },
        "chapter": {
            "chapter_order": mat.chapter_order,
            "title": chapter.title if chapter else None,
        },
        "material": {
            "content": mat.content,
            "selected_text": mat.selected_text,
            "context_before": context_before,
            "context_after": context_after,
            "locator_text": mat.locator_text,
        },
        "user_input": {
            "note": mat.note,
            "mood": mat.user_mood,
        },
    }


def _apply_ai_analysis(mat: Material, analysis: dict, provider: str, model: str):
    mat.ai_context_summary = analysis.get("context_summary")
    mat.ai_interpretation = analysis.get("interpretation")
    mat.ai_theme_analysis = analysis.get("theme_analysis")
    mat.ai_possible_feelings = _dump_list(analysis.get("possible_feelings"))
    mat.ai_insight_candidates = _dump_list(analysis.get("personal_insight_candidates"))
    mat.ai_writing_topics = _dump_list(analysis.get("writing_topics"))
    mat.ai_questions = _dump_list(analysis.get("questions"))
    mat.ai_analysis_provider = provider
    mat.ai_analysis_model = model
    mat.ai_analysis_status = "completed"
    mat.ai_analysis_error = None
    if analysis.get("tags"):
        mat.tags = _dump_list(analysis.get("tags"))


def background_analyze_material(material_id: str):
    """Analyze one material in the background through the multi-model gateway."""
    import asyncio
    from .database import SessionLocal

    async def _do():
        db = SessionLocal()
        try:
            mat = db.query(Material).filter(Material.id == material_id).first()
            if not mat:
                return
            if not settings.AI_ANALYSIS_ENABLED:
                mat.ai_analysis_status = "skipped"
                mat.ai_analysis_error = "AI analysis disabled"
                db.commit()
                return

            mat.ai_analysis_status = "pending"
            mat.ai_analysis_error = None
            payload = _build_ai_payload(mat, db)
            db.commit()

            analysis, provider, model = await ai_analyze_material(payload)
            mat = db.query(Material).filter(Material.id == material_id).first()
            if mat:
                _apply_ai_analysis(mat, analysis, provider, model)
                db.commit()
        except Exception as exc:
            db.rollback()
            mat = db.query(Material).filter(Material.id == material_id).first()
            if mat:
                mat.ai_analysis_status = "failed"
                mat.ai_analysis_error = str(exc)[:1000]
                db.commit()
        finally:
            db.close()

    asyncio.run(_do())


def _build_material_response(mat: Material, db: Session, include_image: bool = False) -> dict:
    """构建素材响应，附带关联的书名和章节标题"""
    book_title = None
    chapter_title = None
    if mat.book_id:
        book = db.query(Book).filter(Book.id == mat.book_id).first()
        if book:
            book_title = book.title
        if mat.chapter_order:
            ch = db.query(Chapter).filter(
                Chapter.book_id == mat.book_id,
                Chapter.chapter_order == mat.chapter_order
            ).first()
            if ch:
                chapter_title = ch.title

    tags_list = []
    if mat.tags:
        try:
            tags_list = json.loads(mat.tags)
        except Exception:
            pass

    return {
        "id": mat.id,
        "content": mat.content,
        "source_type": mat.source_type,
        "book_id": mat.book_id,
        "chapter_order": mat.chapter_order,
        "note": mat.note,
        "tags": tags_list,
        "status": mat.status or "completed",
        "entry_mode": mat.entry_mode,
        "selected_text": mat.selected_text,
        "anchor_start": mat.anchor_start,
        "anchor_end": mat.anchor_end,
        "locator_text": mat.locator_text,
        "context_before": mat.context_before,
        "context_after": mat.context_after,
        "user_mood": mat.user_mood,
        "ai_context_summary": mat.ai_context_summary,
        "ai_interpretation": mat.ai_interpretation,
        "ai_theme_analysis": mat.ai_theme_analysis,
        "ai_possible_feelings": _json_list(mat.ai_possible_feelings),
        "ai_insight_candidates": _json_list(mat.ai_insight_candidates),
        "ai_writing_topics": _json_list(mat.ai_writing_topics),
        "ai_questions": _json_list(mat.ai_questions),
        "ai_analysis_provider": mat.ai_analysis_provider,
        "ai_analysis_model": mat.ai_analysis_model,
        "ai_analysis_status": mat.ai_analysis_status or "not_started",
        "ai_analysis_error": mat.ai_analysis_error,
        "image_data": mat.image_data if include_image else None,
        "created_at": mat.created_at,
        "updated_at": mat.updated_at,
        "book_title": book_title,
        "chapter_title": chapter_title,
    }


class MatchChapterRequest(BaseModel):
    book_id: str
    text: str


class MatchChapterResponse(BaseModel):
    matched: bool
    chapter_order: Optional[int] = None
    chapter_title: Optional[str] = None
    anchor_start: Optional[int] = None


def _match_text_in_chapters(db: Session, book_id: str, text: str) -> dict:
    """在书籍所有章节中查找原文位置，返回匹配结果"""
    if not text or not text.strip():
        return {"matched": False}

    text = text.strip()
    chapters = db.query(Chapter).filter(
        Chapter.book_id == book_id
    ).order_by(Chapter.chapter_order).all()

    # 策略1: 精确匹配
    for ch in chapters:
        content = ch.content or ""
        idx = content.find(text)
        if idx >= 0:
            return {
                "matched": True,
                "chapter_order": ch.chapter_order,
                "chapter_title": ch.title,
                "anchor_start": idx
            }

    # 策略2: 去除空白后匹配
    import re
    normalized_text = re.sub(r'\s+', '', text)
    for ch in chapters:
        content = ch.content or ""
        normalized_content = re.sub(r'\s+', '', content)
        idx = normalized_content.find(normalized_text)
        if idx >= 0:
            return {
                "matched": True,
                "chapter_order": ch.chapter_order,
                "chapter_title": ch.title,
                "anchor_start": idx
            }

    # 策略3: 取前50字作为关键词搜索
    keywords = normalized_text[:50]
    if len(keywords) >= 10:
        for ch in chapters:
            content = ch.content or ""
            normalized_content = re.sub(r'\s+', '', content)
            idx = normalized_content.find(keywords)
            if idx >= 0:
                return {
                    "matched": True,
                    "chapter_order": ch.chapter_order,
                    "chapter_title": ch.title,
                    "anchor_start": idx
                }

    return {"matched": False}


@app.post("/api/v1/materials/match-chapter", response_model=MatchChapterResponse)
async def match_chapter(
    req: MatchChapterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """根据原文内容匹配书籍章节"""
    book = db.query(Book).filter(
        Book.id == req.book_id,
        Book.user_id == current_user.id
    ).first()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    result = _match_text_in_chapters(db, req.book_id, req.text)
    return MatchChapterResponse(**result)


@app.post("/api/v1/materials", response_model=MaterialResponse, status_code=201)
async def create_material(
    req: MaterialCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建素材，标签在后台异步生成"""
    try:
        # 空字符串转 None
        if req.book_id is not None and req.book_id.strip() == "":
            req.book_id = None

        # 验证书籍归属
        if req.book_id:
            book = db.query(Book).filter(
                Book.id == req.book_id,
                Book.user_id == current_user.id
            ).first()
            if not book:
                raise HTTPException(status_code=404, detail="书籍不存在")

            # 自动匹配章节：有 selected_text + book_id 但没有 chapter_order
            if req.selected_text and req.chapter_order is None:
                match_result = _match_text_in_chapters(db, req.book_id, req.selected_text)
                if match_result["matched"]:
                    req.chapter_order = match_result["chapter_order"]
                    req.anchor_start = match_result.get("anchor_start")
                    req.anchor_end = (req.anchor_start + len(req.selected_text)) if req.anchor_start is not None else None
                    # 提取上下文
                    chapter = db.query(Chapter).filter(
                        Chapter.book_id == req.book_id,
                        Chapter.chapter_order == req.chapter_order
                    ).first()
                    if chapter and chapter.content:
                        start = req.anchor_start or 0
                        end = req.anchor_end or start
                        req.context_before = chapter.content[max(0, start - 600):start].strip()
                        req.context_after = chapter.content[end:min(len(chapter.content), end + 600)].strip()

        material = Material(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            content=req.content,
            source_type=req.source_type,
            book_id=req.book_id,
            chapter_order=req.chapter_order,
            note=req.note,
            status=req.status,
            entry_mode=req.entry_mode,
            selected_text=req.selected_text,
            anchor_start=req.anchor_start,
            anchor_end=req.anchor_end,
            locator_text=req.locator_text,
            context_before=req.context_before,
            context_after=req.context_after,
            user_mood=req.user_mood,
            image_data=req.image_data,
            ai_analysis_status="pending" if req.status == "completed" else "not_started",
        )
        db.add(material)
        db.commit()
        db.refresh(material)

        # completed 态在后台异步生成标签，不阻塞响应
        if req.status == "completed":
            background_tasks.add_task(background_analyze_material, material.id)

        logger.info(
            f"创建素材成功: material_id={material.id}, book_id={req.book_id}, "
            f"source_type={req.source_type}, content_length={len(req.content or '')}, user={current_user.username}"
        )
        return _build_material_response(material, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"创建素材失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建素材失败: {str(e)}")


@app.get("/api/v1/materials", response_model=MaterialListResponse)
async def get_materials(
    book_id: Optional[str] = None,
    chapter_order: Optional[int] = None,
    tag: Optional[str] = None,
    source_type: Optional[str] = None,
    keyword: Optional[str] = None,
    material_status: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取素材列表，支持按书籍/标签/来源/关键词/状态筛选"""
    query = db.query(Material).filter(Material.user_id == current_user.id)

    if book_id:
        query = query.filter(Material.book_id == book_id)
    if chapter_order is not None:
        query = query.filter(Material.chapter_order == chapter_order)
    if source_type:
        query = query.filter(Material.source_type == source_type)
    if keyword:
        query = query.filter(Material.content.like(f"%{keyword}%"))
    if tag:
        query = query.filter(Material.tags.like(f"%{tag}%"))
    if material_status:
        query = query.filter(Material.status == material_status)

    # draft 按 updated_at 排序，其他按 created_at
    if material_status == "draft":
        query = query.order_by(Material.updated_at.desc())
    else:
        query = query.order_by(Material.created_at.desc())

    # 先计算总数（不受 limit 影响）
    total = query.count()

    if limit:
        query = query.limit(limit)

    materials = query.all()

    items = [_build_material_response(m, db) for m in materials]

    # 如果按标签筛选，再精确过滤
    if tag:
        filtered = []
        for item in items:
            if item["tags"] and any(tag in t for t in item["tags"]):
                filtered.append(item)
        items = filtered

    return MaterialListResponse(total=total, items=items)


@app.get("/api/v1/materials/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取单个素材详情"""
    mat = db.query(Material).filter(
        Material.id == material_id,
        Material.user_id == current_user.id
    ).first()
    if not mat:
        raise HTTPException(status_code=404, detail="素材不存在")
    return _build_material_response(mat, db, include_image=True)


@app.patch("/api/v1/materials/{material_id}", response_model=MaterialResponse)
async def update_material(
    material_id: str,
    req: MaterialUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新素材"""
    mat = db.query(Material).filter(
        Material.id == material_id,
        Material.user_id == current_user.id
    ).first()
    if not mat:
        raise HTTPException(status_code=404, detail="素材不存在")

    if req.content is not None:
        mat.content = req.content
    if req.note is not None:
        mat.note = req.note
    if req.tags is not None:
        mat.tags = json.dumps(req.tags, ensure_ascii=False)
    if req.selected_text is not None:
        mat.selected_text = req.selected_text
    if req.anchor_start is not None:
        mat.anchor_start = req.anchor_start
    if req.anchor_end is not None:
        mat.anchor_end = req.anchor_end
    if req.chapter_order is not None:
        mat.chapter_order = req.chapter_order
    if req.entry_mode is not None:
        mat.entry_mode = req.entry_mode
    if req.user_mood is not None:
        mat.user_mood = req.user_mood

    # 状态从 draft 变为 completed 时，后台异步生成标签
    becoming_completed = req.status == "completed" and mat.status == "draft"

    if req.status is not None:
        mat.status = req.status

    db.commit()
    db.refresh(mat)

    if becoming_completed:
        mat.ai_analysis_status = "pending"
        db.commit()
        background_tasks.add_task(background_analyze_material, mat.id)

    return _build_material_response(mat, db)


@app.delete("/api/v1/materials/{material_id}", status_code=204)
async def delete_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除素材"""
    mat = db.query(Material).filter(
        Material.id == material_id,
        Material.user_id == current_user.id
    ).first()
    if not mat:
        raise HTTPException(status_code=404, detail="素材不存在")

    logger.info(f"删除素材成功: material_id={material_id}, book_id={mat.book_id}, user={current_user.username}")
    db.delete(mat)
    db.commit()


@app.get("/api/v1/materials/{material_id}/location")
async def get_material_location(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取素材的位置信息，用于书籍详情页高亮定位"""
    mat = db.query(Material).filter(
        Material.id == material_id,
        Material.user_id == current_user.id
    ).first()
    if not mat:
        raise HTTPException(status_code=404, detail="素材不存在")

    book_title = None
    chapter_title = None
    if mat.book_id:
        book = db.query(Book).filter(Book.id == mat.book_id).first()
        if book:
            book_title = book.title
        if mat.chapter_order:
            ch = db.query(Chapter).filter(
                Chapter.book_id == mat.book_id,
                Chapter.chapter_order == mat.chapter_order
            ).first()
            if ch:
                chapter_title = ch.title

    return {
        "book_id": mat.book_id,
        "book_title": book_title,
        "chapter_order": mat.chapter_order,
        "chapter_title": chapter_title,
        "selected_text": mat.selected_text,
        "anchor_start": mat.anchor_start,
        "anchor_end": mat.anchor_end,
        "locator_text": mat.locator_text,
    }


@app.post("/api/v1/materials/{material_id}/retag", response_model=MaterialResponse)
async def retag_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """重新生成AI标签"""
    mat = db.query(Material).filter(
        Material.id == material_id,
        Material.user_id == current_user.id
    ).first()
    if not mat:
        raise HTTPException(status_code=404, detail="素材不存在")

    tags = await ai_generate_tags(mat.content)
    mat.tags = json.dumps(tags, ensure_ascii=False) if tags else None
    db.commit()
    db.refresh(mat)
    return _build_material_response(mat, db)


# Re-run AI analysis for a saved material.
@app.post("/api/v1/materials/{material_id}/analyze", response_model=MaterialResponse)
async def analyze_material(
    material_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Queue AI material analysis with the configured multi-model route."""
    mat = db.query(Material).filter(
        Material.id == material_id,
        Material.user_id == current_user.id
    ).first()
    if not mat:
        raise HTTPException(status_code=404, detail="素材不存在")

    mat.ai_analysis_status = "pending"
    mat.ai_analysis_error = None
    db.commit()
    db.refresh(mat)
    background_tasks.add_task(background_analyze_material, mat.id)

    logger.info(f"AI分析素材已排队: material_id={material_id}, user={current_user.username}")
    return _build_material_response(mat, db)


@app.get("/api/v1/tags")
async def get_all_tags(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户所有素材的标签汇总"""
    materials = db.query(Material).filter(Material.user_id == current_user.id).all()
    tag_set = set()
    for m in materials:
        if m.tags:
            try:
                tags = json.loads(m.tags)
                tag_set.update(tags)
            except Exception:
                pass
    return {"tags": sorted(tag_set)}
