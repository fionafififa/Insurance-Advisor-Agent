"""在项目数据库中新增用户，或为指定的已有账号设置密码。"""

import argparse
import asyncio
from getpass import GetPassWarning, getpass
import re
import warnings


async def provision_user(args: argparse.Namespace, password: str) -> None:
    from sqlalchemy import or_, select
    from sqlalchemy.exc import IntegrityError

    from app.infra.database import AsyncSessionFactory, close_database
    from app.modules.auth.models import User
    from app.modules.auth.security import hash_password

    password_hash = await asyncio.to_thread(hash_password, password)
    try:
        async with AsyncSessionFactory.begin() as session:
            if args.reset_password:
                user = await session.scalar(select(User).where(User.username == args.username))
                if user is None:
                    raise SystemExit("找不到指定的用户名。")
                user.password_hash = password_hash
            else:
                identifiers = [args.username, args.email]
                duplicate_id = await session.scalar(
                    select(User.id)
                    .where(or_(User.username.in_(identifiers), User.email.in_(identifiers)))
                    .limit(1)
                )
                if duplicate_id is not None:
                    raise SystemExit("该用户名或邮箱已存在。")
                session.add(
                    User(
                        username=args.username,
                        email=args.email,
                        display_name=args.display_name,
                        password_hash=password_hash,
                        status="active",
                    )
                )
    except IntegrityError:
        raise SystemExit("账号数据冲突，无法保存。") from None
    finally:
        await close_database()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", type=str.strip, required=True, help="用户名")
    parser.add_argument("--email", type=str.strip, help="用于登录的邮箱，新建时必填")
    parser.add_argument("--display-name", help="显示名称，可选")
    parser.add_argument("--reset-password", action="store_true", help="为已有账号设置密码")
    args = parser.parse_args()

    if args.reset_password:
        if args.email is not None or args.display_name is not None:
            parser.error("重设密码只需要 --username 和 --reset-password。")
    else:
        if not 1 <= len(args.username) <= 80 or "@" in args.username:
            parser.error("用户名须为 1–80 个字符。@ 用于区分邮箱登录。")
        if not args.email or len(args.email) > 160 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+", args.email
        ):
            parser.error("创建用户需要有效的 --email。")
        if args.display_name is not None and len(args.display_name) > 100:
            parser.error("显示名称不得超过 100 个字符。")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("请输入密码：")
            confirmation = getpass("请再次输入密码：")
    except (EOFError, GetPassWarning, KeyboardInterrupt):
        raise SystemExit("请在支持隐式输入的交互式终端中运行。") from None
    if not 6 <= len(password) <= 1024 or not password.strip():
        parser.error("密码须为 6–1024 个字符，且不能全为空白。")
    if password != confirmation:
        parser.error("两次输入的密码不一致。")

    asyncio.run(provision_user(args, password))
    print("账号密码已设置。" if args.reset_password else "账号已创建。")


if __name__ == "__main__":
    main()
