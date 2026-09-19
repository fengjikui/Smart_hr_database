"""把当前 V2 的完整合成数据导出成可审阅、可重放的迁移输入。

这不是重新生成一份相似数据：people()/policy() 读取的就是当前 V2 使用的
SQLite 人员快照及规则。首次尚未启动 V2 时，ensure() 才创建原有确定性样本。
本文件只在宿主机运行；Superset 容器不需要导入应用或安装应用依赖。
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT.parent / ".local" / "v2"
REPO = ROOT.parents[2]


def snapshot():
    # 使用仓库源码作为唯一真源；避免另外手抄一份字段表发生漂移。
    sys.path.insert(0, str(REPO))
    from backend.hr.v2 import store
    from backend.hr.v2.schema import FIELDS

    store.ensure()
    rows = store.people()
    fingerprint = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": 1,
        "source": "backend.hr.v2.store.people()/policy()",
        "as_of": store.AS_OF,
        "data_version": store.DATA_VERSION,
        "data_fingerprint": fingerprint,
        "row_count": len(rows),
        "fields": [{"id": key, "label": value[0], "group": value[1], "description": value[2],
                    "sql_type": "integer" if key == "age" else "text"} for key, value in FIELDS.items()],
        "personas": store.PERSONAS,
        "policy": store.policy(),
        "people": rows,
    }


def main():
    data = snapshot()
    LOCAL.mkdir(parents=True, exist_ok=True)
    target = LOCAL / "fixtures.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"已导出 {data['row_count']} 人、{len(data['fields'])} 字段、{len(data['personas'])} 个身份：{target}")
    return data


if __name__ == "__main__":
    main()
