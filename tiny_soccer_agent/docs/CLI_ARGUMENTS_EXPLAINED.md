# CLI 参数解析初学者讲解

这份文档解释 [cli.py](../cli.py) 里“命令行参数是怎么被解析”的。

我们主要围绕这条命令讲：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

## 1. 先把命令拆开

这条命令可以拆成几段：

```text
python
-m
tiny_soccer_agent.cli
ingest
--limit-matches
3
--db
artifacts\tools_llm_smoke.db
```

含义分别是：

| 片段 | 含义 |
|---|---|
| `python` | 使用当前环境里的 Python |
| `-m` | 以模块方式运行 |
| `tiny_soccer_agent.cli` | 运行 `tiny_soccer_agent/cli.py` |
| `ingest` | 子命令，表示执行导入数据 |
| `--limit-matches` | 参数名，限制导入多少场比赛 |
| `3` | 参数值，表示导入 3 场比赛 |
| `--db` | 参数名，指定数据库路径 |
| `artifacts\tools_llm_smoke.db` | 参数值，数据库文件路径 |

所以你可以先理解成：

```text
请运行 cli.py，并告诉它：
我要执行 ingest；
最多导入 3 场比赛；
数据库放在 artifacts\tools_llm_smoke.db。
```

## 2. 什么是命令行参数

当你在终端输入：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

后面这些内容：

```text
ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

就会被传给 Python 程序。

程序需要把它们解析成 Python 里能用的变量。

例如：

```python
args.command = "ingest"
args.limit_matches = 3
args.db = "artifacts\\tools_llm_smoke.db"
```

这个“从命令行字符串变成 Python 变量”的过程，就叫：

```text
命令行参数解析
```

## 3. argparse 是什么

`cli.py` 里有：

```python
import argparse
```

`argparse` 是 Python 标准库自带的命令行参数解析工具。

它可以帮我们做几件事：

- 定义程序支持哪些命令
- 定义每个命令支持哪些参数
- 把终端输入解析成 Python 对象
- 自动生成 `--help` 帮助信息
- 用户输入错参数时自动报错

比如你执行：

```powershell
python -m tiny_soccer_agent.cli --help
```

能看到帮助信息，就是 `argparse` 自动生成的。

## 4. main() 是入口

`cli.py` 里有：

```python
def main(argv: List[str] | None = None) -> int:
```

这就是 CLI 程序的主入口。

`argv` 可以先理解为：

```text
命令行参数列表
```

如果你没有手动传 `argv`，`argparse` 会自动读取终端里输入的参数。

### 4.0 `argv` 是什么意思

先看这一整行：

```python
def main(argv: List[str] | None = None) -> int:
```

这里的 `argv` 是一个参数名。

它不是 Python 关键字，只是程序员常用的命名习惯。

`argv` 来自英文：

```text
argument vector
```

可以先不用纠结 `vector` 这个词。在这里，你可以把它理解成：

```text
命令行参数列表
```

也就是用户在终端输入的那些参数。

比如你执行：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

真正交给 `cli.py` 解析的主要是后面这一段：

```text
ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

如果写成 Python 里的 list，大概就是：

```python
[
    "ingest",
    "--limit-matches",
    "3",
    "--db",
    "artifacts\\tools_llm_smoke.db",
]
```

这就是 `argv` 想表达的东西。

所以：

```python
argv
```

可以理解成：

```text
准备交给 argparse 解析的命令行参数列表
```

注意，这里一般不包括：

```text
python
-m
tiny_soccer_agent.cli
```

因为这几段是用来告诉 Python “运行哪个模块”的，不是 `cli.py` 自己要解析的业务参数。

`cli.py` 真正关心的是：

