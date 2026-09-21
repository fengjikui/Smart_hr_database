// 使用 OpenFGA 官方转换器，不自行解释 DSL 的 and/or/递归语义。
import { readFileSync } from 'node:fs';
import { transformer } from '@openfga/syntax-transformer';
const dsl = readFileSync(0, 'utf8');
process.stdout.write(JSON.stringify(transformer.transformDSLToJSONObject(dsl)));
