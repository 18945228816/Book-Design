import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import relationship

from .database import Base


class ChatRole(Base):
    """AI persona available to all users or owned by one user."""

    __tablename__ = "chat_roles"
    __table_args__ = (
        Index("idx_chat_roles_user_id", "user_id"),
        Index("idx_chat_roles_role_type", "role_type"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    avatar = Column(String(500), nullable=True)
    system_prompt = Column(Text, nullable=False)
    description = Column(String(500), nullable=True)
    role_type = Column(String(20), nullable=False, default="custom")
    book_id = Column(String(36), ForeignKey("books.id"), nullable=True, index=True)
    model_preference = Column(String(100), nullable=True)
    is_public = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    book = relationship("Book")


class ChatConversation(Base):
    """One conversation between a user and one chat role."""

    __tablename__ = "chat_conversations"
    __table_args__ = (
        Index("idx_chat_conversations_user_id", "user_id"),
        Index("idx_chat_conversations_role_id", "role_id"),
        Index("idx_chat_conversations_user_role", "user_id", "role_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("chat_roles.id"), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    category = Column(String(50), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    role = relationship("ChatRole")
    messages = relationship("ChatMessage", cascade="all, delete-orphan", back_populates="conversation")


class ChatMessage(Base):
    """A single message in a chat conversation."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_messages_conversation_id", "conversation_id"),
        Index("idx_chat_messages_created_at", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=True)
    message_type = Column(String(20), nullable=False, default="text")
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    conversation = relationship("ChatConversation", back_populates="messages")


class ChatMemory(Base):
    """Long-term memory attached to a user-role pair."""

    __tablename__ = "chat_memories"
    __table_args__ = (
        Index("idx_chat_memories_user_role", "user_id", "role_id"),
        Index("idx_chat_memories_importance", "importance"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("chat_roles.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    source_conversation_id = Column(String(36), ForeignKey("chat_conversations.id"), nullable=True)
    importance = Column(Float, default=0.5)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")
    role = relationship("ChatRole")


class ChatSummary(Base):
    """Rolling summary for one conversation or a user-role pair."""

    __tablename__ = "chat_summaries"
    __table_args__ = (
        Index("idx_chat_summaries_user_role_conv", "user_id", "role_id", "conversation_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("chat_roles.id"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("chat_conversations.id"), nullable=True, index=True)
    summary = Column(Text, nullable=False)
    message_count = Column(Integer, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    role = relationship("ChatRole")
