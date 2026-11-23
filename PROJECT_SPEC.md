# 街段门牌换号谱 · 数据与接口规范

## 使用者和交付

使用者：市政历史地名整理员。把日期、街段和门号段变更关联成可前推和反查的地址证据；无覆盖不补号，多来源不抹平。 所有样例为合成数据。服务无跨请求状态或数据持久化，不连接外部接口。

## 规则和输入

- 输入 `notices`：最多 128 条，`id` 唯一；每条含 `effective`、`before` 和 `after`。街段为 `street`、`first`、`last`、`stride`（1 或 2）。两个门号段必须等长，按位置而不是号码差配对；书面顺序允许倒序。
- `forward` 和 `reverse` 另收 `address:{street,number}`、`from`、`to`。资料只在 `(from,to]` 生效。前查从早往晚用旧段，反查从晚往早追溯显式新段；没有命中则照带。反查是档案规则反查，不声称枚举现实中未登记的地址。一天内按同一入参处理全部规则，不用当日另一条规则作后继。多个同址路径全部返回，超过 512 条活跃路径拒绝该次请求。
- `inspect` 查同日的旧段和新段重叠，报告每对登记的一个实际门号见证；交叉范围相交但奇偶不符不算。见证是重叠，不断言哪个来源错误。

## 入口和可观察结果

| 入口 | 工作流 | 样例结果 | 合成输入 |
| --- | --- | --- | --- |
| `POST /doorfolio/forward` | 按有效日推演门牌 | 苇岸道 13 号得到旧栈巷 31 号与西汊路 42 号，保留不同登记路径 | [`forward.json`](examples/forward.json) |
| `POST /doorfolio/reverse` | 从现门牌反查前址 | 西汊路 42 号反查到苇岸道 13 号，依次引用 N9、N7 | [`reverse.json`](examples/reverse.json) |
| `POST /doorfolio/inspect` | 给出规则冲突及证据 | N7 和 N8 的旧号重叠，首个共同门号为 13 | [`inspect.json`](examples/inspect.json) |

`POST` 接收不大于 512 KiB 的 UTF-8 JSON，要求 `application/json`。字段缺失、主键重复、非法范围或冲突合同返回 HTTP 400。可合法表达的未解业务状态仍为 HTTP 200。健康接口为 `GET /health`。

## 代码职责

- `doorfolio/app.py`：注册该服务公开数据入口。
- `doorfolio/http_service.py`：限定请求方法、内容体积和 JSON 传输边界。
- `doorfolio/contract.py`：严格字段、范围及标识去重。
- `doorfolio/segment.py`：段内按位换号。
- `doorfolio/walk.py`：分日分支推演。
- `doorfolio/lookup.py`：双向档案查找。

请求由 WSGI 入口分发给对应领域归约，边界字段由校验层及领域解析器检查；证据随归约返回，不作为后置猜测。对外入口的运行步骤和输出核对见 README。单元测试留置；不含故障预埋、私有评审或后续任务解法。
