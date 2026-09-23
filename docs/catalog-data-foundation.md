# 商品数据底座（模拟数据）

本项目的商品目录由 SQLite 数据底座承载，启动后按如下顺序执行：

1. 创建 `catalog_sources`、`catalog_products`、`catalog_skus`、`catalog_highlights`、`catalog_markets` 与 `catalog_compliance_reviews`；
2. 首次导入 `seed_products.py` 中超过 100 个 SPU；重复启动只补充不存在的 `product_id`；
3. 仅查询 `lifecycle_status=published` 的目录记录；
4. 从数据库读出商品后批量向量化，并幂等写入 Qdrant。

数据源 `synthetic-catalog-v1` 是项目自建的虚构文本。目录覆盖 CN、US、EU、GB、JP、KR、SG、AU、NZ、TH、MY、AE、BR 等目标市场，并包含多个虚构产地与货币，用于测试跨境筛选、UI 和检索效果。审核状态 `simulated_approved` 只说明其通过了演示数据的字段完整性、市场代码和“不得伪造真实品牌/认证”校验；它不代表真实商品、供货授权、监管认证、税务、汇率、价格或市场准入。

生产接入时，应以已获授权的供应商或品牌目录替换该来源，并将许可证/授权证明、原始文件哈希、人工审核结论、适用法规版本及复审时间写入来源与审核记录。不得抓取、复制或未经授权地再发布第三方电商平台的商品详情、图片、评论和价格。
