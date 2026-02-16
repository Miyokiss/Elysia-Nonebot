from tortoise import fields
from src.clover_sqlite.data_init.db_connect import Model

class chat_admin_user_permissions(Model):
    """
    管理权限用户表
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    user_id = fields.CharField(max_length=128,description="user_id")
    allow_private_chat = fields.BooleanField(default=False, description="是否允许私聊使用")
    is_banned = fields.BooleanField(default=False, description="是否被全局封禁")
    admin_id = fields.CharField(max_length=128, description="操作的管理员ID")
    updated_at = fields.DatetimeField(description="最后修改时间")
    class Meta:
        # 指定表名
        table = "chat_admin_user_permissions"
        table_description = "管理权限用户表"


class chat_admin_group_permissions(Model):
    """
    管理权群组表
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    group_id = fields.CharField(max_length=128, description="群ID")
    is_allowed = fields.BooleanField(default=False, description="是否允许该群使用功能")
    admin_id = fields.CharField(max_length=128, description="操作人")
    updated_at = fields.DatetimeField(description="最后更新时间")

    class Meta:
        # 指定表名
        table = "chat_admin_group_permissions"
        table_description = "管理权群组表"

class chat_admin_list(Model):
    """
    管理列表
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    admin_id = fields.CharField(max_length=128, description="管理员ID")
    admin_name = fields.CharField(max_length=128, description="管理员名称")
    permission_level = fields.IntField(default=1, description="权限等级")
    created_at = fields.DatetimeField(description="创建时间")

    class Meta:
        # 指定表名
        table = "chat_admin_list"
        table_description = "管理列表"


class chat_application_form(Model):
    """
    chat申请表
    """
    id = fields.IntField(primary_key=True, generated=True, auto_increment=True)
    applicant_id = fields.CharField(max_length=128, description="申请人ID", index=True)
    group_id = fields.CharField(max_length=128, description="群ID", index=True)
    reason = fields.TextField(description="申请理由/备注")
    status = fields.IntField(default=0, description="状态：0-待审批，1-已同意，2-已拒绝")
    admin_id = fields.CharField(max_length=128, description="处理人ID（管理员名称或ID）", null=True)
    apply_time = fields.DatetimeField(description="申请时间")
    handle_time = fields.DatetimeField(description="处理时间", null=True)
    refuse_reason = fields.TextField(description="拒绝理由", null=True)

    class Meta:
        # 指定表名
        table = "chat_application_form"
        table_description = "chat申请表"