from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .ai_service import chat_completion
from .chat_models import ChatConversation, ChatMemory, ChatMessage, ChatRole, ChatSummary
from .logger import get_logger

logger = get_logger(__name__)


RECENT_MESSAGE_LIMIT = 40


def role_to_dict(role: ChatRole) -> dict:
    return {
        "id": role.id,
        "user_id": role.user_id,
        "name": role.name,
        "avatar": role.avatar,
        "system_prompt": role.system_prompt,
        "description": role.description,
        "role_type": role.role_type,
        "book_id": role.book_id,
        "model_preference": role.model_preference,
        "is_public": bool(role.is_public),
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def conversation_to_dict(conversation: ChatConversation, include_role: bool = True) -> dict:
    data = {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "role_id": conversation.role_id,
        "title": conversation.title,
        "category": conversation.category,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }
    if include_role and conversation.role:
        data["role"] = role_to_dict(conversation.role)
    return data


def message_to_dict(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "message_type": message.message_type,
        "image_url": message.image_url,
        "created_at": message.created_at,
    }


def get_visible_role(db: Session, role_id: str, user_id: str) -> ChatRole:
    role = db.query(ChatRole).filter(ChatRole.id == role_id).first()
    if not role or not (role.role_type == "preset" or role.user_id == user_id or role.is_public):
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def get_owned_conversation(db: Session, conversation_id: str, user_id: str) -> ChatConversation:
    conversation = db.query(ChatConversation).filter(
        ChatConversation.id == conversation_id,
        ChatConversation.user_id == user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def create_user_message(
    db: Session,
    conversation: ChatConversation,
    content: str,
    message_type: str = "text",
    image_url: Optional[str] = None,
) -> ChatMessage:
    if not content.strip() and not image_url:
        raise HTTPException(status_code=400, detail="Message content is required")

    message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
        message_type=message_type,
        image_url=image_url,
    )
    db.add(message)
    if not conversation.title:
        conversation.title = content.strip()[:20] or "New chat"
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    db.refresh(conversation)
    return message


def create_assistant_placeholder(db: Session, conversation: ChatConversation) -> ChatMessage:
    message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="",
        message_type="text",
    )
    db.add(message)
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def update_assistant_message(db: Session, message: ChatMessage, content: str):
    message.content = content
    conversation = db.query(ChatConversation).filter(ChatConversation.id == message.conversation_id).first()
    if conversation:
        conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)


def build_prompt_messages(db: Session, conversation: ChatConversation, exclude_message_id: Optional[str] = None) -> List[Dict[str, str]]:
    role = conversation.role or db.query(ChatRole).filter(ChatRole.id == conversation.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    system_parts = [role.system_prompt.strip()]

    # Inject book metadata if role is linked to a book
    if role.book_id:
        from .models import Book, Chapter
        book = db.query(Book).filter(Book.id == role.book_id).first()
        if book:
            book_info = f"Related book: \"{book.title}\""
            if book.author:
                book_info += f" by {book.author}"
            book_info += f" ({book.chapters_count} chapters)"
            chapters = db.query(Chapter).filter(Chapter.book_id == book.id).order_by(Chapter.chapter_order).limit(50).all()
            if chapters:
                toc = "\n".join(f"  - {ch.title}" for ch in chapters)
                book_info += f"\nTable of contents:\n{toc}"
            system_parts.append(book_info)

    memories = db.query(ChatMemory).filter(
        ChatMemory.user_id == conversation.user_id,
        ChatMemory.role_id == conversation.role_id,
    ).order_by(ChatMemory.importance.desc(), ChatMemory.created_at.desc()).limit(20).all()
    if memories:
        memory_text = "\n".join(f"- {item.content}" for item in memories)
        system_parts.append(f"Long-term memory about this user:\n{memory_text}")

    summary = db.query(ChatSummary).filter(
        ChatSummary.user_id == conversation.user_id,
        ChatSummary.role_id == conversation.role_id,
        ChatSummary.conversation_id == conversation.id,
    ).first()
    if summary:
        system_parts.append(f"Conversation summary so far:\n{summary.summary}")

    messages: List[Dict[str, str]] = [{"role": "system", "content": "\n\n".join(system_parts)}]
    query = db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation.id)
    if exclude_message_id:
        query = query.filter(ChatMessage.id != exclude_message_id)
    history = query.order_by(ChatMessage.created_at.desc()).limit(RECENT_MESSAGE_LIMIT).all()
    for item in reversed(history):
        if item.role not in {"user", "assistant", "system"}:
            continue
        if item.role == "assistant" and not (item.content or "").strip():
            continue
        content = item.content or ""
        if item.image_url:
            content = f"{content}\n\n[Image: {item.image_url}]".strip()
        messages.append({"role": item.role, "content": content})
    return messages


