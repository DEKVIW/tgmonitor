"""
管理相关的 Pydantic Schema
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class CredentialResponse(BaseModel):
    """API凭据响应"""
    id: int
    api_id: str
    api_hash: str

    class Config:
        from_attributes = True


class CredentialCreate(BaseModel):
    """创建API凭据请求"""
    api_id: str
    api_hash: str


class ChannelResponse(BaseModel):
    """频道响应"""
    id: int
    username: str

    class Config:
        from_attributes = True


class ChannelCreate(BaseModel):
    """创建频道请求"""
    username: str


class SystemConfigResponse(BaseModel):
    """系统配置响应"""
    public_dashboard_enabled: bool


class SystemConfigUpdate(BaseModel):
    """更新系统配置请求"""
    public_dashboard_enabled: bool


class UserResponse(BaseModel):
    """用户响应"""
    username: str
    name: str
    email: str
    role: str


class UserCreate(BaseModel):
    """创建用户请求"""
    username: str
    password: str
    name: str = ""
    email: str = ""
    role: str = "user"


class UserUpdate(BaseModel):
    """更新用户请求"""
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


class PasswordChange(BaseModel):
    """修改密码请求"""
    new_password: str


class UsernameChange(BaseModel):
    """修改用户名请求"""
    new_username: str


class RoleChange(BaseModel):
    """修改角色请求"""
    new_role: str


class BulkRandomCreateRequest(BaseModel):
    """批量随机创建用户请求"""
    count: int = 10
    prefix: str = "user"
    start_index: int = 1
    role: str = "user"
    password_length: int = 12


class BulkRandomCreateResult(BaseModel):
    username: str
    password: str
    role: str


class BulkFailure(BaseModel):
    username: Optional[str] = None
    reason: str


class BulkCreateResponse(BaseModel):
    successes: List[BulkRandomCreateResult]
    failures: List[BulkFailure]


class BulkUsernamesRequest(BaseModel):
    usernames: List[str]
    password_length: Optional[int] = 12  # 仅在重置密码时使用


class BulkResetResult(BaseModel):
    username: str
    password: str


class BulkSimpleResponse(BaseModel):
    successes: List[Any]
    failures: List[BulkFailure]


class MaintenanceResult(BaseModel):
    """数据维护结果"""
    success: bool
    fixed_count: Optional[int] = None
    deleted_count: Optional[int] = None
    deleted_details: Optional[int] = None
    deleted_stats: Optional[int] = None
    cutoff_time: Optional[str] = None
    errors: Optional[List[str]] = None
    error: Optional[str] = None


class ClearOldDataRequest(BaseModel):
    """清空旧数据请求"""
    days: int = 30


class ChannelDiagnosisResult(BaseModel):
    """频道诊断结果"""
    valid_channels: List[Dict[str, Any]]
    invalid_channels: List[Dict[str, Any]]


class MonitorTestResult(BaseModel):
    """监控测试结果"""
    success: bool
    channels_tested: Optional[int] = None
    message_received: Optional[bool] = None
    message: Optional[str] = None
    error: Optional[str] = None


class LinkCheckTaskCreate(BaseModel):
    """创建链接检测任务请求"""
    period: str  # 时间段：today, yesterday, week, month, year, 或日期格式
    max_concurrent: int = 5


class LinkCheckTaskStatus(BaseModel):
    """链接检测任务状态"""
    task_id: str
    status: str  # running, completed, failed
    progress: int
    period_desc: Optional[str] = None
    total_links: Optional[int] = None
    checked_links: Optional[int] = None
    valid_links: Optional[int] = None
    invalid_links: Optional[int] = None
    check_time: Optional[str] = None
    duration: Optional[float] = None
    logs: Optional[List[str]] = None
    error: Optional[str] = None


class LinkCheckTaskHistory(BaseModel):
    """链接检测任务历史"""
    id: int
    check_time: str
    total_messages: int
    total_links: int
    valid_links: int
    invalid_links: int
    status: str
    duration: Optional[float] = None


class LinkCheckTaskResult(BaseModel):
    """链接检测任务结果"""
    stats: Dict[str, Any]
    details: List[Dict[str, Any]]

