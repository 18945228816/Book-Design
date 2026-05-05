from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Float, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship
import uuid
from .database import Base


class Material(Base):
    """User material, quote, or reading note."""
    __tablename__ = "materials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    content = Column(MEDIUMTEXT, nullable=False)
    source_type = Column(String(20), nullable=False)
    book_id = Column(String(36), ForeignKey("books.id"), nullable=True, index=True)
    chapter_order = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="completed")
    entry_mode = Column(String(50), nullable=True)
    selected_text = Column(Text, nullable=True)
    anchor_start = Column(Integer, nullable=True)
    anchor_end = Column(Integer, nullable=True)
    locator_text = Column(String(255), nullable=True)
    context_before = Column(Text, nullable=True)
    context_after = Column(Text, nullable=True)
    user_mood = Column(String(50), nullable=True)
    ai_context_summary = Column(Text, nullable=True)
    ai_interpretation = Column(MEDIUMTEXT, nullable=True)
    ai_theme_analysis = Column(Text, nullable=True)
    ai_possible_feelings = Column(Text, nullable=True)
    ai_insight_candidates = Column(Text, nullable=True)
    ai_writing_topics = Column(Text, nullable=True)
    ai_questions = Column(Text, nullable=True)
    ai_analysis_provider = Column(String(50), nullable=True)
    ai_analysis_model = Column(String(100), nullable=True)
    ai_analysis_status = Column(String(20), nullable=False, default="not_started")
    ai_analysis_error = Column(Text, nullable=True)
    image_data = Column(MEDIUMTEXT, nullable=True)  # base64 截图数据
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    book = relationship("Book")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    books = relationship("Book", back_populates="user")


class Book(Base):
    __tablename__ = "books"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    author = Column(String(200))
    file_type = Column(String(10), nullable=False)
    chapters_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="books")
    chapters = relationship("Chapter", back_populates="book", order_by="Chapter.chapter_order")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id = Column(String(36), ForeignKey("books.id"), nullable=False, index=True)
    title = Column(String(500))
    content = Column(MEDIUMTEXT, nullable=False)
    chapter_order = Column(Integer, nullable=False)
    level = Column(Integer, default=1)
    parent_title = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    book = relationship("Book", back_populates="chapters")


class ReadingProgress(Base):
    """Last reading position for a user-book pair."""
    __tablename__ = "reading_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_reading_progress_user_book"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    book_id = Column(String(36), ForeignKey("books.id"), nullable=False, index=True)
    chapter_order = Column(Integer, nullable=False)
    scroll_top = Column(Integer, default=0)
    scroll_ratio = Column(Float, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    book = relationship("Book")


class AIProvider(Base):
    """Configurable AI provider such as Sensenova, DeepSeek, Qwen, Doubao, OpenAI."""
    __tablename__ = "ai_providers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_key = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=False)
    api_key = Column(Text, nullable=True)
    enabled = Column(Integer, default=1)
    is_default = Column(Integer, default=0)
    last_test_status = Column(String(20), nullable=True)
    last_test_error = Column(Text, nullable=True)
    last_test_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    models = relationship("AIModel", back_populates="provider")


class AIModel(Base):
    """One callable model under an AI provider."""
    __tablename__ = "ai_models"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String(36), ForeignKey("ai_providers.id"), nullable=False, index=True)
    model_key = Column(String(150), nullable=False)
    display_name = Column(String(150), nullable=False)
    model_type = Column(String(50), nullable=False, default="chat")
    endpoint_path = Column(String(300), nullable=True)
    capability_json = Column(Text, nullable=True)
    context_window = Column(Integer, nullable=True)
    enabled = Column(Integer, default=1)
    priority = Column(Integer, default=100)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    provider = relationship("AIProvider", back_populates="models")


class AITaskRoute(Base):
    """Ordered fallback route for one AI task type."""
    __tablename__ = "ai_task_routes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type = Column(String(80), nullable=False, index=True)
    provider_id = Column(String(36), ForeignKey("ai_providers.id"), nullable=False, index=True)
    model_id = Column(String(36), ForeignKey("ai_models.id"), nullable=False, index=True)
    route_order = Column(Integer, default=1)
    strategy = Column(String(50), default="quality_first")
    timeout_seconds = Column(Integer, default=30)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    provider = relationship("AIProvider")
    model = relationship("AIModel")


class AICallLog(Base):
    """A lightweight log for AI provider calls."""
    __tablename__ = "ai_call_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    material_id = Column(String(36), ForeignKey("materials.id"), nullable=True, index=True)
    task_type = Column(String(80), nullable=False, index=True)
    provider_key = Column(String(50), nullable=True)
    model_key = Column(String(150), nullable=True)
    status = Column(String(20), nullable=False)
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
