"""课堂数据生成器：只用 Python 标准库，不读取真实员工，也不连接数据库。

先运行此文件、阅读输出，再看 setup.py 如何把这些记录写入 PostgreSQL。
数据刻意保持很小且完全确定：不使用当前日期、随机数或真实客户资料。
因此，每次生成的内容相同，学生可以手算总数、金额和授权名单。
"""

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT.parent / ".local" / "classroom"

# 这是组织主数据，不是授权结果。每行只保存直属主管和直接 HRBP。
# D 管 E/F/H，F 管 G，H 管 I，故 D 的管理范围跨两个部门。
# C 服务 J，但不服务 J 的下属 K：用来发现错误的 HRBP 递归扩权。
PERSON_FACTS = [
    ("A", "模拟总经理", "总经办", None, None),
    ("B", "模拟人力负责人", "人力资源部", "A", None),
    ("C", "模拟HRBP甲", "人力资源部", "B", None),
    ("D", "模拟华东主管", "华东销售部", "A", "C"),
    ("E", "模拟华东销售甲", "华东销售部", "D", "C"),
    ("F", "模拟华东组长", "华东销售部", "D", "C"),
    ("G", "模拟华东销售乙", "华东销售部", "F", "C"),
    ("H", "模拟战略客户主管", "战略客户部", "D", "X"),
    ("I", "模拟华西销售", "战略客户部", "H", "X"),
    ("J", "模拟华北主管", "华北销售部", "A", "C"),
    ("K", "模拟华北销售", "华北销售部", "J", "X"),
    ("X", "模拟HRBP乙", "人力资源部", "A", None),
]

# 学习账号与人员 ID 是显式映射，不能用姓名、岗位猜测身份。
# finance 是一个批准的学习角色，不从 X 的岗位名称自动推导。
USERS = [
    ("learn_east", "E", "LEARN_East", "employee", ["EAST"]),
    ("learn_west", "I", "LEARN_West", "employee", ["WEST"]),
    ("learn_manager", "D", "LEARN_Manager", "manager", ["EAST", "WEST"]),
    ("learn_hrbp", "C", "LEARN_HRBP", "hrbp", []),
    ("learn_hrlead", "B", "LEARN_HRLead", "hrlead", []),
    ("learn_finance", "X", "LEARN_Finance", "employee", ["EAST", "WEST", "NORTH"]),
    ("learn_unmapped", None, "LEARN_Unmapped", "employee", []),
]

# 人工预先写出的标准答案。不要调用 SQL 授权算法来生成自己的标准答案。
EXPECTED = {
    "all_order_count": 12,
    "all_order_amount": 78000,
    "east_order_ids": ["O001", "O002", "O003", "O004", "O005", "O006"],
    "west_order_ids": ["O007", "O008", "O009"],
    "north_order_ids": ["O010", "O011", "O012"],
    "east_amount": 21000,
    "west_amount": 24000,
    "north_amount": 33000,
    "east_public_ids": ["O001", "O002", "O004", "O005"],
    "east_or_public_count": 10,
    "own_east_ids": ["O001", "O002", "O003"],
    "manager_people": ["D", "E", "F", "G", "H", "I"],
    "manager_department_people": ["D", "E", "F", "G"],
    "hrbp_people": ["C", "D", "E", "F", "G", "J"],
    "hrlead_people": ["B", "C", "D", "E", "F", "G", "J"],
}


def generate():
    """返回业务事实；不做任何 Superset 权限配置。"""
    people, payroll = [], []
    for index, (person_id, name, department, manager, hrbp) in enumerate(PERSON_FACTS, 1):
        people.append({
            "person_id": person_id,
            "employee_no": f"{index:08d}",  # 工号用字符串，保留前导零。
            "name": name,
            "department": department,
            "manager_id": manager,
            "hrbp_id": hrbp,
            "education": "博士" if person_id in {"D", "G", "K"} else "本科",
        })
        # 薪资放单独业务表，便于观察连接账号和数据集两层边界。
        payroll.append({"person_id": person_id, "salary": 10000 + index * 1000})

    orders = []
    # 四名销售各三单；E/G 的六单属于 EAST，I 三单 WEST，K 三单 NORTH。
    for owner, region in [("E", "EAST"), ("G", "EAST"), ("I", "WEST"), ("K", "NORTH")]:
        for _ in range(3):
            index = len(orders) + 1
            orders.append({
                "order_id": f"O{index:03d}",
                "owner_id": owner,
                "region": region,
                "order_date": date(2026, 9, index).isoformat(),
                "amount": index * 1000,  # 整数金额，避免浮点误差干扰教学。
                "classification": "RESTRICTED" if index % 3 == 0 else "PUBLIC",
                "customer_name": f"模拟客户{index:03d}",
                # 非真实手机号；仅模仿 11 字符形态，不生成可拨打号码。
                "customer_phone": f"0000000{index:04d}",
            })
    return {"people": people, "payroll": payroll, "orders": orders, "expected": EXPECTED}


def main():
    """数据落盘只是生成阶段；不会启动服务或重置学生刚填的规则。"""
    LOCAL.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = LOCAL / "generated-data.json"
    path.write_text(json.dumps(generate(), ensure_ascii=False, indent=2) + "\n")
    print(f"已生成 12 名模拟员工、12 条薪资、12 笔订单：{path}")


if __name__ == "__main__":
    main()