```text
ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

### 4.0.1 `List[str]` 是什么意思

函数签名里有：

```python
argv: List[str]
```

这叫类型标注。

意思是：

```text
argv 应该是一个 list；
这个 list 里面的每个元素都应该是字符串 str。
```

比如：

```python
["ingest", "--limit-matches", "3"]
```

就是一个 `List[str]`。

注意，命令行传进来的内容一开始通常都是字符串。

哪怕你在终端里写的是：

```powershell
--limit-matches 3
```

这里的 `3` 一开始也更像字符串：

```python
"3"
```

后面是 `argparse` 根据我们注册参数时写的：

```python
type=int
```

才把它转换成整数：

```python
3
```

### 4.0.2 `| None` 是什么意思

函数签名里还有：

```python
List[str] | None
```

意思是：

```text
argv 可以是 List[str]；
argv 也可以是 None。
```

也就是这两种都可以：

```python
main(["ingest", "--limit-matches", "3"])
```

或者：

```python
main()
```

当你写：

```python
main()
```

没有传 `argv` 时，`argv` 就会使用默认值：

```python
None
```

### 4.0.3 `= None` 是什么意思

这一段：

```python
argv: List[str] | None = None
```

里的 `= None` 表示：

```text
如果调用 main() 时没有传 argv，
那么 argv 默认就是 None。
```

所以：

```python
main()
```

等价于：

```python
main(argv=None)
```

在本项目里，文件最后调用的是：

```python
raise SystemExit(main())
```

也就是说，它没有手动传 `argv`。

因此这次调用里：

```python
argv = None
```

### 4.0.4 `argv=None` 时参数从哪里来

你可能会问：

```text
既然 argv 是 None，那程序怎么知道我在终端输入了什么？
```

关键在这行：

```python
args = parser.parse_args(argv)
```

如果 `argv` 是 `None`，`argparse` 会自动去读取终端里真实输入的参数。

也就是说：

```python
parser.parse_args(None)
```

大致可以理解成：

```text
请 argparse 自己从当前终端命令里读取参数。
```

所以正常运行时：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

虽然我们调用的是：

```python
main()
```

但 `argparse` 仍然能读到：

```text
ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

### 4.0.5 那为什么还要设计 `argv` 这个参数

既然正常运行时可以不传 `argv`，为什么函数还要写：

```python
def main(argv: List[str] | None = None) -> int:
```

而不是直接写：

```python
def main() -> int:
```

主要是为了方便测试和复用。

比如我们可以在 Python 代码里手动模拟一条命令：

```python
main([
    "ingest",
    "--limit-matches",
    "3",
    "--db",
    "artifacts\\tools_llm_smoke.db",
])
```

这样就不需要真的打开终端输入命令，也能测试 `ingest` 子命令能不能正确解析。

所以可以这样理解：

```text
正常用户运行：
    main()
    argv = None
    argparse 自动读终端

程序员测试时：
    main(["ingest", "--limit-matches", "3"])
    argparse 解析这份手动传入的列表
```

### 4.0.6 当前项目里的完整理解

这一行：

```python
def main(argv: List[str] | None = None) -> int:
```

可以翻译成：

```text
定义一个 main 函数。

它可以接收一个叫 argv 的参数。
argv 要么是字符串列表，要么是 None。
如果调用 main 时没有传 argv，就默认使用 None。
main 最后会返回一个整数，这个整数通常作为命令行程序的退出码。
```

对应到本项目：

```python
raise SystemExit(main())
```

这里没有传 `argv`，所以 `argv=None`。

然后：

```python
args = parser.parse_args(argv)
```

等价于让 `argparse` 自动读取你终端里输入的：

```text
ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

文件最后还有：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

这两行是 Python 文件里非常常见的“程序入口写法”。

先给一个直观理解：

```text
如果 cli.py 是被直接运行的：
    就执行 main()
否则：
    只加载这个文件里的函数和类，不自动执行 main()
```

也就是说，它在判断：

```text
这个文件现在是“主程序”吗？
```

如果答案是“是”，才真正开始跑命令行程序。

### 4.1 `__name__` 是什么

`__name__` 是 Python 自动提供的一个特殊变量。

每个 Python 文件被运行或导入时，Python 都会给它设置一个 `__name__`。

可以先把它理解成：

```text
当前这个 Python 文件在运行时的名字
```

比如有一个文件：

```text
tiny_soccer_agent/cli.py
```

当它被正常导入时：

```python
import tiny_soccer_agent.cli
```

这个文件里的 `__name__` 大概会是：

```python
"tiny_soccer_agent.cli"
```

意思是：

```text
我是 tiny_soccer_agent 包里的 cli 模块。
```

但是，当这个文件被当作主程序运行时：

```powershell
python -m tiny_soccer_agent.cli
```

Python 会把这个文件的 `__name__` 设置成：

```python
"__main__"
```

意思是：

```text
我现在不是普通模块，我现在是这次程序运行的入口。
```

所以这行：

```python
if __name__ == "__main__":
```

可以翻译成：

```text
如果当前文件是主程序入口：
```

注意，`"__main__"` 只是一个字符串。

它不是函数，也不是类。

它只是 Python 用来标记“当前入口文件”的特殊名字。

### 4.2 为什么需要这个判断

如果没有这个判断，文件里的代码可能会在“被导入”时也自动执行。

比如别的文件只是想复用 `cli.py` 里的某个函数：

```python
from tiny_soccer_agent.cli import main
```

如果 `cli.py` 底部直接写：

```python
main()
```

那么一导入 `main`，命令行程序就会直接跑起来。

这通常不是我们想要的。

我们想要的是：

```text
被 import 的时候：
    只提供函数，不自动运行

