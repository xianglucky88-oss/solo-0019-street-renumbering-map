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

## 离线换号册（folio）

查阅台拿不到整本市政底册时，馆员开一份只覆盖授权街廓和固定 `(from,to]` 窗口的离线册，分页交付、随到随查。册状态只存在于本工作进程，不写盘、不联外部接口；各册的页彼此隔离，另一册的同编号页不能补本册缺页。

- `POST /doorfolio/booklet_open`：收 `booklet_id`、`from`、`to`、`scopes`（街名+首尾号+步长，最多 64 块）和带 `page` 引证的目录公告（最多 128 条）。服务沿前查与显式新号反查两条路径，用整数区间运算裁出每则公告**确实会走到的配对偏移区间** `needs`；长号段不逐门生成。目录公告不整本入册，只有 `needs` 命中的配对允许交付。
- `POST /doorfolio/booklet_deliver`：按 `page` 分批交付片段。片段必须是某侧（`before`/`after`）位置对齐的 `needs` 子段；夹带本册不需要的配对、页与公告引证不符、与已交付配对重叠均返回 400。沿用 512 KiB 单请求限制，每批片段最多 128 条；馆员可多次交付。
- `POST /doorfolio/booklet_status`：报告该册 `expected_pages`、`delivered_pages`、`missing_pages` 与是否完整。
- `POST /doorfolio/booklet_forward` / `booklet_reverse`：在授权街廓内做带证据的前查与显式新号反查。入参地址不在授权街廓返回 HTTP 200 且 `status=out_of_scope`；换号中途经过的未开放街可作为路径上的中间地址显示，但不能单独查询该街。
- 查询状态严格区分：证据齐全且未换号为 `unchanged`；证据齐全且换号为 `mapped`（同址多路径合并，沿用旧口径；多个不同候选地址为 `ambiguous`）；存在尚可到达但页未到的分支时为 `incomplete`，`candidates` 只列证据齐全的分支，`pending` 点名缺的是哪份 `page`、哪条公告、在哪个门号处断链——即使现存分支末址相同也不得报成完整答案；不依赖缺页的另一号段照常可查。
- 倒排书面顺序、单双号步长、同日规则不串接全部沿用既有口径；路径每跳同时带 `notice_id` 与交付 `page` 作为公告引证。活跃路径超过 512 条拒绝该次请求。

## 代码职责

- `doorfolio/app.py`：注册该服务公开数据入口。
- `doorfolio/http_service.py`：限定请求方法、内容体积和 JSON 传输边界。
- `doorfolio/contract.py`：严格字段、范围及标识去重。
- `doorfolio/segment.py`：段内按位换号。
- `doorfolio/walk.py`：分日分支推演。
- `doorfolio/lookup.py`：双向档案查找。
- `doorfolio/folio.py`：换号册街廓授权、偏移区间运算、需求裁剪与片段校验。
- `doorfolio/registry.py`：进程内换号册登记、分页交付与完整度判定。
- `doorfolio/bookwalk.py`：带交付证据与缺页见证的分日推演。
- `doorfolio/folio_lookup.py`：换号册前查与显式新号反查归约。

请求由 WSGI 入口分发给对应领域归约，边界字段由校验层及领域解析器检查；证据随归约返回，不作为后置猜测。对外入口的运行步骤和输出核对见 README。单元测试留置；不含故障预埋、私有评审或后续任务解法。
