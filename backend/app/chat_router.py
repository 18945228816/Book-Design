import json
import time
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import chat_service
from .ai_service import chat_completion, chat_completion_stream
from .chat_models import ChatConversation, ChatMemory, ChatMessage, ChatRole
from .chat_schemas import (
    ChatMemoryResponse,
    ChatMessageCreate,
    ChatRoleCreate,
    ChatRoleResponse,
    ChatRoleUpdate,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageListResponse,
    ResendMessageRequest,
    SyncChatResponse,
)
from .config import settings
from .database import get_db, SessionLocal
from .logger import get_logger
from .models import User

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
security = HTTPBearer()


def get_current_chat_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _streaming_response(generator):
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _run_chat_post_processing(conversation_id: str, user_message_id: str, assistant_message_id: str):
    stream_db = SessionLocal()
    try:
        conv = stream_db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
        user_msg = stream_db.query(ChatMessage).filter(ChatMessage.id == user_message_id).first()
        assistant_msg = stream_db.query(ChatMessage).filter(ChatMessage.id == assistant_message_id).first()
        if conv and user_msg and assistant_msg:
            await chat_service.extract_memories_async(stream_db, conv, user_msg, assistant_msg)
            await chat_service.update_summary_async(stream_db, conv)
    except Exception as exc:
        logger.error(f"对话后处理失败: conversation_id={conversation_id}, error={exc}")
    finally:
        stream_db.close()