被 python -m tiny_soccer_agent.cli 运行的时候：
    才真正执行 main()
```

所以要写：

```python
if __name__ == "__main__":
    ...
```

这相当于给文件加了一个“只有直接运行才启动”的开关。

### 4.3 `main()` 做了什么

在本项目里，`main()` 是命令行程序真正开始工作的地方。

它会做这些事：

```text
创建 parser
注册 ingest / run-one / eval / export-training-data 子命令
注册每个子命令的参数
解析终端输入
根据用户输入调用对应的处理函数
返回退出码
```

比如你执行：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

这时底部入口代码会调用：

```python
main()
```

然后 `main()` 才会解析出：

```python
args.command = "ingest"
args.limit_matches = 3
args.db = "artifacts\\tools_llm_smoke.db"
```

最后调用：

```python
cmd_ingest(args)
```

### 4.4 为什么是 `raise SystemExit(main())`

这句代码可以拆成三层：

```python
main()
```

先执行 `main()`。

```python
SystemExit(main())
```

把 `main()` 的返回值交给 `SystemExit`。

```python
raise SystemExit(main())
```

抛出 `SystemExit`，让 Python 程序按照这个返回值退出。

这里最重要的是：`main()` 通常会返回一个整数。

在命令行程序里，这个整数叫：

```text
退出码
```

常见规则是：

| 返回值 | 含义 |
|---|---|
| `0` | 程序成功结束 |
| 非 `0` | 程序失败或异常结束 |

本项目里的 `main()` 定义是：

```python
def main(argv: List[str] | None = None) -> int:
```

最后如果执行成功，会返回：

```python
return 0
```

所以：

```python
raise SystemExit(main())
```

等价于：

```text
运行 main()
拿到 main() 的返回值
把这个返回值作为程序退出码
结束这个 Python 进程
```

如果 `main()` 返回 `0`，终端会认为程序执行成功。

如果 `main()` 返回 `1`，终端会认为程序执行失败。

### 4.5 为什么不用直接写 `main()`

技术上，下面这样也能运行：

```python
if __name__ == "__main__":
    main()
```

但对于命令行程序来说，更规范的是：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

原因是：

```text
main() 的返回值可以变成真正的命令行退出码。
```

这对自动化脚本、测试、CI/CD 都很重要。

比如别的程序可以根据退出码判断：

```text
这个命令成功了吗？
```

虽然你现在主要是在本地手动跑命令，但这是写 CLI 程序时很常见、很正规的写法。

### 4.6 放到当前项目里理解

这两行：

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

在 TinySoccerAgent 里可以翻译成：

```text
如果用户通过 python -m tiny_soccer_agent.cli 运行这个文件，
就启动命令行程序；
启动后，解析用户输入的是 ingest、run-one、eval 还是 export-training-data；
执行对应函数；
最后把执行结果作为退出码返回给终端。
```

所以执行链是：

```text
python -m tiny_soccer_agent.cli
  -> 运行 cli.py
  -> Python 设置 __name__ = "__main__"
  -> if 条件成立
  -> 调用 main()
  -> main() 创建 parser 并解析参数
  -> 调用对应子命令函数
  -> main() 返回 0
  -> SystemExit(0)
  -> 程序正常退出
