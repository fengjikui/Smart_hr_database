import json
from functools import lru_cache

from . import config
from .db import application


@lru_cache(maxsize=1)
def catalog():
    return json.loads(config.CATALOG_PATH.read_text())


def metric(metric_id: str):
    return next(m for m in catalog()['metrics'] if m['id']==metric_id)


def visible_catalog(principal):
    return [m for m in catalog()['metrics'] if m['sensitivity']=='internal' or principal['salary_aggregate']]


def search(principal, query=''):
    allowed=visible_catalog(principal)
    if not query:
        return allowed
    # Chinese one/two-character terms use exact substring matching; longer prose
    # benefits from the derived FTS5 trigram index. Neither source can grant access.
    lowered=query.casefold().strip()
    hits={m['id'] for m in allowed if lowered in json.dumps(m,ensure_ascii=False).casefold()}
    if len(lowered)>=3:
        with application() as db:
            found=db.execute('SELECT id FROM metric_search WHERE metric_search MATCH ? LIMIT 30',('"'+lowered.replace('"','""')+'"',)).fetchall()
            hits.update(r[0] for r in found)
    return [m for m in allowed if m['id'] in hits]