@router.get("/roles", response_model=list[ChatRoleResponse])
async def list_roles(
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    roles = chat_service.accessible_roles_query(db, current_user.id).order_by(
        ChatRole.role_type.desc(),
        ChatRole.created_at.asc(),
    ).all()
    return [chat_service.role_to_dict(role) for role in roles]


@router.post("/roles", response_model=ChatRoleResponse, status_code=201)
async def create_role(
    req: ChatRoleCreate,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    role = ChatRole(
        user_id=current_user.id,
        name=req.name,
        avatar=req.avatar,
        system_prompt=req.system_prompt,
        description=req.description,
        role_type="custom",
        book_id=req.book_id,
        model_preference=req.model_preference,
        is_public=1 if req.is_public else 0,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return chat_service.role_to_dict(role)


@router.get("/roles/{role_id}", response_model=ChatRoleResponse)
async def get_role(
    role_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    role = chat_service.get_visible_role(db, role_id, current_user.id)
    return chat_service.role_to_dict(role)


@router.patch("/roles/{role_id}", response_model=ChatRoleResponse)
async def update_role(
    role_id: str,
    req: ChatRoleUpdate,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    role = db.query(ChatRole).filter(
        ChatRole.id == role_id,
        ChatRole.user_id == current_user.id,
        ChatRole.role_type == "custom",
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Custom role not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(role, field, 1 if field == "is_public" and value else value)
    db.commit()
    db.refresh(role)
    return chat_service.role_to_dict(role)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    role = db.query(ChatRole).filter(
        ChatRole.id == role_id,
        ChatRole.user_id == current_user.id,
        ChatRole.role_type == "custom",
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Custom role not found")
    db.delete(role)
    db.commit()


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    role_id: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    query = db.query(ChatConversation).filter(ChatConversation.user_id == current_user.id)
    if role_id:
        query = query.filter(ChatConversation.role_id == role_id)
    if category:
        query = query.filter(ChatConversation.category == category)
    conversations = query.order_by(ChatConversation.updated_at.desc(), ChatConversation.created_at.desc()).all()
    return [chat_service.conversation_to_dict(item) for item in conversations]


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    req: ConversationCreate,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    chat_service.get_visible_role(db, req.role_id, current_user.id)
    conversation = ChatConversation(
        user_id=current_user.id,
        role_id=req.role_id,
        title=req.title,
        category=req.category,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    logger.info(f"创建对话成功: conversation_id={conversation.id}, role_id={req.role_id}, user={current_user.username}")
    return chat_service.conversation_to_dict(conversation)


@router.delete("/conversations/failed", status_code=200)
async def delete_failed_conversations(
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    deleted = chat_service.delete_failed_conversations(db, current_user.id)
    return {"deleted": deleted}


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    messages = db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.created_at.asc()).all()
    data = chat_service.conversation_to_dict(conversation)
    data["messages"] = [chat_service.message_to_dict(item) for item in messages]
    return data


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    req: ConversationUpdate,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    if req.title is not None:
        conversation.title = req.title
    if req.category is not None:
        conversation.category = req.category
    db.commit()
    db.refresh(conversation)
    return chat_service.conversation_to_dict(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    chat_service.delete_conversation_tree(db, conversation)

    logger.info(f"删除对话成功: conversation_id={conversation_id}, user={current_user.username}")


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    query = db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation.id)
    if cursor:
        query = query.filter(ChatMessage.id < cursor)
    items = query.order_by(ChatMessage.created_at.desc()).limit(limit + 1).all()
    next_cursor = items[-1].id if len(items) > limit else None
    items = list(reversed(items[:limit]))
    return {"items": [chat_service.message_to_dict(item) for item in items], "next_cursor": next_cursor}


@router.post("/conversations/{conversation_id}/messages")
async def send_message_stream(
    conversation_id: str,
    req: ChatMessageCreate,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    user_message = chat_service.create_user_message(db, conversation, req.content, req.message_type, req.image_url)
    assistant_message = chat_service.create_assistant_placeholder(db, conversation)
    prompt_messages = chat_service.build_prompt_messages(db, conversation, exclude_message_id=assistant_message.id)
    model_preference = req.preferred_model or (conversation.role.model_preference if conversation.role else None)

    saved_user_message = chat_service.message_to_dict(user_message)
    saved_assistant_id = assistant_message.id
    conversation_id = conversation.id
    stream_start = time.time()

    logger.info(
        f"发送消息: conversation_id={conversation_id}, message_type={req.message_type}, "
        f"content_length={len(req.content or '')}, model={model_preference or 'default'}, user={current_user.username}"
    )

    async def event_stream():
        # Use a dedicated session that lives for the full streaming duration
        stream_db = SessionLocal()
        full_content = ""
        yield _sse({
            "type": "start",
            "message_id": saved_assistant_id,
            "user_message": saved_user_message,
        })
        try:
            async for chunk in chat_completion_stream(prompt_messages, preferred_model=model_preference):
                full_content += chunk
                yield _sse({"type": "delta", "content": chunk})
            if not full_content.strip():
                raise ValueError("AI model returned empty answer content")
            assistant_msg = stream_db.query(ChatMessage).filter(ChatMessage.id == saved_assistant_id).first()
            if assistant_msg:
                chat_service.update_assistant_message(stream_db, assistant_msg, full_content)
            elapsed = int((time.time() - stream_start) * 1000)
            logger.info(
                f"流式回复完成: conversation_id={conversation_id}, 回复长度={len(full_content)}, 耗时={elapsed}ms"
            )
            yield _sse({"type": "done", "full_content": full_content})
            asyncio.create_task(_run_chat_post_processing(conversation_id, saved_user_message["id"], saved_assistant_id))
        except Exception as exc:
            elapsed = int((time.time() - stream_start) * 1000)
            logger.error(f"流式回复失败: conversation_id={conversation_id}, error={exc}, 耗时={elapsed}ms")
            chat_service.delete_messages_by_ids(stream_db, [saved_user_message["id"], saved_assistant_id])
            yield _sse({"type": "error", "message": str(exc), "full_content": ""})
        yield "data: [DONE]\n\n"
        stream_db.close()

    return _streaming_response(event_stream())


@router.post("/conversations/{conversation_id}/messages/sync", response_model=SyncChatResponse)
async def send_message_sync(
    conversation_id: str,
    req: ChatMessageCreate,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    prompt_messages = chat_service.build_prompt_with_pending_user_message(db, conversation, req.content, req.image_url)
    model_preference = req.preferred_model or (conversation.role.model_preference if conversation.role else None)
    try:
        content = await chat_completion(prompt_messages, preferred_model=model_preference)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI model call failed: {exc}")
    user_message, assistant_message = chat_service.save_successful_exchange(
        db,
        conversation,
        req.content,
        content,
        req.message_type,
        req.image_url,
    )

    asyncio.create_task(_run_chat_post_processing(conversation.id, user_message.id, assistant_message.id))

    return {
        "user_message": chat_service.message_to_dict(user_message),
        "assistant_message": chat_service.message_to_dict(assistant_message),
    }


@router.delete("/messages/{message_id}/from-here", status_code=204)
async def delete_messages_from_here(
    message_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    chat_service.delete_from_message(db, message_id, current_user.id)


@router.post("/conversations/{conversation_id}/messages/{message_id}/resend")
async def resend_message_stream(
    conversation_id: str,
    message_id: str,
    req: ResendMessageRequest,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    if conversation.id != conversation_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    chat_service.delete_from_message(db, message_id, current_user.id)
    new_req = ChatMessageCreate(content=req.content)
    return await send_message_stream(conversation_id, new_req, current_user, db)


@router.get("/roles/{role_id}/memories", response_model=list[ChatMemoryResponse])
async def list_memories(
    role_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    chat_service.get_visible_role(db, role_id, current_user.id)
    memories = db.query(ChatMemory).filter(
        ChatMemory.user_id == current_user.id,
        ChatMemory.role_id == role_id,
    ).order_by(ChatMemory.importance.desc(), ChatMemory.created_at.desc()).all()
    return memories


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    memory = db.query(ChatMemory).filter(
        ChatMemory.id == memory_id,
        ChatMemory.user_id == current_user.id,
    ).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(memory)
    db.commit()


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("md", regex="^(md|txt)$"),
    current_user: User = Depends(get_current_chat_user),
    db: Session = Depends(get_db),
):
    conversation = chat_service.get_owned_conversation(db, conversation_id, current_user.id)
    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation.id,
    ).order_by(ChatMessage.created_at.asc()).all()

    role_name = conversation.role.name if conversation.role else "AI"
    title = conversation.title or "Conversation"
    lines = [f"# {title}\n"]

    for msg in messages:
        if msg.role == "system":
            continue
        speaker = "You" if msg.role == "user" else role_name
        content = msg.content or ""
        if msg.image_url:
            content = f"{content}\n\n[Image: {msg.image_url}]".strip()
        if format == "md":
            lines.append(f"**{speaker}:**\n\n{content}\n")
        else:
            lines.append(f"{speaker}: {content}\n")
        lines.append("---\n" if format == "md" else "")

    from fastapi.responses import PlainTextResponse
    ext = "md" if format == "md" else "txt"
    media = "text/markdown" if format == "md" else "text/plain"
    return PlainTextResponse(
        "\n".join(lines),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{title}.{ext}"'},
    )