```

## 5. 创建总 parser

`main()` 里第一步是：

```python
parser = argparse.ArgumentParser(description="TinySoccerAgent 事件驱动足球解说智能体编排框架")
```

这里创建了一个“总解析器”。

你可以把 `parser` 理解成：

```text
命令行参数翻译器
```

它负责把终端输入翻译成 Python 变量。

`description` 是帮助信息里的描述文本。

当你执行：

```powershell
python -m tiny_soccer_agent.cli --help
```

就会看到这段描述。

## 6. subparsers 是什么

接着有：

```python
subparsers = parser.add_subparsers(dest="command", required=True)
```

这行比较关键。

`subparsers` 表示：

```text
这个 CLI 下面有多个子命令。
```

本项目现在有四个子命令：

```text
ingest
run-one
eval
export-training-data
```

这就像 git 有很多子命令：

```text
git status
git add
git commit
git push
```

其中：

```python
dest="command"
```

表示把用户输入的子命令名字保存到：

```python
args.command
```

所以当你输入：

```powershell
... ingest ...
```

解析后就是：

```python
args.command == "ingest"
```

`required=True` 表示：

必须输入一个子命令。

如果你只输入：

```powershell
python -m tiny_soccer_agent.cli
```

不写 `ingest` / `run-one` / `eval`，程序就会报错。

## 7. 注册 ingest 子命令

接下来是：

```python
ingest_parser = subparsers.add_parser("ingest", help="将本地比赛 JSON 规范化写入 SQLite memory")
```

这行的意思是：

```text
注册一个叫 ingest 的子命令。
```

所以用户以后可以输入：

```powershell
python -m tiny_soccer_agent.cli ingest
```

`help` 是帮助信息。

## 8. 给 ingest 添加参数

然后有几行：

```python
ingest_parser.add_argument("--tar", default=DEFAULT_TAR, help="Game_dataset.tar.gz 路径")
ingest_parser.add_argument("--index", default=DEFAULT_INDEX, help="game_database.csv 路径")
ingest_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
ingest_parser.add_argument("--limit-matches", type=int, default=None, help="可选：限制 ingest 的比赛数量")
```

这些是在告诉程序：

```text
ingest 子命令支持哪些参数。
```

逐个解释。

### 8.1 --tar

```python
ingest_parser.add_argument("--tar", default=DEFAULT_TAR, help="Game_dataset.tar.gz 路径")
```

表示支持：

```powershell
--tar 某个路径
```

如果用户没写 `--tar`，就用默认值：

```python
DEFAULT_TAR = "database/Game_dataset.tar.gz"
```

所以你执行命令时没有写 `--tar`，实际等价于：

```powershell
--tar database/Game_dataset.tar.gz
```

### 8.2 --index

```python
ingest_parser.add_argument("--index", default=DEFAULT_INDEX, help="game_database.csv 路径")
```

如果用户没写 `--index`，就用默认值：

```python
DEFAULT_INDEX = "database/Game_dataset_csv/game_database.csv"
```

### 8.3 --db

```python
ingest_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
```

表示支持：

```powershell
--db artifacts\tools_llm_smoke.db
```

解析后：

```python
args.db = "artifacts\\tools_llm_smoke.db"
```

如果你不写 `--db`，就用默认值：

```python
DEFAULT_DB = "artifacts/tiny_soccer_agent.db"
```

### 8.4 --limit-matches

```python
ingest_parser.add_argument("--limit-matches", type=int, default=None, help="可选：限制 ingest 的比赛数量")
```

表示支持：

```powershell
--limit-matches 3
```

这里的：

```python
type=int
```

很重要。

命令行里所有东西原本都是字符串。

比如 `"3"` 原本是字符串。

`type=int` 会把它转换成整数：

```python
args.limit_matches = 3
```

如果没有 `type=int`，它会是：

```python
args.limit_matches = "3"
```

字符串 `"3"` 和整数 `3` 不一样。

后面 `ingest.py` 需要用它做数量限制，所以这里转成整数更合适。

## 9. set_defaults(func=cmd_ingest) 是什么

这行非常关键：

```python
ingest_parser.set_defaults(func=cmd_ingest)
```

意思是：

```text
如果用户选择了 ingest 子命令，就把 args.func 设置成 cmd_ingest。
```

也就是说，当你输入：

```powershell
python -m tiny_soccer_agent.cli ingest ...
```

解析后会得到：

```python
args.func = cmd_ingest
```

后面代码会统一执行：

```python
args.func(args)
```

于是就相当于执行：

```python
cmd_ingest(args)
```

这是一种常见 CLI 写法。

它避免写很多 if/elif：

```python
if args.command == "ingest":
    cmd_ingest(args)
