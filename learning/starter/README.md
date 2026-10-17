# 半闭卷示例：查询体构造

目标：不复制生产实现，根据下面的小步骤完成`exercise_query_builder.py`。

## 允许查看

- 本文件；
- `tests/test_exercise05_query.py`中的需求断言；
- Python语法资料。

## 暂时不要查看

- `exercise05/query_builder.py`函数体；
- `docs/02_核心代码逐行逐词讲解.md`的完整示例段。

## 分步任务

1. 建立空的`must_clauses`和`filter_clauses`列表。
2. 有`keyword`时向`must_clauses`追加`match name`。
3. `min_price`或`max_price`不是`None`时建立价格字典；价格是`float`，需支持`100.5`。
4. 将价格字典放入`range price`并追加到filter。
5. 有`category`时追加`term category`。
6. 返回包含query、highlight、size和sort的字典。

每完成一步先打印并预测结果，不要依靠编辑器一次补全整段。Tab可以接受语法补全，但接受后必须逐行说出它生成了什么；整函数AI补全不能当作你的独立证据。真实示例商品名应使用`phone model 001`这类空格形式，不能自己改回下划线后仍声称与真实检索一致。

运行：

```powershell
Set-Location "./Day37_Bank_QA_Homework\learning\starter"
uv run python ".\exercise_query_builder.py"
```

完成后对照生产测试，但先不要覆盖生产文件。
