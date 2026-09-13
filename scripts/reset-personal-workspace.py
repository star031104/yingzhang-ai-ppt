"""Preview by default. Stop the server before executing an irreversible local reset."""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "apps" / "api"))


def main():
    parser = argparse.ArgumentParser(description="映章离线恢复出厂：默认只预览，不删除")
    parser.add_argument("--confirm", choices=["RESET-MY-WORKSPACE"])
    parser.add_argument("--server-stopped", action="store_true")
    args = parser.parse_args()
    if Path.cwd().resolve() != WORKSPACE:
        parser.error("请先进入本项目根目录，再运行此脚本")
    from app.config import settings
    from app.personalization.data_management import managed_reset_paths

    paths = managed_reset_paths(settings, WORKSPACE)
    print(
        json.dumps(
            {
                "action": "恢复出厂",
                "paths": [str(path) for path in paths],
                "retained": [
                    "应用源代码和内置技能",
                    "外部模型文件",
                    "用户下载、复制或自行备份的文件",
                    "test-results 及其他用户自行指定输出目录",
                ],
                "externalCopies": "不会删除外部模型服务、操作系统快照或其他目录中的副本",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.confirm:
        print("以上仅预览。执行前停止服务，再添加 --server-stopped --confirm RESET-MY-WORKSPACE。")
        return
    if not args.server_stopped:
        parser.error("必须停止映章服务，并明确添加 --server-stopped")
    database = Path(settings.database_url.removeprefix("sqlite:///")).resolve()
    # Refuse an active writer. The explicit stopped-server requirement also covers idle servers.
    if database.exists():
        with sqlite3.connect(database, timeout=0) as connection:
            connection.execute("BEGIN EXCLUSIVE")
            tables = {
                item[0]
                for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            refs = (
                [
                    item[0]
                    for item in connection.execute(
                        "SELECT api_key_ref FROM providers WHERE api_key_ref IS NOT NULL"
                    )
                ]
                if "providers" in tables
                else []
            )
            connection.rollback()
        from app.security.secrets import secret_store

        for ref in refs:
            secret_store.delete(ref)
    for path in paths:
        # Revalidate every exact target immediately before mutation.
        if path not in managed_reset_paths(settings, WORKSPACE):
            raise RuntimeError("清理路径已发生变化")
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    print("应用管理范围内的数据和凭据已清理。代码、内置技能和外部副本保留。")


if __name__ == "__main__":
    main()