elif args.command == "run-one":
    cmd_run_one(args)
elif args.command == "eval":
    cmd_eval(args)
```

用 `set_defaults(func=...)` 后，代码更简洁。

## 9.5 “注册”到底是什么意思

你现在已经注意到一个很重要的词：

```text
注册
```

在 CLI 代码里，“注册”不是“立刻执行”。

它更像是：

```text
先把规则登记到 argparse 里，等用户真正输入命令时，再按规则匹配和执行。
```

可以把 `argparse` 想象成一张命令规则表。

当代码执行这些语句时：

```python
parser = argparse.ArgumentParser(...)
subparsers = parser.add_subparsers(dest="command", required=True)
```

意思是：

```text
创建一张总的命令规则表。
```

然后：

```python
ingest_parser = subparsers.add_parser("ingest", help="将本地比赛 JSON 规范化写入 SQLite memory")
```

意思是：

```text
往规则表里登记一个子命令：ingest。
```

这一步不是在导入数据。

它只是告诉程序：

```text
以后如果用户输入 ingest，我认识这个命令。
```

接着：

```python
ingest_parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
ingest_parser.add_argument("--limit-matches", type=int, default=None, help="可选：限制 ingest 的比赛数量")
```

意思是：

```text
给 ingest 这个子命令登记它能接受的参数。
```

也就是说：

```text
以后如果用户在 ingest 后面输入 --db，我认识它；
以后如果用户在 ingest 后面输入 --limit-matches，我也认识它。
```

最后：

```python
ingest_parser.set_defaults(func=cmd_ingest)
```

意思是：

```text
给 ingest 这个子命令登记它对应的处理函数 cmd_ingest。
```

所以 `ingest` 的完整注册信息大概是：

```text
子命令名：ingest
可接受参数：
  --tar
  --index
  --db
  --limit-matches
处理函数：
  cmd_ingest
```

这就像你在系统里登记了一张表：

| 用户输入 | 程序知道什么 |
|---|---|
| `ingest` | 这是一个合法子命令 |
| `--db` | 这是 ingest 可以接受的参数 |
| `--limit-matches` | 这是 ingest 可以接受的参数，而且要转成 int |
| `cmd_ingest` | 匹配到 ingest 后最终要调用的函数 |

等用户真正输入：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

`argparse` 才会拿这条命令去和刚才登记好的规则表对照。

对照结果是：

```python
args.command = "ingest"
args.limit_matches = 3
args.db = "artifacts\\tools_llm_smoke.db"
args.func = cmd_ingest
```

然后：

```python
args.func(args)
```

才真正执行：

```python
cmd_ingest(args)
```

所以你可以这样记：

```text
add_parser 是注册子命令。
add_argument 是注册这个子命令能接受的参数。
set_defaults(func=...) 是注册这个子命令对应的处理函数。
parse_args 才是真正读取用户输入并匹配规则。
args.func(args) 才是真正执行功能。
```

更直观地说：

```text
注册阶段：
告诉 argparse：我有哪些命令、哪些参数、对应哪些函数。

解析阶段：
argparse 读取用户输入，判断用户选了哪个命令、传了哪些参数。

执行阶段：
调用对应函数，例如 cmd_ingest(args)。
```

## 10. parse_args 真正开始解析

注册完所有子命令和参数后，代码执行：

```python
args = parser.parse_args(argv)
```

这行才是真正开始解析。

如果你输入：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

那么 `parse_args` 会得到一个对象，大致像这样：

```python
args.command = "ingest"
args.tar = "database/Game_dataset.tar.gz"
args.index = "database/Game_dataset_csv/game_database.csv"
args.db = "artifacts\\tools_llm_smoke.db"
args.limit_matches = 3
args.func = cmd_ingest
```

这个对象的类型是：

```python
argparse.Namespace
```

你可以把它理解成：

```text
一个专门装命令行参数的对象。
```

## 11. args.func(args) 是真正执行

接下来：

```python
args.func(args)
```

因为现在：

```python
args.func = cmd_ingest
```

所以它等价于：

```python
cmd_ingest(args)
```

这时才真正开始执行 ingest 逻辑。

## 12. cmd_ingest 如何使用这些参数

`cmd_ingest` 定义是：

```python
def cmd_ingest(args: argparse.Namespace) -> None:
```

它接收刚才解析出来的 `args`。

里面第一行：

```python
memory = SQLiteMemory(args.db)
```

这里用到了：

```python
args.db
```

也就是你命令行里传入的：

```powershell
artifacts\tools_llm_smoke.db
```

所以程序知道数据库要放哪里。

再看：

```python
for match, events in iter_match_records(args.tar, args.index, max_matches=args.limit_matches):
```

这里用到了：

```python
args.tar
args.index
args.limit_matches
```

也就是：

```python
args.tar = "database/Game_dataset.tar.gz"
args.index = "database/Game_dataset_csv/game_database.csv"
args.limit_matches = 3
```

所以程序知道：

```text
从哪个压缩包读比赛 JSON
从哪个 CSV 读比赛索引
最多读几场比赛
```

## 13. 这条命令完整执行链

把整个过程串起来：

```text
终端输入命令
  |
  v
