"""邮箱验证码发送服务。

使用标准库 smtplib + email，无需额外依赖。
SMTP 未配置时降级为打印到日志，便于本地调试。
"""
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import formataddr

from sqlalchemy.orm import Session

from .config import settings
from .logger import get_logger
from .models import EmailCode

logger = get_logger(__name__)


def generate_code() -> str:
    """生成 6 位数字验证码。用 secrets 而非 random，防预测。"""
    return f"{secrets.randbelow(1_000_000):06d}"


def save_code(db: Session, email: str, code: str, purpose: str = "register") -> EmailCode:
    """保存验证码到数据库，返回新建的记录。"""
    record = EmailCode(
        email=email,
        code=code,
        purpose=purpose,
        used=0,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.CODE_EXPIRE_MINUTES),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _send_email_smtp(to: str, subject: str, html: str) -> None:
    """通过 SMTP 发送 HTML 邮件。"""
    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_USER))
    msg["To"] = to
    msg["Subject"] = subject

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ctx, timeout=20) as s:
        s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.sendmail(settings.SMTP_USER, [to], msg.as_string())


def send_verification_code(to_email: str, code: str) -> bool:
    """发送注册验证码邮件。返回是否真正发出。

    SMTP 未配置时，把验证码打到日志里（方便本地调试），返回 False。
    SMTP 配置了但发送失败则抛异常，由调用方处理。
    """
    subject = f"[{settings.SMTP_FROM_NAME}] 注册验证码 {code}"
    html = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #333;">
  <div style="background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; padding: 24px; border-radius: 12px 12px 0 0;">
    <h2 style="margin: 0;">注册验证码</h2>
  </div>
  <div style="background: #fff; padding: 28px 24px; border: 1px solid #eee; border-top: none; border-radius: 0 0 12px 12px;">
    <p>您好，</p>
    <p>您正在使用此邮箱注册 <strong>{settings.SMTP_FROM_NAME}</strong> 账号。</p>
    <p style="text-align: center; margin: 24px 0;">
      <span style="font-size: 32px; letter-spacing: 8px; font-weight: 600; color: #667eea; background: #f5f3ff; padding: 12px 32px; border-radius: 8px;">{code}</span>
    </p>
    <p>验证码在 <strong>{settings.CODE_EXPIRE_MINUTES} 分钟</strong> 内有效，请勿告诉他人。</p>
    <p style="color: #999; font-size: 14px; margin-top: 24px;">
      如非本人操作，请忽略此邮件。
    </p>
  </div>
</div>
"""

    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(f"SMTP 未配置，验证码不发送。to={to_email} code={code}")
        return False

    try:
        _send_email_smtp(to_email, subject, html)
        logger.info(f"验证码邮件已发送 to={to_email}")
        return True
    except Exception:
        logger.exception(f"验证码邮件发送失败 to={to_email}")
        raise


def verify_code(db: Session, email: str, code: str, purpose: str = "register") -> tuple[bool, str]:
    """校验验证码。返回 (是否通过, 错误信息)。

    规则：
    - 找到该邮箱最新的、相同用途的、未使用的、未过期的、码匹配的记录
    - 通过后立即标记 used=1（一次性，防重放）
    - 找不到或不匹配返回 False
    """
    record = (
        db.query(EmailCode)
        .filter(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.used == 0,
        )
        .order_by(EmailCode.created_at.desc())
        .first()
    )

    if not record:
        return False, "验证码不存在或已使用"

    if record.expires_at < datetime.utcnow():
        return False, "验证码已过期"

    if record.code != code:
        return False, "验证码错误"

    # 标记已使用
    record.used = 1
    db.commit()
    return True, ""
