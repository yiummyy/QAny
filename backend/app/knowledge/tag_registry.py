"""每个知识库的预设标签 & 标签→KB 反向映射 — 单源真理."""

KB_TAGS: dict[str, list[str]] = {
    "qa": ["差旅交通", "奖金激励", "入职须知", "通知文件", "业务规则"],
    "ticket": ["网络故障", "账号权限", "硬件报修", "软件安装", "系统异常"],
    "sales": ["产品报价", "竞品分析", "客户案例", "营销话术", "投放策略"],
    "ops": ["监控告警", "部署变更", "备份恢复", "日志排查", "性能优化"],
}

ALL_TAGS: list[str] = sorted({t for tags in KB_TAGS.values() for t in tags})

TAG_TO_KB: dict[str, str] = {
    tag: kb for kb, tags in KB_TAGS.items() for tag in tags
}