python -m tiny_soccer_agent.cli
  |
  v
运行 cli.py
  |
  v
调用 main()
  |
  v
argparse 解析命令行参数
  |
  v
发现子命令是 ingest
  |
  v
args.func = cmd_ingest
  |
  v
执行 args.func(args)
  |
  v
等价于执行 cmd_ingest(args)
  |
  v
cmd_ingest 调用 ingest.py 读取数据
  |
  v
cmd_ingest 调用 memory.py 写入 SQLite
```

## 14. 为什么参数名前面有 --

像这种：

```powershell
--db
--limit-matches
--tar
--index
```

叫做可选参数。

它们的特点是：

```text
有名字，可以不写；不写就用默认值。
```

比如：

```powershell
python -m tiny_soccer_agent.cli ingest
```

也可以运行，因为：

```python
--tar 有默认值
--index 有默认值
--db 有默认值
--limit-matches 默认是 None
```

而 `ingest` 这种没有 `--` 的，是位置参数 / 子命令。

它必须写在正确位置。

## 15. 为什么是 args.limit_matches，不是 args.limit-matches

命令行里写的是：

```powershell
--limit-matches
```

但 Python 变量名不能有短横线 `-`。

所以 `argparse` 会自动把短横线变成下划线：

```python
--limit-matches -> args.limit_matches
```

同理：

```text
--event-json -> args.event_json
--source-ref -> args.source_ref
```

这是 `argparse` 的默认规则。

## 16. 其他子命令也是同样逻辑

比如 `run-one`：

```python
run_parser = subparsers.add_parser("run-one", ...)
run_parser.add_argument("--db", ...)
run_parser.add_argument("--source-ref", ...)
run_parser.add_argument("--event-json", ...)
run_parser.set_defaults(func=cmd_run_one)
```

所以：

```powershell
python -m tiny_soccer_agent.cli run-one --db artifacts\tools_llm_smoke.db
```

会变成：

```python
args.command = "run-one"
args.db = "artifacts\\tools_llm_smoke.db"
args.source_ref = None
args.event_json = None
args.func = cmd_run_one
```

最后执行：

```python
cmd_run_one(args)
```

## 17. 你可以怎么观察参数解析结果

如果你想学习，可以临时在 `main()` 里：

```python
args = parser.parse_args(argv)
print(args)
args.func(args)
```

执行 ingest 时可能会看到类似：

```text
Namespace(
    command='ingest',
    tar='database/Game_dataset.tar.gz',
    index='database/Game_dataset_csv/game_database.csv',
    db='artifacts\\tools_llm_smoke.db',
    limit_matches=3,
    func=<function cmd_ingest at 0x...>
)
```

这就是 argparse 解析后的结果。

不过这个 `print(args)` 只适合学习时临时加，不建议长期保留。

## 18. 一句话总结

`argparse` 做的事情就是：

```text
把终端命令：
ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db

转换成 Python 对象：
args.command = "ingest"
args.limit_matches = 3
args.db = "artifacts\\tools_llm_smoke.db"
args.func = cmd_ingest
```

然后这一句：

```python
args.func(args)
```

把解析结果交给真正的处理函数。

所以这条命令最终会执行：

```python
cmd_ingest(args)
```

这就是 TinySoccerAgent CLI 参数解析的核心机制。
