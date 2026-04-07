from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies_runtime import get_admin_user
from app.schemas.admin_models import (
    AccountListResponse,
    AccountRuntimeSettingsResponse,
    AccountRuntimeSettingsUpdate,
    BulkCreateResponse,
    BulkRandomCreateRequest,
    BulkSimpleResponse,
    BulkUsernamesRequest,
    PasswordChange,
    RoleChange,
    UserCreate,
    UserResponse,
    UserUpdate,
    UsernameChange,
)
from app.services.account_service import (
    apply_user_runtime_settings,
    bulk_create_random_accounts,
    bulk_delete_accounts,
    bulk_reset_passwords_for_accounts,
    change_password_for_account,
    change_username_for_account,
    create_user_account,
    delete_user_account,
    export_user_accounts,
    get_available_roles,
    get_user_record,
    get_user_runtime_settings,
    list_user_accounts,
    update_user_account,
)

router = APIRouter(prefix="/api/admin/accounts", tags=["后台用户"])


def _user_or_404(username: str) -> dict[str, Any]:
    user = get_user_record(username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {username} 不存在")
    return user


@router.get("", response_model=AccountListResponse, summary="分页获取账号列表")
async def get_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str = Query("", max_length=100),
    role: Optional[str] = Query(default=None),
    effective_status: Optional[str] = Query(default=None),
    account_source: Optional[str] = Query(default=None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> AccountListResponse:
    del current_user
    result = list_user_accounts(
        page=page,
        page_size=page_size,
        keyword=keyword,
        role=role,
        effective_status=effective_status,
        account_source=account_source,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return AccountListResponse(
        items=[UserResponse(**item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        runtime_settings=AccountRuntimeSettingsResponse(**result["runtime_settings"]),
    )


@router.get("/settings", response_model=AccountRuntimeSettingsResponse, summary="获取账号运行设置")
async def get_account_runtime_settings_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> AccountRuntimeSettingsResponse:
    del current_user
    return AccountRuntimeSettingsResponse(**get_user_runtime_settings())


@router.put("/settings", response_model=AccountRuntimeSettingsResponse, summary="更新账号运行设置")
async def update_account_runtime_settings_api(
    payload: AccountRuntimeSettingsUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> AccountRuntimeSettingsResponse:
    updated = apply_user_runtime_settings(payload.model_dump(), updated_by=current_user.get("username"))
    return AccountRuntimeSettingsResponse(**updated)


@router.get("/roles/available", summary="获取可用角色")
async def get_available_roles_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> Dict[str, str]:
    del current_user
    return get_available_roles()


@router.get("/export", response_model=list[UserResponse], summary="导出账号列表")
async def export_accounts_api(
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> list[UserResponse]:
    del current_user
    return [UserResponse(**item) for item in export_user_accounts()]


@router.get("/{username}", response_model=UserResponse, summary="获取单个账号")
async def get_account(
    username: str,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> UserResponse:
    del current_user
    return UserResponse(**_user_or_404(username))


@router.post("", response_model=UserResponse, summary="创建账号")
async def create_account(
    payload: UserCreate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> UserResponse:
    user = create_user_account(
        username=payload.username,
        password=payload.password,
        name=payload.name,
        email=payload.email,
        role=payload.role,
        status=payload.status,
        validity_mode=payload.validity_mode,
        validity_unit=payload.validity_unit,
        validity_value=payload.validity_value,
        fixed_expires_at=payload.fixed_expires_at,
        session_limit_override=payload.session_limit_override,
        created_by=current_user.get("username"),
    )
    return UserResponse(**user)


@router.put("/{username}", response_model=UserResponse, summary="更新账号")
async def update_account(
    username: str,
    payload: UserUpdate,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> UserResponse:
    user = update_user_account(
        username,
        name=payload.name,
        email=payload.email,
        role=payload.role,
        status=payload.status,
        validity_mode=payload.validity_mode,
        validity_unit=payload.validity_unit,
        validity_value=payload.validity_value,
        fixed_expires_at=payload.fixed_expires_at,
        session_limit_override=payload.session_limit_override,
        updated_by=current_user.get("username"),
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {username} 不存在")
    return UserResponse(**user)


@router.put("/{username}/password", summary="修改账号密码")
async def change_account_password(
    username: str,
    payload: PasswordChange,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> Dict[str, str]:
    if not change_password_for_account(username, payload.new_password, updated_by=current_user.get("username")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {username} 不存在")
    return {"message": "密码修改成功", "username": username}


@router.put("/{username}/username", summary="修改账号用户名")
async def change_account_username(
    username: str,
    payload: UsernameChange,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> Dict[str, str]:
    try:
        changed = change_username_for_account(username, payload.new_username, updated_by=current_user.get("username"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {username} 不存在")
    return {"message": "用户名修改成功", "old_username": username, "new_username": payload.new_username}


@router.put("/{username}/role", summary="修改账号角色")
async def change_account_role(
    username: str,
    payload: RoleChange,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> Dict[str, str]:
    user = update_user_account(username, role=payload.new_role, updated_by=current_user.get("username"))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {username} 不存在")
    return {"message": "角色修改成功", "username": username, "new_role": payload.new_role}


@router.delete("/{username}", summary="删除账号")
async def delete_account(
    username: str,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> Dict[str, str]:
    try:
        removed = delete_user_account(username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 {username} 不存在")
    return {"message": "用户删除成功", "username": username}


@router.post("/bulk/random-create", response_model=BulkCreateResponse, summary="批量随机创建账号")
async def bulk_random_create_accounts_api(
    payload: BulkRandomCreateRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BulkCreateResponse:
    result = bulk_create_random_accounts(
        count=payload.count,
        prefix=payload.prefix,
        start_index=payload.start_index,
        role=payload.role,
        password_length=payload.password_length,
        validity_mode=payload.validity_mode,
        validity_unit=payload.validity_unit,
        validity_value=payload.validity_value,
        fixed_expires_at=payload.fixed_expires_at,
        created_by=current_user.get("username"),
    )
    return BulkCreateResponse(**result)


@router.post("/bulk/delete", response_model=BulkSimpleResponse, summary="批量删除账号")
async def bulk_delete_accounts_api(
    payload: BulkUsernamesRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> BulkSimpleResponse:
    del current_user
    return BulkSimpleResponse(**bulk_delete_accounts(payload.usernames))


@router.post("/bulk/reset-password", summary="批量重置密码")
async def bulk_reset_passwords_api(
    payload: BulkUsernamesRequest,
    current_user: Dict[str, Any] = Depends(get_admin_user),
) -> Dict[str, Any]:
    del current_user
    return bulk_reset_passwords_for_accounts(payload.usernames, password_length=payload.password_length or 12)
