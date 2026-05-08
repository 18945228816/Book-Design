from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ChatRoleBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str
    avatar: Optional[str] = None
    system_prompt: str
    description: Optional[str] = None
    book_id: Optional[str] = None
    model_preference: Optional[str] = None
    is_public: bool = False


class ChatRoleCreate(ChatRoleBase):
    pass


class ChatRoleUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: Optional[str] = None
    avatar: Optional[str] = None
    system_prompt: Optional[str] = None
    description: Optional[str] = None
    book_id: Optional[str] = None
    model_preference: Optional[str] = None
    is_public: Optional[bool] = None


class ChatRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    user_id: Optional[str] = None
    name: str
    avatar: Optional[str] = None
    system_prompt: str
    description: Optional[str] = None
    role_type: str
    book_id: Optional[str] = None
    model_preference: Optional[str] = None
    is_public: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ConversationCreate(BaseModel):
    role_id: str
    title: Optional[str] = None
    category: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    role_id: str
    title: Optional[str] = None
    category: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    role: Optional[ChatRoleResponse] = None


class ChatMessageCreate(BaseModel):
    content: str
    message_type: str = "text"
    image_url: Optional[str] = None
    preferred_model: Optional[str] = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: Optional[str] = None
    message_type: str = "text"
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None


class ConversationDetailResponse(ConversationResponse):
    messages: List[ChatMessageResponse] = []


class MessageListResponse(BaseModel):
    items: List[ChatMessageResponse]
    next_cursor: Optional[str] = None


class SyncChatResponse(BaseModel):
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse


class ChatMemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    role_id: str
    content: str
    source_conversation_id: Optional[str] = None
    importance: float = 0.5
    created_at: Optional[datetime] = None


class ResendMessageRequest(BaseModel):
    content: str
