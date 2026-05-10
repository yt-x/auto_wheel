"""
依赖树确认闸口规则。
"""


def should_block_download(require_tree_approval: bool, tree_approved: bool, plan_only: bool) -> bool:
    """
    判断当前任务是否需要阻断下载。

    规则：
    - 预览模式不下载，不阻断；
    - 启用确认闸口且未确认时阻断；
    - 其他情况放行。
    """
    if plan_only:
        return False
    if require_tree_approval and not tree_approved:
        return True
    return False

