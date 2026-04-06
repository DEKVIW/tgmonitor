from __future__ import annotations

import json

from app.models.models import create_tables
from app.services.system_config_service import (
    ensure_runtime_configuration_seeded,
    get_backup_settings_values,
    get_system_config_values,
)


def _mask_backup_settings(values: dict[str, object]) -> dict[str, object]:
    masked = dict(values)
    if masked.get("webdav_password_encrypted"):
        masked["webdav_password_encrypted"] = "***"
    return masked


def main() -> None:
    print("=" * 60)
    print("迁移运行时配置到数据库")
    print("=" * 60)

    print("1. 创建缺失的数据表...")
    create_tables()

    print("2. 初始化系统配置与备份配置单例行...")
    ensure_runtime_configuration_seeded()

    system_config = get_system_config_values()
    backup_settings = get_backup_settings_values()

    print("3. 当前 system_settings：")
    print(json.dumps(system_config, ensure_ascii=False, indent=2))

    print("4. 当前 backup_settings：")
    print(json.dumps(_mask_backup_settings(backup_settings), ensure_ascii=False, indent=2))

    print("完成。")
    print("说明：如果数据库里已有配置行，本脚本不会覆盖现有值。")


if __name__ == "__main__":
    main()
