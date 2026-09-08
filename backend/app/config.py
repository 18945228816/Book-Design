from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "zhewww7768"
    DB_NAME: str = "book_design"

    SECRET_KEY: str = "your-secret-key-change-this"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    AI_API_KEY: str = ""
    AI_API_BASE_URL: str = "https://hk.xty.app/v1"
    AI_MODEL: str = "gpt-3.5-turbo"
    AI_ANALYSIS_ENABLED: bool = True
    AI_REQUEST_TIMEOUT: int = 30
    AI_DEFAULT_PROVIDER: str = "sensenova"
    AI_TASK_ROUTE_DEFAULT: str = "sensenova,zhipu,deepseek,qwen,doubao,openai,legacy"
    AI_TASK_ROUTE_TAG_GENERATION: str = "sensenova,zhipu,qwen,deepseek,doubao,openai,legacy"
    AI_TASK_ROUTE_MATERIAL_ANALYSIS: str = "sensenova,zhipu,deepseek,qwen,doubao,openai,legacy"
    AI_TASK_ROUTE_CHAT_COMPLETION: str = "sensenova,zhipu,deepseek,qwen,doubao,openai,legacy"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    DOUBAO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    DOUBAO_MODEL: str = "doubao-pro-32k"

    SENSENOVA_API_KEY: str = ""
    SENSENOVA_BASE_URL: str = "https://token.sensenova.cn/v1"
    SENSENOVA_TEXT_MODEL: str = "deepseek-v4-flash"
    SENSENOVA_IMAGE_MODEL: str = "sensenova-u1-fast"
    SENSENOVA_VISION_MODEL: str = "sensenova-6.7-flash-lite"

    ZHIPU_API_KEY: str = ""
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_MODEL: str = "glm-5.1"

    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    LOG_RETENTION_DAYS: int = 30

    # 邮件发送（注册验证码）
    SMTP_HOST: str = "smtp.qq.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "读书感悟记录系统"
    CODE_EXPIRE_MINUTES: int = 10
    CODE_RESEND_SECONDS: int = 60

    @property
    def AI_TASK_ROUTES(self) -> dict:
        return {
            "default": [item.strip() for item in self.AI_TASK_ROUTE_DEFAULT.split(",") if item.strip()],
            "tag_generation": [item.strip() for item in self.AI_TASK_ROUTE_TAG_GENERATION.split(",") if item.strip()],
            "material_analysis": [item.strip() for item in self.AI_TASK_ROUTE_MATERIAL_ANALYSIS.split(",") if item.strip()],
            "chat_completion": [item.strip() for item in self.AI_TASK_ROUTE_CHAT_COMPLETION.split(",") if item.strip()],
        }

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    class Config:
        env_file = (".env", "backend/.env")
        extra = "ignore"


settings = Settings()
