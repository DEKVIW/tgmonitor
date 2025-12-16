"""
管理相关 API 路由
包括API凭据管理和频道管理
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.schemas.admin import (
    CredentialResponse,
    CredentialCreate,
    ChannelResponse,
    ChannelCreate,
    SystemConfigResponse,
    SystemConfigUpdate,
    UserResponse,
    UserCreate,
    UserUpdate,
    PasswordChange,
    UsernameChange,
    RoleChange,
    BulkRandomCreateRequest,
    BulkCreateResponse,
    BulkUsernamesRequest,
    BulkSimpleResponse,
    BulkResetResult,
    MaintenanceResult,
    ClearOldDataRequest
)
from app.models.models import Credential, Channel
from app.api.dependencies import get_db, get_current_user, get_admin_user
from app.models.config import settings
from app.services.user_service import (
    list_users,
    get_user,
    add_user,
    update_user,
    change_password,
    change_username,
    change_user_role,
    remove_user,
    get_available_roles,
    bulk_create_random_users,
    bulk_remove_users,
    bulk_reset_passwords,
    export_users
)
from app.services.maintenance_service import (
    fix_tags,
    dedup_links,
    clear_link_check_data,
    clear_old_link_check_data
)
from app.services.channel_service import (
    diagnose_channels,
    test_monitor
)
from app.services.link_check_service import (
    run_link_check_task,
    get_task_status,
    get_task_history,
    get_task_result
)
from app.schemas.admin import (
    ChannelDiagnosisResult,
    MonitorTestResult,
    LinkCheckTaskCreate,
    LinkCheckTaskStatus,
    LinkCheckTaskHistory,
    LinkCheckTaskResult
)
import uuid
from typing import Dict, Any, List
import os

router = APIRouter(prefix="/api/admin", tags=["管理"])


# ========== API凭据管理 ==========

@router.get("/credentials", response_model=List[CredentialResponse], summary="获取API凭据列表")
async def get_credentials(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> List[CredentialResponse]:
    """
    获取所有API凭据列表
    
    需要 Bearer Token 认证
    """
    try:
        credentials = db.query(Credential).all()
        return [CredentialResponse.from_orm(cred) for cred in credentials]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取API凭据列表失败: {str(e)}"
        )


@router.post("/credentials", response_model=CredentialResponse, summary="添加API凭据")
async def create_credential(
    credential_data: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> CredentialResponse:
    """
    添加新的API凭据
    
    需要 Bearer Token 认证
    """
    try:
        # 检查是否已存在相同的api_id
        existing = db.query(Credential).filter(Credential.api_id == credential_data.api_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API ID {credential_data.api_id} 已存在"
            )
        
        credential = Credential(
            api_id=credential_data.api_id,
            api_hash=credential_data.api_hash
        )
        db.add(credential)
        db.commit()
        db.refresh(credential)
        
        return CredentialResponse.from_orm(credential)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加API凭据失败: {str(e)}"
        )


@router.delete("/credentials/{credential_id}", summary="删除API凭据")
async def delete_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    删除指定的API凭据
    
    需要 Bearer Token 认证
    """
    try:
        credential = db.query(Credential).filter(Credential.id == credential_id).first()
        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API凭据 {credential_id} 不存在"
            )
        
        db.delete(credential)
        db.commit()
        
        return {"message": "API凭据删除成功", "id": str(credential_id)}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除API凭据失败: {str(e)}"
        )


# ========== 频道管理 ==========

@router.get("/channels", response_model=List[ChannelResponse], summary="获取频道列表")
async def get_channels(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> List[ChannelResponse]:
    """
    获取所有监听频道列表
    
    需要 Bearer Token 认证
    """
    try:
        channels = db.query(Channel).all()
        return [ChannelResponse.from_orm(channel) for channel in channels]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取频道列表失败: {str(e)}"
        )


@router.post("/channels", response_model=ChannelResponse, summary="添加频道")
async def create_channel(
    channel_data: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> ChannelResponse:
    """
    添加新的监听频道
    
    需要 Bearer Token 认证
    """
    try:
        # 检查是否已存在相同的频道
        existing = db.query(Channel).filter(Channel.username == channel_data.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"频道 {channel_data.username} 已存在"
            )
        
        channel = Channel(username=channel_data.username)
        db.add(channel)
        db.commit()
        db.refresh(channel)
        
        return ChannelResponse.from_orm(channel)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加频道失败: {str(e)}"
        )


