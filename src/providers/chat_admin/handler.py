from datetime import datetime
from typing import Dict, List, Optional
from nonebot import logger
from src.providers.chat_admin import (
    chat_admin_user_permissions,
    chat_admin_group_permissions,
    chat_admin_list,
    chat_application_form
)


class ChatAdminHandler:
    """Chat管理处理器"""

    @classmethod
    async def register_admin(cls, admin_id: str, admin_name: str, permission_level: int = 1, register_key: Optional[str] = None) -> Dict[str, any]:
        """
        注册管理员

        :param admin_id: 管理员ID
        :param admin_name: 管理员名称
        :param permission_level: 权限等级 (1-普通管理员, 2-超管)
        :param register_key: 注册密钥（用于超管注册）
        :return: {"code": bool, "msg": str}
        """
        try:
            # 检查是否已存在
            existing_admin = await chat_admin_list.filter(admin_id=admin_id).first()
            if existing_admin:
                return {"code": False, "msg": "该用户已是管理员"}

            # 创建管理员记录
            await chat_admin_list.create(
                admin_id=admin_id,
                admin_name=admin_name,
                permission_level=permission_level,
                created_at=datetime.now()
            )
            return {"code": True, "msg": "管理员注册成功"}

        except Exception as e:
            logger.error(f"注册管理员失败: {e}", exc_info=True)
            return {"code": False, "msg": f"注册失败: {str(e)}"}

    @classmethod
    async def is_admin(cls, user_id: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否为管理员

        :param user_id: 用户ID
        :param group_id: 群ID（可选，用于检查群管理员）
        :return: 是否为管理员
        """
        try:
            # 检查是否为系统管理员
            admin = await chat_admin_list.filter(admin_id=user_id).first()
            if admin and admin.permission_level >= 1:
                return True

            # 如果有群ID，检查是否为群管理员（使用GroupChatRole的逻辑）
            if group_id:
                from src.clover_sqlite.models.chat import GroupChatRole
                group_admin = await GroupChatRole.get_admin_list(group_id, user_id)
                if group_admin:
                    return True

            return False

        except Exception as e:
            logger.error(f"检查管理员权限失败: {e}", exc_info=True)
            return False

    @classmethod
    async def is_super_admin(cls, user_id: str) -> bool:
        """
        检查用户是否为超管

        :param user_id: 用户ID
        :return: 是否为超管
        """
        try:
            admin = await chat_admin_list.filter(admin_id=user_id).first()
            return admin is not None and admin.permission_level >= 2

        except Exception as e:
            logger.error(f"检查超管权限失败: {e}", exc_info=True)
            return False

    @classmethod
    async def get_admin_level(cls, user_id: str) -> Optional[int]:
        """
        获取用户的管理员等级

        :param user_id: 用户ID
        :return: 权限等级 (0-非管理员, 1-普通管理员, 2-超管)
        """
        try:
            admin = await chat_admin_list.filter(admin_id=user_id).first()
            if admin:
                return admin.permission_level
            return 0

        except Exception as e:
            logger.error(f"获取管理员等级失败: {e}", exc_info=True)
            return 0

    @classmethod
    async def create_application(cls, applicant_id: str, group_id: str, reason: Optional[str] = None) -> Dict[str, any]:
        """
        创建申请

        :param applicant_id: 申请人ID
        :param group_id: 群ID
        :param reason: 申请理由
        :return: {"code": bool, "msg": str}
        """
        try:
            # 检查是否已有待审批的申请
            existing_application = await chat_application_form.filter(
                applicant_id=applicant_id,
                group_id=group_id,
                status=0
            ).first()

            if existing_application:
                return {"code": False, "msg": "您已有待审批的申请，请勿重复提交"}

            # 创建申请记录
            await chat_application_form.create(
                applicant_id=applicant_id,
                group_id=group_id,
                reason=reason or "无",
                status=0,
                admin_id=None,
                apply_time=datetime.now(),
                handle_time=None,
                refuse_reason=None
            )
            return {"code": True, "msg": "申请提交成功，请等待管理员审批"}

        except Exception as e:
            logger.error(f"创建申请失败: {e}", exc_info=True)
            return {"code": False, "msg": f"申请提交失败: {str(e)}"}

    @classmethod
    async def get_applications(cls, group_id: Optional[str] = None, status: Optional[int] = None) -> List[Dict]:
        """
        获取申请列表

        :param group_id: 群ID（可选，筛选特定群的申请）
        :param status: 状态 (0-待审批, 1-已同意, 2-已拒绝, None-全部)
        :return: 申请列表
        """
        try:
            query = chat_application_form.all()

            if group_id:
                query = query.filter(group_id=group_id)

            if status is not None:
                query = query.filter(status=status)

            applications = await query.order_by("-apply_time").values()

            result = []
            for app in applications:
                status_text = {0: "待审批", 1: "已同意", 2: "已拒绝"}.get(app["status"], "未知")
                handler_text = f"处理人：{app.get('admin_id', '无')}" if app.get('admin_id') else "待处理"
                result.append({
                    "id": app["id"],
                    "applicant_id": app["applicant_id"],
                    "group_id": app["group_id"],
                    "reason": app["reason"],
                    "status": app["status"],
                    "status_text": status_text,
                    "admin_id": app.get("admin_id"),
                    "apply_time": app["apply_time"].strftime("%Y-%m-%d %H:%M:%S") if app["apply_time"] else "未知",
                    "handle_time": app["handle_time"].strftime("%Y-%m-%d %H:%M:%S") if app["handle_time"] else "未知",
                    "refuse_reason": app.get("refuse_reason"),
                    "handler_text": handler_text
                })

            return result

        except Exception as e:
            logger.error(f"获取申请列表失败: {e}", exc_info=True)
            return []

    @classmethod
    async def approve_application(cls, application_id: int, admin_id: str, approve: bool, refuse_reason: Optional[str] = None) -> Dict[str, any]:
        """
        审批申请

        :param application_id: 申请ID
        :param admin_id: 管理员ID
        :param approve: 是否同意 (True-同意, False-拒绝)
        :param refuse_reason: 拒绝理由（仅拒绝时使用）
        :return: {"code": bool, "msg": str}
        """
        try:
            application = await chat_application_form.filter(id=application_id).first()

            if not application:
                return {"code": False, "msg": "申请不存在"}

            if application.status != 0:
                return {"code": False, "msg": "该申请已被处理"}

            # 更新申请状态
            application.status = 1 if approve else 2
            application.admin_id = admin_id
            application.handle_time = datetime.now()
            if not approve:
                application.refuse_reason = refuse_reason or "无理由拒绝"
            await application.save()

            # 如果同意，自动添加相关权限
            # 分情况处理：如果是私聊申请，设置用户权限；如果是群聊申请，设置群组权限
            if approve:
                if application.group_id == "C2C":
                    await cls.set_user_permission(
                        user_id=application.applicant_id,
                        allow_private_chat=True,
                        admin_id=admin_id
                    )
                else:
                    await cls.set_group_permission(
                        group_id=application.group_id,
                        is_allowed=True,
                        admin_id=admin_id
                    )

            status_text = "已同意" if approve else "已拒绝"
            return {"code": True, "msg": f"申请审批{status_text}成功"}

        except Exception as e:
            logger.error(f"审批申请失败: {e}", exc_info=True)
            return {"code": False, "msg": f"审批失败: {str(e)}"}

    @classmethod
    async def approve_application_by_user_id(cls, applicant_id: str, group_id: str, admin_id: str, approve: bool, refuse_reason: Optional[str] = None) -> Dict[str, any]:
        """
        根据申请人ID审批申请

        :param applicant_id: 申请人ID
        :param group_id: 群ID
        :param admin_id: 管理员ID
        :param approve: 是否同意 (True-同意, False-拒绝)
        :param refuse_reason: 拒绝理由（仅拒绝时使用）
        :return: {"code": bool, "msg": str}
        """
        try:
            # 查找待审批的申请
            application = await chat_application_form.filter(
                applicant_id=applicant_id,
                group_id=group_id,
                status=0
            ).first()

            if not application:
                return {"code": False, "msg": "未找到该用户的待审批申请"}

            return await cls.approve_application(application.id, admin_id, approve, refuse_reason)

        except Exception as e:
            logger.error(f"根据用户ID审批申请失败: {e}", exc_info=True)
            return {"code": False, "msg": f"审批失败: {str(e)}"}

    @classmethod
    async def set_user_permission(cls, user_id: str, allow_private_chat: bool, is_banned: bool = False, admin_id: str = "system") -> Dict[str, any]:
        """
        设置用户权限

        :param user_id: 用户ID
        :param allow_private_chat: 是否允许私聊
        :param is_banned: 是否封禁
        :param admin_id: 操作管理员ID
        :return: {"code": bool, "msg": str}
        """
        try:
            # 检查是否已存在
            existing_permission = await chat_admin_user_permissions.filter(user_id=user_id).first()

            if existing_permission:
                # 更新现有记录
                existing_permission.allow_private_chat = allow_private_chat
                existing_permission.is_banned = is_banned
                existing_permission.admin_id = admin_id
                existing_permission.updated_at = datetime.now()
                await existing_permission.save()
                return {"code": True, "msg": "用户权限更新成功"}
            else:
                # 创建新记录
                await chat_admin_user_permissions.create(
                    user_id=user_id,
                    allow_private_chat=allow_private_chat,
                    is_banned=is_banned,
                    admin_id=admin_id,
                    updated_at=datetime.now()
                )
                return {"code": True, "msg": "用户权限创建成功"}

        except Exception as e:
            logger.error(f"设置用户权限失败: {e}", exc_info=True)
            return {"code": False, "msg": f"设置失败: {str(e)}"}

    @classmethod
    async def get_user_permission(cls, user_id: str) -> Optional[Dict]:
        """
        获取用户权限

        :param user_id: 用户ID
        :return: 用户权限信息
        """
        try:
            permission = await chat_admin_user_permissions.filter(user_id=user_id).first()

            if permission:
                return {
                    "user_id": permission.user_id,
                    "allow_private_chat": permission.allow_private_chat,
                    "is_banned": permission.is_banned,
                    "admin_id": permission.admin_id,
                    "updated_at": permission.updated_at.strftime("%Y-%m-%d") if permission.updated_at else None
                }
            return None

        except Exception as e:
            logger.error(f"获取用户权限失败: {e}", exc_info=True)
            return None

    @classmethod
    async def set_group_permission(cls, group_id: str, is_allowed: bool, admin_id: str) -> Dict[str, any]:
        """
        设置群组权限

        :param group_id: 群ID
        :param is_allowed: 是否允许使用
        :param admin_id: 操作管理员ID
        :return: {"code": bool, "msg": str}
        """
        try:
            # 检查是否已存在
            existing_permission = await chat_admin_group_permissions.filter(group_id=group_id).first()

            if existing_permission:
                # 更新现有记录
                existing_permission.is_allowed = is_allowed
                existing_permission.admin_id = admin_id
                existing_permission.updated_at = datetime.now()
                await existing_permission.save()
                return {"code": True, "msg": "群组权限更新成功"}
            else:
                # 创建新记录
                await chat_admin_group_permissions.create(
                    group_id=group_id,
                    is_allowed=is_allowed,
                    admin_id=admin_id,
                    updated_at=datetime.now()
                )
                return {"code": True, "msg": "群组权限创建成功"}

        except Exception as e:
            logger.error(f"设置群组权限失败: {e}", exc_info=True)
            return {"code": False, "msg": f"设置失败: {str(e)}"}

    @classmethod
    async def get_group_permission(cls, group_id: str) -> Optional[Dict]:
        """
        获取群组权限

        :param group_id: 群ID
        :return: 群组权限信息
        """
        try:
            permission = await chat_admin_group_permissions.filter(group_id=group_id).first()

            if permission:
                return {
                    "group_id": permission.group_id,
                    "is_allowed": permission.is_allowed,
                    "admin_id": permission.admin_id,
                    "updated_at": permission.updated_at.strftime("%Y-%m-%d") if permission.updated_at else None
                }
            return None

        except Exception as e:
            logger.error(f"获取群组权限失败: {e}", exc_info=True)
            return None

    @classmethod
    async def check_chat_permission(cls, user_id: str, group_id: Optional[str] = None) -> Dict[str, any]:
        """
        检查用户聊天权限

        :param user_id: 用户ID
        :param group_id: 群ID（可选）
        :return: {"allowed": bool, "reason": str}
        """
        try:
            # 检查用户是否被封禁
            user_permission = await cls.get_user_permission(user_id)
            if user_permission and user_permission["is_banned"]:
                return {"allowed": False, "reason": "您已被封禁"}

            # 检查是否有群权限
            if group_id:
                group_permission = await cls.get_group_permission(group_id)
                if group_permission and not group_permission["is_allowed"]:
                    return {"allowed": False, "reason": "该群组未授权使用此功能"}

            # 如果是私聊，检查用户是否有私聊权限
            if not group_id:
                if user_permission is None or not user_permission["allow_private_chat"]:
                    return {"allowed": False, "reason": "暂未在私聊开放此功能"}

            return {"allowed": True, "reason": ""}

        except Exception as e:
            logger.error(f"检查聊天权限失败: {e}", exc_info=True)
            return {"allowed": False, "reason": "权限检查失败"}

    @classmethod
    async def list_admins(cls) -> List[Dict]:
        """
        获取管理员列表

        :return: 管理员列表
        """
        try:
            admins = await chat_admin_list.all().values()

            result = []
            for admin in admins:
                level_text = {1: "管理员", 2: "超管"}.get(admin["permission_level"], "未知")
                result.append({
                    "admin_id": admin["admin_id"],
                    "admin_name": admin["admin_name"],
                    "permission_level": admin["permission_level"],
                    "level_text": level_text,
                    "created_at": admin["created_at"].strftime("%Y-%m-%d") if admin["created_at"] else "未知"
                })

            return result

        except Exception as e:
            logger.error(f"获取管理员列表失败: {e}", exc_info=True)
            return []
