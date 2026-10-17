# 独立复现合同（不提供答案）

在本目录自己新建`my_day37_rebuild.py`。不要打开生产实现和starter答案。

## 必须实现

### 函数1：查询体

```text
函数名：build_product_search_body
参数：keyword、min_price、max_price、category，均可选；价格上下界是float
返回：Elasticsearch查询体字典
```

合同：

- 关键词进入`bool.must`；
- 最低价、最高价进入`bool.filter`中的`range price`；
- 品类进入`bool.filter`中的精确查询；
- `min_price=0`不能丢失；
- 名称高亮使用`<em>`和`</em>`；
- size等于10；
- `_score`降序。

### 函数2：金融适配

```text
函数名：is_product_eligible
输入：客户字典、产品字典
返回：布尔值
```

合同：产品在售、客户风险足够、客户金额达到起投门槛时才返回真。

### 函数3：缓存键

```text
函数名：build_cache_key
输入：customer_id、question、data_version，以及仅限关键字传入的profile_fingerprint、catalog_fingerprint
返回：字符串
```

合同：相同客户、相同画像指纹、相同目录指纹、相同规范化问题和版本得到相同键；其中任一变化，键必须不同；键中不要保存完整敏感问题文本。为了与本项目当前源码一致，画像指纹包含姓名、风险等级和可用金额，目录指纹随产品名称、品类、风险、起投、状态或描述变化。

### 函数4：问题类型

```text
函数名：classify_query
输入：question、products
输出：PRODUCT_FACT / RECOMMENDATION / OUT_OF_SCOPE
```

合同：

- “安心存款的风险等级是什么？”是事实问答；
- “我有5000元，适合什么？”是个性化推荐；
- “今天天气怎么样？”是无关问题，结果中不得出现任何推荐产品ID或伪造来源。

### 安全运行合同

- VM三库端口只绑定`127.0.0.1`，Windows经SSH隧道访问；
- FastAPI的`/health`、`/products/search`、`/qa/ask`三个业务端点要求`X-API-Key`；
- 密钥只放当前PowerShell的`DAY37_API_KEY`，闭卷文件也不要写真实值。

## 自己设计至少8个检查

至少覆盖：

1. 全参数查询；
2. 最低价等于0；
3. 低风险客户遇到高风险产品；
4. 金额刚好等于门槛；
5. 两个客户问同一个问题；
6. 同一客户金额变化后缓存键必须变化；
7. 无关天气问题返回空推荐；
8. API无密钥和错误密钥均为401，正确密钥为200。

## 口述

完成后不看代码回答：每个函数的输入、处理、输出和一个失败边界是什么？

这里不会提供参考实现。若卡住，先只查看函数签名；仍卡住再回starter，并如实记录提示层级。