@router.put("/channels/{channel_id}", response_model=ChannelResponse, summary="编辑频道")
async def update_channel(
    channel_id: int,
    channel_data: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> ChannelResponse:
    """
    编辑频道用户名
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"频道 {channel_id} 不存在"
            )
        
        # 检查新用户名是否已存在
        existing = db.query(Channel).filter(
            Channel.username == channel_data.username,
            Channel.id != channel_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"频道 {channel_data.username} 已存在"
            )
        
        channel.username = channel_data.username
        db.commit()
        db.refresh(channel)
        
        return ChannelResponse.from_orm(channel)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"编辑频道失败: {str(e)}"
        )


@router.delete("/channels/{channel_id}", summary="删除频道")
async def delete_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    删除指定的监听频道
    
    需要 Bearer Token 认证
    """
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"频道 {channel_id} 不存在"
            )
        
        db.delete(channel)
        db.commit()
        
        return {"message": "频道删除成功", "id": str(channel_id), "username": channel.username}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除频道失败: {str(e)}"
        )


# ========== 系统配置 ==========

@router.get("/config", response_model=SystemConfigResponse, summary="获取系统配置")
async def get_system_config(
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> SystemConfigResponse:
    """
    获取系统配置
    
    需要 Bearer Token 认证（管理员权限）
    """
    return SystemConfigResponse(
        public_dashboard_enabled=settings.PUBLIC_DASHBOARD_ENABLED
    )


@router.put("/config", response_model=SystemConfigResponse, summary="更新系统配置")
async def update_system_config(
    config_data: SystemConfigUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> SystemConfigResponse:
    """
    更新系统配置
    
    需要 Bearer Token 认证（管理员权限）
    
    注意：配置更新会写入 .env 文件，需要重启服务才能完全生效
    """
    try:
        # 更新配置对象
        settings.PUBLIC_DASHBOARD_ENABLED = config_data.public_dashboard_enabled
        
        # 更新 .env 文件
        env_file = ".env"
        if os.path.exists(env_file):
            # 读取现有 .env 内容
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 确保最后一行以换行结尾，避免黏连
            if lines and not lines[-1].endswith('\n'):
                lines[-1] = lines[-1] + '\n'
            
            # 更新或添加 PUBLIC_DASHBOARD_ENABLED
            updated = False
            for i, line in enumerate(lines):
                if line.startswith('PUBLIC_DASHBOARD_ENABLED='):
                    lines[i] = f'PUBLIC_DASHBOARD_ENABLED={str(config_data.public_dashboard_enabled).lower()}\n'
                    updated = True
                    break
            
            if not updated:
                lines.append(f'PUBLIC_DASHBOARD_ENABLED={str(config_data.public_dashboard_enabled).lower()}\n')
            
            # 写回文件
            with open(env_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        
        return SystemConfigResponse(
            public_dashboard_enabled=settings.PUBLIC_DASHBOARD_ENABLED
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新系统配置失败: {str(e)}"
        )


# ========== 用户管理 ==========

@router.get("/users", response_model=List[UserResponse], summary="获取用户列表")
async def get_users(
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> List[UserResponse]:
    """
    获取所有用户列表
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        users = list_users()
        return [UserResponse(**user) for user in users]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户列表失败: {str(e)}"
        )


@router.get("/users/export-all", response_model=List[UserResponse], summary="导出用户列表")
@router.get("/users/export", response_model=List[UserResponse], include_in_schema=False)
async def export_users_api(
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> List[UserResponse]:
    """
    导出用户列表（不含密码）
    """
    try:
        users = export_users()
        return [UserResponse(**u) for u in users]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出用户列表失败: {str(e)}"
        )


@router.get("/users/{username}", response_model=UserResponse, summary="获取用户信息")
async def get_user_info(
    username: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> UserResponse:
    """
    获取指定用户信息
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        user = get_user(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"用户 {username} 不存在"
            )
        return UserResponse(**user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户信息失败: {str(e)}"
        )


@router.post("/users", response_model=UserResponse, summary="添加用户")
async def create_user(
    user_data: UserCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> UserResponse:
    """
    添加新用户
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        success = add_user(
            username=user_data.username,
            password=user_data.password,
            name=user_data.name,
            email=user_data.email,
            role=user_data.role
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"添加用户失败：用户名已存在或角色无效"
            )
        
        user = get_user(user_data.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="用户创建成功但无法获取用户信息"
            )
        
        return UserResponse(**user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加用户失败: {str(e)}"
        )


@router.put("/users/{username}", response_model=UserResponse, summary="更新用户信息")
async def update_user_info(
    username: str,
    user_data: UserUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> UserResponse:
    """
    更新用户信息
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        success = update_user(
            username=username,
            name=user_data.name,
            email=user_data.email,
            role=user_data.role
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"更新用户失败：用户不存在或角色无效"
            )
        
        user = get_user(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"用户 {username} 不存在"
            )
        
        return UserResponse(**user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新用户信息失败: {str(e)}"
        )


@router.put("/users/{username}/password", summary="修改用户密码")
async def change_user_password(
    username: str,
    password_data: PasswordChange,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    修改用户密码
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        success = change_password(username, password_data.new_password)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"修改密码失败：用户不存在"
            )
        
        return {"message": "密码修改成功", "username": username}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修改密码失败: {str(e)}"
        )


@router.put("/users/{username}/username", summary="修改用户名")
async def change_user_username(
    username: str,
    username_data: UsernameChange,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    修改用户名
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        success = change_username(username, username_data.new_username)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"修改用户名失败：原用户不存在或新用户名已存在"
            )
        
        return {"message": "用户名修改成功", "old_username": username, "new_username": username_data.new_username}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修改用户名失败: {str(e)}"
        )


@router.put("/users/{username}/role", summary="修改用户角色")
async def change_user_role_api(
    username: str,
    role_data: RoleChange,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    修改用户角色
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        success = change_user_role(username, role_data.new_role)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"修改角色失败：用户不存在或角色无效"
            )
        
        return {"message": "角色修改成功", "username": username, "new_role": role_data.new_role}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修改角色失败: {str(e)}"
        )


@router.delete("/users/{username}", summary="删除用户")
async def delete_user(
    username: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    删除用户
    
    需要 Bearer Token 认证（管理员权限）
    
    注意：不能删除 admin 用户
    """
    try:
        success = remove_user(username)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"删除用户失败：用户不存在或不能删除管理员用户"
            )
        
        return {"message": "用户删除成功", "username": username}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除用户失败: {str(e)}"
        )


@router.get("/users/roles/available", summary="获取可用角色列表")
async def get_available_roles_api(
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, str]:
    """
    获取可用角色列表
    
    需要 Bearer Token 认证（管理员权限）
    """
    return get_available_roles()


@router.post("/users/bulk/random-create", response_model=BulkCreateResponse, summary="批量随机创建用户")
async def bulk_random_create_users(
    req: BulkRandomCreateRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> BulkCreateResponse:
    """
    批量随机创建用户（仅管理员）
    - 保护：仅 admin；角色必须合法；数量有限制
    """
    try:
        result = bulk_create_random_users(
            count=req.count,
            prefix=req.prefix,
            start_index=req.start_index,
            role=req.role,
            password_length=req.password_length
        )
        return BulkCreateResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量创建失败: {str(e)}"
        )


@router.post("/users/bulk/delete", response_model=BulkSimpleResponse, summary="批量删除用户")
async def bulk_delete_users(
    req: BulkUsernamesRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> BulkSimpleResponse:
    """
    批量删除用户（仅管理员），保护 admin
    """
    try:
        result = bulk_remove_users(req.usernames)
        return BulkSimpleResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量删除失败: {str(e)}"
        )


@router.post("/users/bulk/reset-password", summary="批量重置密码")
async def bulk_reset_users_password(
    req: BulkUsernamesRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> Dict[str, Any]:
    """
    批量重置密码（仅管理员），保护 admin
    """
    try:
        result = bulk_reset_passwords(req.usernames, password_length=req.password_length or 12)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量重置密码失败: {str(e)}"
        )


# ========== 数据维护 ==========

@router.post("/maintenance/fix-tags", response_model=MaintenanceResult, summary="修复Tags脏数据")
async def fix_tags_api(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> MaintenanceResult:
    """
    修复tags字段脏数据
    
    将字符串格式的tags转换为list格式
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        result = fix_tags(db)
        return MaintenanceResult(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修复Tags失败: {str(e)}"
        )


@router.post("/maintenance/dedup-links", response_model=MaintenanceResult, summary="链接去重")
async def dedup_links_api(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> MaintenanceResult:
    """
    链接去重
    
    相同链接且时间间隔5分钟内，优先保留网盘链接多的，否则保留最新的
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        result = dedup_links(db)
        return MaintenanceResult(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"链接去重失败: {str(e)}"
        )


@router.post("/maintenance/clear-link-check-data", response_model=MaintenanceResult, summary="清空链接检测数据")
async def clear_link_check_data_api(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> MaintenanceResult:
    """
    清空所有链接检测数据
    
    ⚠️ 危险操作，会删除所有链接检测记录
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        result = clear_link_check_data(db)
        return MaintenanceResult(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空链接检测数据失败: {str(e)}"
        )


@router.post("/maintenance/clear-old-link-check-data", response_model=MaintenanceResult, summary="清空旧链接检测数据")
async def clear_old_link_check_data_api(
    request: ClearOldDataRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> MaintenanceResult:
    """
    清空指定天数之前的链接检测数据
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        result = clear_old_link_check_data(db, days=request.days)
        return MaintenanceResult(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空旧链接检测数据失败: {str(e)}"
        )


# ========== 频道管理扩展 ==========

@router.post("/channels/diagnose", response_model=ChannelDiagnosisResult, summary="诊断所有频道")
async def diagnose_channels_api(
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> ChannelDiagnosisResult:
    """
    诊断所有频道的有效性
    
    检查频道是否存在且可访问，显示频道详细信息
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        valid_channels, invalid_channels = await diagnose_channels()
        return ChannelDiagnosisResult(
            valid_channels=valid_channels,
            invalid_channels=invalid_channels
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"频道诊断失败: {str(e)}"
        )


@router.post("/channels/test-monitor", response_model=MonitorTestResult, summary="测试监控功能")
async def test_monitor_api(
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> MonitorTestResult:
    """
    测试监控功能
    
    验证Telegram客户端连接和事件处理器是否正常工作
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        result = await test_monitor()
        return MonitorTestResult(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试监控失败: {str(e)}"
        )


# ========== 链接检测 ==========

@router.post("/link-check/start", response_model=LinkCheckTaskStatus, summary="开始链接检测任务")
async def start_link_check_task(
    task_data: LinkCheckTaskCreate,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> LinkCheckTaskStatus:
    """
    开始链接检测任务
    
    需要 Bearer Token 认证（管理员权限）
    
    时间段格式：
    - today: 今天
    - yesterday: 昨天
    - week: 最近7天
    - month: 最近30天
    - year: 最近365天
    - 2024-01-15: 指定日期
    - 2024-01-15:2024-01-20: 日期范围
    """
    try:
        task_id = str(uuid.uuid4())
        
        # 添加后台任务
        background_tasks.add_task(
            run_link_check_task,
            task_id,
            task_data.period,
            task_data.max_concurrent
        )
        
        # 返回初始状态
        return LinkCheckTaskStatus(
            task_id=task_id,
            status="running",
            progress=0
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动链接检测任务失败: {str(e)}"
        )


@router.get("/link-check/tasks/{task_id}", response_model=LinkCheckTaskStatus, summary="获取任务状态")
async def get_link_check_task_status(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> LinkCheckTaskStatus:
    """
    获取链接检测任务状态
    
    需要 Bearer Token 认证（管理员权限）
    """
    status_data = get_task_status(task_id)
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {task_id} 不存在"
        )
    
    return LinkCheckTaskStatus(
        task_id=task_id,
        **status_data
    )


@router.get("/link-check/tasks", response_model=List[LinkCheckTaskHistory], summary="获取检测历史")
async def get_link_check_history(
    limit: int = 20,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> List[LinkCheckTaskHistory]:
    """
    获取链接检测任务历史
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        history = get_task_history(limit=limit)
        return [LinkCheckTaskHistory(**item) for item in history]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取检测历史失败: {str(e)}"
        )


@router.get("/link-check/tasks/{check_time}/result", response_model=LinkCheckTaskResult, summary="获取检测结果")
async def get_link_check_result(
    check_time: str,
    current_user: Dict[str, Any] = Depends(get_admin_user)
) -> LinkCheckTaskResult:
    """
    获取链接检测结果详情
    
    需要 Bearer Token 认证（管理员权限）
    """
    try:
        result = get_task_result(check_time)
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"]
            )
        return LinkCheckTaskResult(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取检测结果失败: {str(e)}"
        )