def build_prompt_with_pending_user_message(
    db: Session,
    conversation: ChatConversation,
    content: str,
    image_url: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Build prompt with an unsaved user message so failed AI calls do not pollute history."""
    messages = build_prompt_messages(db, conversation)
    pending_content = content or ""
    if image_url:
        pending_content = f"{pending_content}\n\n[Image: {image_url}]".strip()
    messages.append({"role": "user", "content": pending_content})
    return messages


def save_successful_exchange(
    db: Session,
    conversation: ChatConversation,
    user_content: str,
    assistant_content: str,
    message_type: str = "text",
    image_url: Optional[str] = None,
) -> Tuple[ChatMessage, ChatMessage]:
    """Persist both sides only after the AI call succeeds."""
    if not user_content.strip() and not image_url:
        raise HTTPException(status_code=400, detail="Message content is required")
    if not (assistant_content or "").strip():
        raise HTTPException(status_code=502, detail="AI model returned empty answer content")

    user_message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=user_content,
        message_type=message_type,
        image_url=image_url,
    )
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_content,
        message_type="text",
    )
    db.add(user_message)
    db.add(assistant_message)
    if not conversation.title:
        conversation.title = user_content.strip()[:20] or "New chat"
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    db.refresh(conversation)
    return user_message, assistant_message


def delete_messages_by_ids(db: Session, message_ids: List[str]) -> int:
    if not message_ids:
        return 0
    deleted = db.query(ChatMessage).filter(ChatMessage.id.in_(message_ids)).delete(synchronize_session=False)
    db.commit()
    return deleted


def delete_conversation_tree(db: Session, conversation: ChatConversation):
    """Delete a conversation and every table that can reference it."""
    try:
        db.execute(text("DELETE FROM chat_memories WHERE source_conversation_id = :conversation_id"), {"conversation_id": conversation.id})
        db.execute(text("DELETE FROM chat_summaries WHERE conversation_id = :conversation_id"), {"conversation_id": conversation.id})
        db.execute(text("DELETE FROM chat_messages WHERE conversation_id = :conversation_id"), {"conversation_id": conversation.id})
        db.execute(
            text("DELETE FROM chat_conversations WHERE id = :conversation_id AND user_id = :user_id"),
            {"conversation_id": conversation.id, "user_id": conversation.user_id},
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete conversation: {exc}") from exc


def list_failed_conversation_ids(db: Session, user_id: str) -> List[str]:
    """Find conversations polluted by failed assistant placeholders from earlier implementations."""
    rows = db.execute(
        text("""
            SELECT DISTINCT c.id
            FROM chat_conversations c
            JOIN chat_messages m ON m.conversation_id = c.id
            WHERE c.user_id = :user_id
              AND m.role = 'assistant'
              AND (
                m.content IS NULL
                OR TRIM(m.content) = ''
                OR m.content LIKE 'AI response failed:%'
              )
        """),
        {"user_id": user_id},
    ).fetchall()
    return [row[0] for row in rows]


def delete_failed_conversations(db: Session, user_id: str) -> int:
    """Delete only the user's historical failed chat conversations."""
    conversation_ids = list_failed_conversation_ids(db, user_id)
    deleted = 0
    for conversation_id in conversation_ids:
        conversation = get_owned_conversation(db, conversation_id, user_id)
        delete_conversation_tree(db, conversation)
        deleted += 1
    return deleted


def delete_from_message(db: Session, message_id: str, user_id: str) -> Tuple[ChatConversation, ChatMessage]:
    message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    conversation = get_owned_conversation(db, message.conversation_id, user_id)

    later_messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation.id,
        ChatMessage.created_at >= message.created_at,
    ).all()
    for item in later_messages:
        db.delete(item)
    conversation.updated_at = datetime.utcnow()
    db.commit()
    return conversation, message


def accessible_roles_query(db: Session, user_id: str):
    return db.query(ChatRole).filter(
        (ChatRole.role_type == "preset") |
        (ChatRole.user_id == user_id) |
        (ChatRole.is_public == 1)
    )


# ========== Memory & Summary Automation ==========

MEMORY_LIMIT_PER_ROLE = 50
SUMMARY_TRIGGER_ROUNDS = 10


