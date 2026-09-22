"""把当前完整合成数据导出成可审阅、可重放的迁移输入。

这不是重新生成一份相似数据：people()/policy() 读取的就是当前使用的
SQLite 人员快照及规则。首次启动时，ensure() 才创建原有确定性样本。
本文件只在宿主机运行；Superset 容器不需要导入应用或安装应用依赖。
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local" / "application"
REPO = ROOT.parents[1]


def snapshot():
    # 使用仓库源码作为唯一真源；避免另外手抄一份字段表发生漂移。
    sys.path.insert(0, str(REPO))
    from backend.hr import store
    from backend.hr.schema import FIELDS

    store.ensure()
    # 读取的是确定性合成基线，不是线上 Superset 结果；供迁移及独立验收比较。
    # 仅导出不会改变 Superset 中已有数据库、角色或规则。
    rows = store.people()
    fingerprint = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": 1,
        "manual_learning": (LOCAL / "manual-learning.json").exists(),
        "source": "backend.hr.store.people()/policy()",
        "as_of": store.AS_OF,
        "data_version": store.DATA_VERSION,
        "data_fingerprint": fingerprint,
        "row_count": len(rows),
        "fields": [{"id": key, "label": value[0], "group": value[1], "description": value[2],
                    "sql_type": "integer" if key == "age" else "text"} for key, value in FIELDS.items()],
        # persona.id 是应用身份，person_id 是人员主键；此时尚没有 Superset user.id。
        "personas": store.PERSONAS,
        "policy": store.policy(),
        "people": rows,
    }


def main():
    data = snapshot()
    LOCAL.mkdir(parents=True, exist_ok=True)
    target = LOCAL / "fixtures.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    # 宿主机 .local 为私有目录；容器单独只读挂载此文件，UID 可与宿主机不同。
    # 这里只开放合成导入样本的读取，绝不修改同目录 credentials.json 的 0600 权限。
    target.chmod(0o644)
    print(f"已导出 {data['row_count']} 人、{len(data['fields'])} 字段、{len(data['personas'])} 个身份：{target}")
    return data


if __name__ == "__main__":
    main()
