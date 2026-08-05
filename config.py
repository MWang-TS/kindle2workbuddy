# -*- coding: utf-8 -*-
"""kindle-dashboard 项目数据配置
多项目进度看板数据源，手动维护状态。
"""

# 多项目进度看板（dashboard 中部显示）
# status: done / active / pending / blocked
PROJECTS = [
    {
        "name": "YOLO laogang-ft",
        "detail": "Helmet v2 mAP50=0.942 freeze=7",
        "status": "active",
        "progress": 85,
    },
    {
        "name": "香港西九龙 微调",
        "detail": "helmet_vest-yilihk-20260722",
        "status": "active",
        "progress": 45,
    },
    {
        "name": "公众号内容创作",
        "detail": "印度vs巴基斯坦章节 配图",
        "status": "active",
        "progress": 60,
    },
    {
        "name": "售电/电力市场PPT",
        "detail": "内容结构与视觉设计",
        "status": "active",
        "progress": 30,
    },
    {
        "name": "轻奢室内设计",
        "detail": "5人居住 预算15万",
        "status": "pending",
        "progress": 10,
    },
    {
        "name": "ZARA连衣裙海报",
        "detail": "田曦薇 9:16竖版",
        "status": "pending",
        "progress": 5,
    },
    {
        "name": "高校影视课程分析",
        "detail": "广电编导/戏文/摄制 比较",
        "status": "active",
        "progress": 50,
    },
    {
        "name": "World Cup 2026",
        "detail": "每日10:00飞书简报",
        "status": "done",
        "progress": 100,
    },
]

# 今日待办（dashboard 底部显示，预留手动更新）
TODOS = [
    "Helmet模型裁剪与性能验证",
    "西九龙视频数据集整理(rawN子文件夹)",
    "公众号印度章节高亮笔记汇总",
    "Ubuntu启动慢/网络异常诊断",
]

# 今日日程（预留飞书API接入，当前为占位）
SCHEDULE = [
    # 飞书连接器接入后自动填充
]

# 状态图标映射（e-ink无emoji，用文字标记）
STATUS_MARK = {
    "done": "[x]",
    "active": "[~]",
    "pending": "[ ]",
    "blocked": "[!]",
}

# 自动化任务简称映射（dashboard显示用）
SHORT_NAME = {
    "World Cup 2026 Daily Brief": "WC简报",
    "World Cup 2026 Daily Brief - Feishu": "WC简报-飞书",
    "AI HOT 晨报": "AI HOT晨报",
    "公众号灵感": "公众号灵感",
}
