# -*- coding: utf-8 -*-
"""默认模式（关）下的敏感实操预检。

判定原则：动词 + 对象 双命中才拦，避免误伤「冰毒是什么」「如何戒毒」这类正常问题。
暴力类词汇冲击性太强（杀人/绑架/下毒），对象词单命中即拦，豁免词兜底科普/文娱向问法。
"""
from __future__ import annotations

# 对象词（含中英文别名，统一小写比对）
_SUBSTANCES = (
    "冰毒", "甲基苯丙胺", "海洛因", "可卡因", "氯胺酮", "k粉", "摇头丸",
    "芬太尼", "麻黄碱", "tnt", "硝化甘油", "c4", "土制炸弹", "土炸弹",
    "雷管", "氰化钾", "氰化物", "毒鼠强", "蓖麻毒素", "沙林", "芥子气",
    "枪", "炸药",
)

# 制作类动词/场景词
_ACTIONS = (
    "制作", "制造", "合成", "自制", "配方", "工艺", "怎么弄", "怎么做",
    "如何做", "如何制", "怎么制", "提取", "配比", "土法", "造一个",
    "搞一个", "整一个",
)

# 暴力/人身伤害类对象词：单命中即拦
_VIOLENCE = (
    "杀人", "伤人", "害人", "打人", "绑架", "劫持", "抢劫", "下毒",
    "投毒", "肢解", "分尸", "碎尸", "自杀",
)

# 豁免：戒毒、科普、防身知识类不拦
_EXEMPT = ("戒毒", "危害", "历史", "是什么", "科普", "戒断", "远离", "禁毒")

# 暴力词豁免：文娱/社科类正常问法不拦
_VIOLENCE_EXEMPT = ("游戏", "小说", "电影", "电视剧", "动漫", "剧情", "角色", "案件")

RESTRICTED_REPLY = "这个我不能说，换个别的话题吧。"


def is_restricted(text: str) -> bool:
    t = text.lower()
    if any(e in t for e in _EXEMPT):
        return False
    if any(v in t for v in _VIOLENCE) and not any(e in t for e in _VIOLENCE_EXEMPT):
        return True
    return any(a in t for a in _ACTIONS) and any(s in t for s in _SUBSTANCES)
