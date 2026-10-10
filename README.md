# xweb-ops

x.com web client (x-web, Relay persisted queries) GraphQL bindings, extracted from the public web JS bundle.

`xweb-ops.json` (schema 1):

| field | meaning |
| --- | --- |
| `schema` | format version (`1`) |
| `snapshot` | web build id the bindings were taken from |
| `generated_at` | generation time, RFC 3339 |
| `ops.<operationName>.query_id` | persisted query id |
| `ops.<operationName>.type` | `query` or `mutation` |
| `ops.<operationName>.variables` | variable names declared by the web client |
| `ops.<operationName>.provided_variables` | Relay provided variable values (`__relay_internal__pv__*`) |

Only publicly visible data is published here. Commit only when content changes.
