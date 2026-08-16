"""认证与用户画像：注册/登录/JWT/用户偏好、登录频率限制。

- 密码哈希：标准库 hashlib.pbkdf2_hmac（无额外依赖）
- Token：PyJWT，HS256，7 天有效期
- 登录频率限制：5次失败后锁定15分钟（内存计数器，重启清零）
- LLM Key 加密：AES-256-GCM（同机部署，防DB泄露后key被直接读取）

本包由原 app/auth.py 拆分而来，对外 API 保持完全兼容：
所有原公开符号（含 _connect/_init_db 等私有符号与 DB_PATH）均在此 re-export。
"""
from __future__ import annotations

from ..config import DB_PATH
from ._db import _connect, _init_db
from .crypto import (
    _get_enc_key,
    _get_secret,
    decrypt_key,
    encrypt_key,
    hash_password,
    totp_code,
    verify_password,
    verify_totp,
)
from .tokens import (
    JWT_ALGO,
    TOKEN_TTL,
    consume_auth_token,
    create_token,
    decode_token,
    issue_auth_token,
)
from .ratelimit import (
    LOCK_DURATION,
    MAX_LOGIN_FAILS,
    _login_attempts,
    check_rate_limit,
    record_login_fail,
    record_login_success,
)
from .llm_config import (
    _mask_key,
    get_effective_llm_config,
    get_user_llm_config,
    save_user_llm_config,
)
from .users import (
    AGREEMENT_VERSION,
    authenticate,
    change_password,
    create_user,
    get_mfa_secret,
    get_or_create_oauth_user,
    get_profile,
    get_security_profile,
    get_user,
    record_agreement_consent,
    set_email_verified,
    set_mfa,
    set_user_email,
    update_profile,
)
from .usage import (
    FREE_MONTHLY_MODEL_LIMIT,
    _usage_month,
    consume_model_usage,
    get_model_usage,
    has_membership,
)
from .admin import (
    audit_log,
    create_invite_code,
    delete_user,
    get_system_stats,
    is_admin,
    list_all_users,
    list_audit_logs,
    list_invite_codes,
    set_user_admin,
    toggle_user_active,
)

__all__ = [
    "DB_PATH",
    "_connect",
    "_init_db",
    "_get_secret",
    "_get_enc_key",
    "encrypt_key",
    "decrypt_key",
    "hash_password",
    "verify_password",
    "totp_code",
    "verify_totp",
    "JWT_ALGO",
    "TOKEN_TTL",
    "create_token",
    "decode_token",
    "issue_auth_token",
    "consume_auth_token",
    "_login_attempts",
    "MAX_LOGIN_FAILS",
    "LOCK_DURATION",
    "check_rate_limit",
    "record_login_fail",
    "record_login_success",
    "_mask_key",
    "get_user_llm_config",
    "get_effective_llm_config",
    "save_user_llm_config",
    "AGREEMENT_VERSION",
    "create_user",
    "authenticate",
    "get_user",
    "get_or_create_oauth_user",
    "set_user_email",
    "get_security_profile",
    "set_email_verified",
    "set_mfa",
    "get_mfa_secret",
    "record_agreement_consent",
    "get_profile",
    "update_profile",
    "change_password",
    "FREE_MONTHLY_MODEL_LIMIT",
    "_usage_month",
    "has_membership",
    "get_model_usage",
    "consume_model_usage",
    "is_admin",
    "list_all_users",
    "delete_user",
    "toggle_user_active",
    "set_user_admin",
    "create_invite_code",
    "list_invite_codes",
    "audit_log",
    "list_audit_logs",
    "get_system_stats",
]
