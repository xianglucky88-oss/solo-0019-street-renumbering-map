# 街段门牌换号谱

市政历史地名整理员使用的离线数据处理服务。把日期、街段和门号段变更关联成可前推和反查的地址证据；无覆盖不补号，多来源不抹平。

| 入口 | 工作流 | 样例结果 | 合成输入 |
| --- | --- | --- | --- |
| `POST /doorfolio/forward` | 按有效日推演门牌 | 苇岸道 13 号得到旧栈巷 31 号与西汊路 42 号，保留不同登记路径 | [`forward.json`](examples/forward.json) |
| `POST /doorfolio/reverse` | 从现门牌反查前址 | 西汊路 42 号反查到苇岸道 13 号，依次引用 N9、N7 | [`reverse.json`](examples/reverse.json) |
| `POST /doorfolio/inspect` | 给出规则冲突及证据 | N7 和 N8 的旧号重叠，首个共同门号为 13 | [`inspect.json`](examples/inspect.json) |

使用 Python 3.10+ 标准库，无需安装依赖；无需数据库、账户或外部服务。

```sh
python3 -B -m doorfolio.app --port 8821
```

运行于 `127.0.0.1:8821`，`GET /health` 列出操作。可以用另一终端向服务发送样例：

```sh
curl -sS -H 'Content-Type: application/json' --data-binary @examples/forward.json http://127.0.0.1:8821/doorfolio/forward
```

不启动监听器也可以从项目根目录复核生产 WSGI 入口，以下各命令同时核对可预期输出及拒绝表示：

```sh
python3 -B -m examples.check forward
python3 -B -m examples.check reverse
python3 -B -m examples.check inspect
```

本仓不含自动化测试套件；上述命令为公开示例和有界工作流检查。字段、规则和限制见 [PROJECT_SPEC.md](PROJECT_SPEC.md)。