async def extract_memories_async(
    db: Session,
    conversation: ChatConversation,
    user_message: ChatMessage,
    assistant_message: ChatMessage,
):
    """Extract key facts from the latest exchange and store as memories."""
    try:
        recent_messages = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation.id,
        ).order_by(ChatMessage.created_at.desc()).limit(10).all()
        recent_messages.reverse()

        dialog_text = "\n".join(
            f"{'User' if m.role == 'user' else 'AI'}: {m.content or ''}"
            for m in recent_messages
            if m.role in ("user", "assistant") and (m.content or "").strip()
        )
        if not dialog_text.strip():
            return

        extraction_prompt = [
            {"role": "system", "content": (
                "You are a memory extraction assistant. Analyze the conversation and extract key facts about the user. "
                "Return a JSON array where each item has 'content' (the fact, in the same language as the conversation) "
                "and 'importance' (0.0-1.0). Only extract NEW information not obvious from context. "
                "Return [] if nothing noteworthy. Return ONLY the JSON array, no explanation."
            )},
            {"role": "user", "content": dialog_text},
        ]

        response = await chat_completion(extraction_prompt, temperature=0.3)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        import json as _json
        try:
            facts = _json.loads(response)
        except _json.JSONDecodeError:
            return

        if not isinstance(facts, list) or not facts:
            return

        for item in facts:
            content = (item.get("content") or "").strip()
            importance = float(item.get("importance", 0.5))
            if not content:
                continue
            importance = max(0.0, min(1.0, importance))
            db.add(ChatMemory(
                user_id=conversation.user_id,
                role_id=conversation.role_id,
                content=content,
                source_conversation_id=conversation.id,
                importance=importance,
            ))

        db.commit()
        _enforce_memory_limit(db, conversation.user_id, conversation.role_id)
    except Exception as exc:
        db.rollback()
        logger.error(f"记忆提取失败: {exc}")


def _enforce_memory_limit(db: Session, user_id: str, role_id: str):
    """Keep at most MEMORY_LIMIT_PER_ROLE memories per user-role pair."""
    count = db.query(ChatMemory).filter(
        ChatMemory.user_id == user_id,
        ChatMemory.role_id == role_id,
    ).count()
    if count <= MEMORY_LIMIT_PER_ROLE:
        return
    to_remove = count - MEMORY_LIMIT_PER_ROLE
    oldest = db.query(ChatMemory).filter(
        ChatMemory.user_id == user_id,
        ChatMemory.role_id == role_id,
    ).order_by(ChatMemory.importance.asc(), ChatMemory.created_at.asc()).limit(to_remove).all()
    for item in oldest:
        db.delete(item)
    db.commit()


async def update_summary_async(db: Session, conversation: ChatConversation):
    """Update the rolling conversation summary every SUMMARY_TRIGGER_ROUNDS."""
    try:
        total_messages = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.role.in_(["user", "assistant"]),
        ).count()
        if total_messages == 0 or total_messages % (SUMMARY_TRIGGER_ROUNDS * 2) != 0:
            return

        existing = db.query(ChatSummary).filter(
            ChatSummary.user_id == conversation.user_id,
            ChatSummary.role_id == conversation.role_id,
            ChatSummary.conversation_id == conversation.id,
        ).first()

        all_messages = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.role.in_(["user", "assistant"]),
        ).order_by(ChatMessage.created_at.asc()).all()

        dialog_text = "\n".join(
            f"{'User' if m.role == 'user' else 'AI'}: {m.content or ''}"
            for m in all_messages
            if (m.content or "").strip()
        )

        old_summary = existing.summary if existing else ""
        prompt_content = (
            f"Previous summary:\n{old_summary}\n\n"
            f"Full conversation:\n{dialog_text}\n\n"
            "Please update the summary by integrating new information. "
            "Keep it concise but comprehensive. Use the same language as the conversation."
        )

        summary_prompt = [
            {"role": "system", "content": "You are a conversation summarizer. Update the summary by integrating new dialogue into the existing summary. Be concise but capture key points, decisions, and context."},
            {"role": "user", "content": prompt_content},
        ]

        new_summary = await chat_completion(summary_prompt, temperature=0.3)

        if existing:
            existing.summary = new_summary
            existing.message_count = total_messages
            existing.updated_at = datetime.utcnow()
        else:
            db.add(ChatSummary(
                user_id=conversation.user_id,
                role_id=conversation.role_id,
                conversation_id=conversation.id,
                summary=new_summary,
                message_count=total_messages,
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"摘要更新失败: {exc}")
