# -*- coding: utf-8 -*-
"""seed_products

内存商品库的种子数据：跨境 SPU，覆盖旅行装备、数码配件、家居、户外等品类，
中文标题 + 关键词化描述，便于关键词召回命中"抗造 / 轻便 / 不要塑料"这类口语属性词。

分两部分：

    前 10 个 SPU（P1001~P1010）逐字段展开写，保持不变——多个单测依赖它们的 id 与排序；
    P1011 起为**召回评测语料扩充**（见 13-2 章），用紧凑表驱动写法控制篇幅。

为何要扩充：10 个 SPU 下 Recall@10 恒等于 1，指标没有区分度，评测形同虚设。
扩充的唯一目的是**造出区分度**：同品类多候选、标题相近但材质/价位不同、
含易混淆项（"旅行三件套"vs"毛巾三件装"）、价格与 ships_to 分布拉开。

注意：新增语料刻意避开与 P1001 在"旅行三件套 抗造"这条 query 上正面相撞
（竞品 P1011 不写"抗造"），以免推翻已有单测的 top-1 断言。
"""
from __future__ import annotations

from app.domain.catalog.money import Money
from app.domain.catalog.product import Product, ProductHighlight
from app.domain.catalog.sku import Sku


def _sku(sku_id: str, spec: str, major: float, currency: str, stock: int) -> Sku:
    return Sku(sku_id=sku_id, spec=spec, price=Money.from_major_units(major, currency), stock=stock)


# 紧凑表：(id, 标题, 品牌, 品类, 产地, 描述, ships_to, [(sku后缀, 规格, 价, 币种, 库存)], [(亮点名, 亮点值)])
_EXTRA_SPECS: list[tuple] = [
    # ---- 旅行装备：三件套 / 单品 / 箱包 多候选，制造排序区分度 ----
    ("P1011", "Voyager 旅行三件套 记忆棉款", "Voyager", "旅行装备", "CN",
     "记忆棉颈枕 遮光眼罩 收纳袋 三件套 轻便 长途飞行 出差 旅行必备",
     ["CN", "US", "SG"], [("S1", "深灰", 139.0, "CNY", 60)], [("材质", "记忆棉 + 涤纶外套")]),
    ("P1012", "NestRest 充气颈枕 按压式", "NestRest", "旅行装备", "CN",
     "充气颈枕 按压充气 收纳体积小 飞机 高铁 侧睡支撑 轻便 180g",
     ["CN", "US"], [("S1", "海盐蓝", 69.0, "CNY", 120)], [("体积", "收纳后仅掌心大小")]),
    ("P1013", "BlackoutPro 3D 真丝遮光眼罩", "BlackoutPro", "旅行装备", "CN",
     "真丝 遮光眼罩 3D立体 不压眼 天然材质 无塑料 睡眠 飞机 高铁",
     ["CN", "US", "EU"], [("S1", "豆沙色", 89.0, "CNY", 90)], [("材质", "6A 桑蚕丝，无塑料")]),
    ("P1014", "PackMate 压缩收纳袋 6件套", "PackMate", "旅行装备", "CN",
     "压缩收纳袋 六件套 分装 行李整理 防潮 可重复使用 轻便",
     ["CN", "US", "SG"], [("S1", "灰蓝混色", 99.0, "CNY", 140)], [("套装", "大中小共 6 只")]),
    ("P1015", "TrailOx 24寸托运行李箱 铝框款", "TrailOx", "旅行装备", "DE",
     "铝镁合金框 托运尺寸 24寸 结实抗摔 万向静音轮 TSA锁 长途旅行",
     ["CN", "US", "EU"], [("S1", "银色 / 24寸", 1199.0, "CNY", 12)], [("箱体", "铝框，抗摔")]),
    ("P1016", "GlideCase 20寸登机箱 PC硬壳", "GlideCase", "旅行装备", "CN",
     "PC聚碳酸酯硬壳 塑料箱体 登机尺寸 20寸 轻量 万向轮 平价",
     ["CN"], [("S1", "碳黑 / 20寸", 399.0, "CNY", 45)], [("箱体", "PC 塑料硬壳")]),
    ("P1017", "Wanderlite 轻量旅行腰包", "Wanderlite", "旅行装备", "KR",
     "腰包 胸包 轻量 120g 防泼水 贴身 杂物袋 日常通勤 旅行",
     ["CN", "JP", "SG"], [("S1", "雾霞蓝", 79.0, "CNY", 100)], [("重量", "仅 120g")]),
    ("P1018", "DryPack 30L 防水卷口背包", "DryPack", "旅行装备", "CN",
     "卷口防水 30L TPU涂层 户外 涉水 结实抗造 骑行 满水不漏",
     ["CN", "US", "EU"], [("S1", "墨绿", 219.0, "CNY", 55)], [("防水", "IPX6 卷口密封")]),
    ("P1019", "LinenFold 亚麻旅行衣物收纳套", "LinenFold", "旅行装备", "CN",
     "亚麻 天然材质 无塑料 透气 衣物分装 折叠 环保 小众设计",
     ["CN", "JP"], [("S1", "本色三只装", 129.0, "CNY", 70)], [("材质", "100% 亚麻，无塑料")]),
    ("P1020", "SoleFresh 折叠旅行拖鞋", "SoleFresh", "旅行装备", "CN",
     "折叠拖鞋 便携袋 酒店 飞机 轻便 160g 可水洗",
     ["CN", "US"], [("S1", "灰色 M", 49.0, "CNY", 180)], [("重量", "双足仅 160g")]),
    ("P1021", "AquaLite 折叠硅胶水壶 600ml", "AquaLite", "旅行装备", "CN",
     "食品级硅胶 折叠水壶 600ml 轻便 徒步 飞机 可收纳",
     ["CN", "US", "EU"], [("S1", "霉绿", 59.0, "CNY", 160)], [("收纳", "折叠后厚 3cm")]),
    ("P1051", "ZipPouch RFID 证件收纳包", "ZipPouch", "旅行装备", "CN",
     "RFID 防盗刷 证件收纳 护照夹 登机牌 多卡位 轻薄",
     ["CN", "US", "EU"], [("S1", "碳黑", 69.0, "CNY", 130)], [("安全", "RFID 屏蔽层")]),
    ("P1052", "TravelScale 便携行李称", "TravelScale", "旅行装备", "CN",
     "行李称 50kg 电子称 便携 避免超重 背带式",
     ["CN", "US"], [("S1", "黑色", 45.0, "CNY", 200)], [("量程", "最大 50kg")]),
    ("P1053", "QuietEar 硅胶隔音耳塞", "QuietEar", "旅行装备", "CN",
     "硅胶耳塞 隔音降噪 32dB 睡眠 飞机 可水洗 带收纳盒",
     ["CN", "US", "EU"], [("S1", "透明三对装", 39.0, "CNY", 220)], [("降噪", "SNR 32dB")]),
    ("P1058", "SteamRest 蒸汽热敷眼罩", "SteamRest", "旅行装备", "JP",
     "蒸汽眼罩 发热 一次性 缓解眼部疲劳 睡眠 日本制",
     ["CN", "JP"], [("S1", "无香 14片", 79.0, "CNY", 110)], [("发热", "40℃ 持续 20 分钟")]),
    ("P1059", "CompressCube 压缩收纳方块", "CompressCube", "旅行装备", "CN",
     "压缩方块 双拉链 行李分装 省空间 高弹尼龙 轻便",
     ["CN", "US"], [("S1", "黑色两只装", 89.0, "CNY", 95)], [("压缩", "体积减少 40%")]),
    ("P1060", "UniversalStrap 行李捆扎带 TSA锁", "UniversalStrap", "旅行装备", "CN",
     "捆扎带 TSA 密码锁 防护 易辨识 加固行李箱",
     ["CN", "US", "EU"], [("S1", "橙色", 55.0, "CNY", 150)], [("锁具", "TSA 海关认可")]),
    ("P1049", "BudgetPack 20L 简易背包", "BudgetPack", "旅行装备", "CN",
     "20L 入门背包 轻便 平价 涤纶 日常 通勤",
     ["CN"], [("S1", "黑色", 39.0, "CNY", 300)], [("价位", "入门平价款")]),
    ("P1050", "LuxeTrunk 铝镁合金旅行箱 全铝款", "LuxeTrunk", "旅行装备", "DE",
     "全铝镁合金箱体 高级 结实抗摔 终身保修 商务 高价位",
     ["CN", "EU"], [("S1", "原色 / 26寸", 2999.0, "CNY", 5)], [("箱体", "全铝镁合金")]),

    # ---- 数码配件：同品牌高/低配 + 降噪竞品，测同类排序 ----
    ("P1022", "AeroHush Lite 半入耳蓝牙耳机", "AeroHush", "数码配件", "CN",
     "半入耳 蓝牙 5.3 轻便 长续航 30小时 通话降噪 入门价位",
     ["CN", "US"], [("S1", "白色", 299.0, "CNY", 80)], [("续航", "含仓 30 小时")]),
    ("P1023", "SilentBuds 主动降噪耳塞式耳机", "SilentBuds", "数码配件", "US",
     "主动降噪 ANC 深降噪 42dB 耳塞式 通勤 飞机 降噪耳机",
     ["CN", "US", "EU"], [("S1", "子夜蓝", 189.0, "USD", 30)], [("降噪", "深度 42dB")]),
    ("P1024", "VoltTrek 30W 迷你充电器", "VoltTrek", "数码配件", "CN",
     "30W 氮化镓 迷你 单口 折叠插脚 轻便 手机快充",
     ["CN", "US", "EU", "JP"], [("S1", "白色", 89.0, "CNY", 150)], [("体积", "仅鸡蛋大小")]),
    ("P1025", "VoltTrek 100W 四口氮化镓充电器", "VoltTrek", "数码配件", "CN",
     "100W 氮化镓 四口 同时充笔记本 全球插脚 出差 旅行",
     ["CN", "US", "EU", "JP"], [("S1", "深空灰", 299.0, "CNY", 60)], [("功率", "100W 四口分配")]),
    ("P1026", "PowerCore 10000mAh 移动电源", "PowerCore", "数码配件", "CN",
     "10000mAh 移动电源 锂电池 可登机 轻薄 自带线 锂电池空运限制",
     ["CN"], [("S1", "黑色", 129.0, "CNY", 90)], [("空运", "含锂电池，仅国内配送")]),
    ("P1027", "CableRoll 三合一磁吸数据线", "CableRoll", "数码配件", "CN",
     "三合一 数据线 磁吸收纳 Type-C Lightning 微口 快充 旅行",
     ["CN", "US", "EU"], [("S1", "银灰", 59.0, "CNY", 200)], [("兼容", "三种接口一线搞定")]),
    ("P1028", "GlobeAdapt 全球通用转换插头", "GlobeAdapt", "数码配件", "CN",
     "全球通用 转换插头 150国 内置USB 出国 旅行 安全门",
     ["CN", "US", "EU", "JP"], [("S1", "白色", 99.0, "CNY", 130)], [("兼容", "覆盖 150+ 国家")]),
    ("P1029", "ClearShot 铝合金手机三脚架", "ClearShot", "数码配件", "CN",
     "铝合金 三脚架 便携 蓝牙快门 旅拍 Vlog 结实",
     ["CN", "US"], [("S1", "黑色", 149.0, "CNY", 70)], [("材质", "铝合金管体")]),
    ("P1030", "SDVault 高速存储卡读卡器", "SDVault", "数码配件", "CN",
     "读卡器 SD TF 高速 USB3.2 带卡仓 摄影 便携",
     ["CN", "US", "EU"], [("S1", "银色", 79.0, "CNY", 110)], [("速率", "USB 3.2 Gen1")]),
    ("P1054", "BreezeNeck 便携挂颈风扇", "BreezeNeck", "数码配件", "CN",
     "挂颈风扇 无叶 三档风速 续航8小时 夏季 户外 便携",
     ["CN", "SG"], [("S1", "白色", 119.0, "CNY", 85)], [("续航", "最高 8 小时")]),

    # ---- 家居生活：“中性气质咖啡杯”这类气质类 query 的多候选 ----
    ("P1031", "TerraCotta 手工粗陶马克杯", "TerraCotta", "家居生活", "JP",
     "手工粗陶 马克杯 窑烧 天然材质 无塑料 侘寂 中性 小众 咖啡杯",
     ["CN", "JP"], [("S1", "灶变色", 128.0, "CNY", 40)], [("材质", "粗陶手作，无塑料")]),
    ("P1032", "Nordic 中性色陶瓷咖啡杯", "Nordic", "家居生活", "CN",
     "陶瓷 咖啡杯 中性色 北欧极简 磨砂釉 天然 无塑料 办公 居家",
     ["CN", "US", "EU"], [("S1", "雾霞灰", 89.0, "CNY", 120)], [("风格", "北欧中性色")]),
    ("P1033", "BambooLine 竹制餐具旅行套装", "BambooLine", "家居生活", "CN",
     "竹制餐具 筷勺叉 旅行套装 天然材质 无塑料 环保 便携袋",
     ["CN", "US", "EU"], [("S1", "原色", 69.0, "CNY", 160)], [("材质", "天然楱竹，无塑料")]),
    ("P1034", "LinenHome 亚麻抱枕套", "LinenHome", "家居生活", "CN",
     "亚麻 抱枕套 天然材质 透气 中性色 极简 居家",
     ["CN", "JP"], [("S1", "米白 45x45", 79.0, "CNY", 90)], [("材质", "水洗亚麻")]),
    ("P1035", "AromaStone 陶石香薰扩香器", "AromaStone", "家居生活", "CN",
     "陶石 扩香 无火 香薰 天然材质 小众设计 卧室",
     ["CN"], [("S1", "白色", 99.0, "CNY", 60)], [("方式", "无火被动扩香")]),
    ("P1036", "GlassPour 双层玻璃手冲壶", "GlassPour", "家居生活", "CN",
     "双层玻璃 手冲壶 隔热 咖啡 600ml 易清洗",
     ["CN", "US"], [("S1", "透明", 159.0, "CNY", 45)], [("容量", "600ml 双层隔热")]),
    ("P1037", "CorkMat 软木隔热垫", "CorkMat", "家居生活", "PT",
     "软木 隔热垫 天然材质 无塑料 餐桌 四只装",
     ["CN", "EU"], [("S1", "原色四只", 59.0, "CNY", 140)], [("材质", "葡萄牙软木")]),
    ("P1055", "SteamFree 便携挂烫机", "SteamFree", "家居生活", "CN",
     "手持挂烫机 便携 出差 蒸汽熨斗 快热 30秒 旅行",
     ["CN"], [("S1", "白色", 199.0, "CNY", 50)], [("预热", "30 秒出蒸汽")]),
    ("P1056", "ShoeBag 防水鞋袋两只装", "ShoeBag", "家居生活", "CN",
     "鞋袋 防水 加厚 行李分装 可重复使用 旅行",
     ["CN", "US"], [("S1", "灰色两只", 35.0, "CNY", 240)], [("容量", "单只可装 45 码")]),
    ("P1057", "MiniUmbrella 五折超轻晴雨伞", "MiniUmbrella", "家居生活", "CN",
     "五折伞 超轻 180g 防晒 UPF50+ 晴雨兼用 口袋伞",
     ["CN", "US", "JP"], [("S1", "黑胶", 89.0, "CNY", 130)], [("重量", "仅 180g")]),

    # ---- 户外运动：登山杖/露营灯/睡袋 各成梯度 ----
    ("P1038", "LumenGo Mini 钥匙扣手电", "LumenGo", "户外运动", "CN",
     "钥匙扣手电 便携 Type-C充电 强光 应急 轻 28g",
     ["CN", "US", "EU"], [("S1", "银色", 45.0, "CNY", 200)], [("重量", "仅 28g")]),
    ("P1039", "SolarLamp 太阳能营地灯", "SolarLamp", "户外运动", "CN",
     "太阳能 营地灯 露营灯 可充电 防水IPX5 可折叠 应急照明",
     ["CN", "US", "EU"], [("S1", "黑色", 129.0, "CNY", 75)], [("供电", "太阳能 + USB 双模")]),
    ("P1040", "CascadePro 铝合金折叠登山杖一对", "CascadePro", "户外运动", "CN",
     "铝合金 折叠 登山杖 快锁 减震 徒步 入门价位 320g单支",
     ["CN", "US"], [("S1", "黑色一对", 199.0, "CNY", 60)], [("材质", "7075 铝合金")]),
    ("P1047", "TrekPole 碳纤维登山杖一对", "TrekPole", "户外运动", "CN",
     "碳纤维 登山杖 超轻 190g单支 三节 徒步 登山 专业",
     ["CN", "US", "EU"], [("S1", "碳纤纹一对", 459.0, "CNY", 30)], [("重量", "单支仅 190g")]),
    ("P1041", "TrailSeat 超轻折叠露营凳", "TrailSeat", "户外运动", "CN",
     "折叠凳 超轻 680g 铝合金 露营 徒步 承重120kg 结实抗造",
     ["CN", "US"], [("S1", "墨绿", 169.0, "CNY", 65)], [("承重", "最大 120kg")]),
    ("P1042", "ThermoRest 自动充气防潮垫", "ThermoRest", "户外运动", "CN",
     "自动充气 防潮垫 露营 帐篷 保温 R值3.2 可拼接",
     ["CN", "US", "EU"], [("S1", "橙色单人", 279.0, "CNY", 40)], [("保温", "R 值 3.2")]),
    ("P1043", "SummitBag -5℃ 羽绒睡袋", "SummitBag", "户外运动", "CN",
     "羽绒睡袋 -5℃ 鸭绒 露营 保温 可压缩 1.2kg 信封式",
     ["CN", "US", "EU"], [("S1", "深蓝", 699.0, "CNY", 25)], [("适用", "舒适温 -5℃")]),
    ("P1044", "GripLine 静力登山绳 10mm", "GripLine", "户外运动", "CN",
     "静力绳 10mm 登山绳 承重 结实抗造 攀岩 户外安全",
     ["CN", "EU"], [("S1", "30米", 389.0, "CNY", 20)], [("强度", "断裂拉力 22kN")]),
    ("P1045", "HydroFlow 316不锈钢保温水壶", "HydroFlow", "户外运动", "CN",
     "316不锈钢 保温水壶 750ml 保温12小时 运动 户外 无塑料内胆",
     ["CN", "US", "EU"], [("S1", "碳黑 750ml", 189.0, "CNY", 80)], [("内胆", "316 不锈钢，无塑料")]),
    ("P1046", "WindShell 超轻防风外套", "WindShell", "户外运动", "CN",
     "防风外套 超轻 180g 可收纳 拨水 徒步 露营 男女同款",
     ["CN", "US", "EU"], [("S1", "炭黑 L", 259.0, "CNY", 55)], [("重量", "仅 180g 可压缩")]),
    ("P1048", "CampCook 钛合金炊具套装", "CampCook", "户外运动", "CN",
     "钛合金 炊具 露营锅 超轻 240g 可嵌套 无涂层 徒步",
     ["CN", "US", "EU"], [("S1", "钛原色两件", 429.0, "CNY", 28)], [("材质", "纯钛，无涂层")]),
]

# 数据底座演示语料：全部为项目自建的虚构商品及文案，不含第三方品牌、图片、评论或
# 平台抓取内容。覆盖 CN / US / EU 三个目标市场，供结构化入库与检索评测使用。
_COMPLIANT_DEMO_SPECS: list[tuple] = [
    ("P1061", "AtlasFold 可折叠旅行背包 28L", "AtlasFold", "旅行装备", "CN", "28L 折叠背包 城市旅行 轻量 防泼水 可登机", ["CN", "US", "EU"], [("S1", "深灰", 179.0, "CNY", 90)], [("容量", "28L")]),
    ("P1062", "CloudRest U型旅行颈枕", "CloudRest", "旅行装备", "CN", "U型颈枕 可拆洗 长途飞行 高铁 午休 支撑", ["CN", "US", "EU"], [("S1", "雾蓝", 109.0, "CNY", 110)], [("填充", "高弹纤维")]),
    ("P1063", "RouteMark 行李牌两件套", "RouteMark", "旅行装备", "CN", "行李牌 地址遮挡 卡扣牢固 旅行识别 两件套", ["CN", "US", "EU"], [("S1", "橙色", 39.0, "CNY", 220)], [("套装", "2 件")]),
    ("P1064", "MetroCase 电子收纳包", "MetroCase", "旅行装备", "CN", "电子收纳包 数据线 充电器 分区 防泼水 出差", ["CN", "US", "EU"], [("S1", "石墨灰", 79.0, "CNY", 150)], [("分区", "6 个弹力位")]),
    ("P1065", "Daylight 遮阳帽 可调节", "Daylight", "旅行装备", "CN", "可调节遮阳帽 透气 旅行 徒步 城市通勤", ["CN", "US", "EU"], [("S1", "卡其", 69.0, "CNY", 130)], [("帽围", "54-60cm")]),
    ("P1066", "ClearWave 有线耳机", "ClearWave", "数码配件", "CN", "有线耳机 Type-C 接口 通勤 通话 麦克风 轻便", ["CN", "US", "EU"], [("S1", "白色", 89.0, "CNY", 160)], [("接口", "Type-C")]),
    ("P1067", "OrbitStand 铝合金平板支架", "OrbitStand", "数码配件", "CN", "平板支架 铝合金 折叠 角度可调 桌面办公", ["CN", "US", "EU"], [("S1", "银色", 119.0, "CNY", 100)], [("兼容", "7-13 英寸")]),
    ("P1068", "KeyGuard 键盘防尘收纳套", "KeyGuard", "数码配件", "CN", "键盘收纳套 防尘 便携 软内衬 出差 办公", ["CN", "US", "EU"], [("S1", "黑色", 99.0, "CNY", 100)], [("适用", "75% 配列")]),
    ("P1069", "PixelClean 屏幕清洁套装", "PixelClean", "数码配件", "CN", "屏幕清洁布 清洁喷雾 无酒精 电脑 手机 镜头", ["CN", "US", "EU"], [("S1", "基础套", 49.0, "CNY", 180)], [("内容", "喷雾+两块布")]),
    ("P1070", "DeskFlow 桌面理线夹 8只装", "DeskFlow", "数码配件", "CN", "桌面理线夹 数据线 固线 8只装 办公 整理", ["CN", "US", "EU"], [("S1", "黑色", 29.0, "CNY", 300)], [("数量", "8 只")]),
    ("P1071", "MoriCup 双层陶瓷随行杯", "MoriCup", "家居生活", "CN", "双层陶瓷随行杯 咖啡 茶饮 硅胶杯盖 简约", ["CN", "US", "EU"], [("S1", "米白 350ml", 149.0, "CNY", 70)], [("容量", "350ml")]),
    ("P1072", "SoftLoom 棉麻桌旗", "SoftLoom", "家居生活", "CN", "棉麻桌旗 餐桌布 中性色 易打理 家居", ["CN", "US", "EU"], [("S1", "亚麻色 180cm", 129.0, "CNY", 80)], [("材质", "棉麻混纺")]),
    ("P1073", "WarmNest 绒面靠垫", "WarmNest", "家居生活", "CN", "绒面靠垫 客厅 卧室 抱枕 中性色 可拆洗", ["CN", "US", "EU"], [("S1", "暖灰 45cm", 99.0, "CNY", 120)], [("填充", "聚酯纤维")]),
    ("P1074", "PantryJar 玻璃储物罐三件套", "PantryJar", "家居生活", "CN", "玻璃储物罐 密封罐 厨房 收纳 三件套", ["CN", "US", "EU"], [("S1", "透明", 139.0, "CNY", 90)], [("套装", "500/800/1200ml")]),
    ("P1075", "QuietLight 阅读台灯", "QuietLight", "家居生活", "CN", "阅读台灯 可调角度 柔和照明 学习 办公 桌面", ["CN", "US", "EU"], [("S1", "白色", 199.0, "CNY", 65)], [("模式", "3 档亮度")]),
    ("P1076", "TrailMug 不锈钢随行杯", "TrailMug", "户外运动", "CN", "不锈钢随行杯 450ml 户外 通勤 防漏 便携", ["CN", "US", "EU"], [("S1", "墨绿", 129.0, "CNY", 100)], [("容量", "450ml")]),
    ("P1077", "CampTowel 超细纤维速干巾", "CampTowel", "户外运动", "CN", "速干巾 露营 健身 游泳 可收纳 轻量", ["CN", "US", "EU"], [("S1", "蓝色 L", 59.0, "CNY", 190)], [("尺寸", "80x130cm")]),
    ("P1078", "PeakCap 可调节徒步帽", "PeakCap", "户外运动", "CN", "徒步帽 透气 可调节 帽檐 防晒 户外", ["CN", "US", "EU"], [("S1", "岩灰", 79.0, "CNY", 140)], [("帽围", "54-60cm")]),
    ("P1079", "FieldNote 防泼水笔记本", "FieldNote", "户外运动", "CN", "防泼水笔记本 户外记录 旅行日志 便携", ["CN", "US", "EU"], [("S1", "棕色", 45.0, "CNY", 200)], [("页数", "96 页")]),
    ("P1080", "PaceBottle 运动水壶 700ml", "PaceBottle", "户外运动", "CN", "运动水壶 700ml 徒步 骑行 防漏 宽口 易清洗", ["CN", "US", "EU"], [("S1", "海蓝", 69.0, "CNY", 150)], [("容量", "700ml")]),
    ("P1081", "HarborMat 可折叠野餐垫", "HarborMat", "户外运动", "CN", "野餐垫 可折叠 防潮 公园 露营 便携", ["CN", "US", "EU"], [("S1", "格纹", 119.0, "CNY", 75)], [("尺寸", "150x180cm")]),
    ("P1082", "NorthStar 指南针钥匙扣", "NorthStar", "户外运动", "CN", "指南针钥匙扣 旅行 徒步 方向识别 轻便", ["CN", "US", "EU"], [("S1", "银灰", 35.0, "CNY", 210)], [("重量", "25g")]),
    ("P1083", "LumaClip 反光挂扣两只装", "LumaClip", "户外运动", "CN", "反光挂扣 背包 夜行 可见性 两只装", ["CN", "US", "EU"], [("S1", "荧光黄", 29.0, "CNY", 250)], [("套装", "2 只")]),
    ("P1084", "BreezeWrap 多用途头巾", "BreezeWrap", "户外运动", "CN", "多用途头巾 徒步 骑行 防风 吸汗 轻便", ["CN", "US", "EU"], [("S1", "深蓝", 39.0, "CNY", 230)], [("材质", "涤纶弹力布")]),
]


# 全球精选演示目录：所有品牌、商品文本、价格和库存均为项目自建虚构数据。
# 覆盖更多产地、结算币种与目的市场，用于检索、筛选和 Docker 演示，不能用于真实采购或合规判断。
_GLOBAL_DEMO_SPECS: list[tuple] = [
    ("P1101", "CedarWay 再生羊毛旅行毯", "CedarWay", "旅行装备", "CA", "再生羊毛旅行毯 飞机 车载 披肩 加拿大设计 可收纳", ["CA", "US", "GB", "EU"], [("S1", "枫叶红 / 130x180cm", 68.0, "CAD", 42)], [("材质", "70% 再生羊毛"), ("适用", "航班与公路旅行")]),
    ("P1102", "HarborTone 防水蓝牙音箱", "HarborTone", "数码配件", "US", "IP67 防水 蓝牙音箱 露营 海边 12小时续航", ["US", "CA", "MX", "AU"], [("S1", "海军蓝", 79.0, "USD", 64)], [("防护", "IP67"), ("续航", "最长 12 小时")]),
    ("P1103", "Moss & Mile 皮革护照夹", "Moss & Mile", "旅行装备", "GB", "植鞣皮护照夹 多卡位 登机牌收纳 英伦旅行", ["GB", "EU", "US", "SG"], [("S1", "橄榄棕", 42.0, "GBP", 38)], [("材质", "植鞣皮革"), ("卡位", "5 个")]),
    ("P1104", "Nordlicht 保温咖啡壶 600ml", "Nordlicht", "家居生活", "SE", "双层不锈钢咖啡壶 北欧极简 通勤 野餐 保温", ["SE", "EU", "GB", "JP"], [("S1", "雾银 600ml", 46.0, "EUR", 50)], [("保温", "热饮 8 小时"), ("内胆", "304 不锈钢")]),
    ("P1105", "AlpenForm 折叠雨伞 防风款", "AlpenForm", "旅行装备", "DE", "折叠伞 防风骨架 快干伞布 城市旅行 德国设计", ["DE", "EU", "GB", "US"], [("S1", "石板灰", 39.0, "EUR", 72)], [("抗风", "8 骨结构"), ("收纳", "28cm")]),
    ("P1106", "Lumière 旅行香氛蜡烛套", "Lumière", "家居生活", "FR", "大豆蜡旅行蜡烛 法式柑橘木香 礼赠 家居氛围", ["FR", "EU", "GB", "SG"], [("S1", "两只旅行装", 34.0, "EUR", 55)], [("香调", "柑橘与雪松"), ("燃烧", "约 18 小时")]),
    ("P1107", "TerraSole 轻量步行凉鞋", "TerraSole", "户外运动", "IT", "旅行凉鞋 软木鞋床 防滑 鞋带可调 城市步行", ["IT", "EU", "US", "AU"], [("S1", "沙岩色 39", 72.0, "EUR", 33), ("S2", "沙岩色 42", 72.0, "EUR", 28)], [("鞋床", "软木复合"), ("鞋底", "防滑橡胶")]),
    ("P1108", "SakuraNote 和纸旅行手账", "SakuraNote", "家居生活", "JP", "和纸手账 旅行记录 钢笔友好 轻薄 A6 日本制", ["JP", "SG", "AU", "US"], [("S1", "樱花白 A6", 1800.0, "JPY", 90)], [("纸张", "80g 和纸"), ("页数", "160 页")]),
    ("P1109", "SeoulFrame 磁吸手机支架", "SeoulFrame", "数码配件", "KR", "磁吸手机支架 桌面 视频通话 折叠 轻巧", ["KR", "JP", "SG", "US"], [("S1", "钛灰", 28000.0, "KRW", 85)], [("角度", "多角度调节"), ("重量", "96g")]),
    ("P1110", "StraitsPack 防泼水通勤托特包", "StraitsPack", "旅行装备", "SG", "通勤托特包 防泼水 15寸电脑隔层 新加坡热带通勤", ["SG", "MY", "TH", "AU"], [("S1", "雨林绿", 79.0, "SGD", 46)], [("隔层", "15 英寸电脑位"), ("面料", "防泼水尼龙")]),
    ("P1111", "Coastline 速干沙滩巾", "Coastline", "户外运动", "AU", "速干沙滩巾 轻量 吸水 海边 露营 澳大利亚设计", ["AU", "NZ", "SG", "US"], [("S1", "珊瑚橙 / 80x150cm", 45.0, "AUD", 78)], [("面料", "再生聚酯纤维"), ("收纳", "附网袋")]),
    ("P1112", "KoruTrail 美利奴徒步袜两双", "KoruTrail", "户外运动", "NZ", "美利奴羊毛徒步袜 透气 快干 旅行 两双装", ["NZ", "AU", "US", "EU"], [("S1", "深灰 M", 39.0, "NZD", 66)], [("材质", "美利奴羊毛混纺"), ("套装", "2 双")]),
    ("P1113", "MekongCraft 藤编桌面收纳篮", "MekongCraft", "家居生活", "TH", "藤编收纳篮 桌面整理 手工质感 东南亚家居", ["TH", "SG", "MY", "JP"], [("S1", "自然色 小号", 590.0, "THB", 44)], [("材质", "天然藤编"), ("尺寸", "22x16cm")]),
    ("P1114", "LotusLink 旅行洗漱包", "LotusLink", "旅行装备", "VN", "旅行洗漱包 干湿分离 挂钩设计 轻便 越南制造", ["VN", "SG", "AU", "US"], [("S1", "海盐蓝", 19.0, "USD", 120)], [("分区", "干湿双层"), ("挂钩", "可折叠")]),
    ("P1115", "MonsoonBean 不锈钢滤杯", "MonsoonBean", "家居生活", "IN", "不锈钢咖啡滤杯 手冲旅行咖啡 可重复使用 印度设计", ["IN", "SG", "AE", "GB"], [("S1", "银色", 1299.0, "INR", 58)], [("材质", "304 不锈钢"), ("滤网", "双层微孔")]),
    ("P1116", "RioFlex 防水手机袋", "RioFlex", "户外运动", "BR", "防水手机袋 海滩 漂流 触屏挂绳 巴西户外", ["BR", "US", "MX", "PT"], [("S1", "柠檬黄", 49.0, "BRL", 110)], [("防护", "IPX8"), ("兼容", "6.8 英寸以内")]),
    ("P1117", "DesertLine 旅行茶杯 450ml", "DesertLine", "家居生活", "AE", "不锈钢旅行茶杯 450ml 防漏 沙漠色系 通勤", ["AE", "SA", "SG", "GB"], [("S1", "沙丘金", 79.0, "AED", 36)], [("容量", "450ml"), ("密封", "旋盖防漏")]),
    ("P1118", "IberiaFold 皮质行李标签", "IberiaFold", "旅行装备", "ES", "皮质行李标签 可替换信息卡 旅行识别 西班牙设计", ["ES", "EU", "GB", "US"], [("S1", "海军蓝", 24.0, "EUR", 95)], [("材质", "再生皮革"), ("结构", "隐私翻盖")]),
    ("P1119", "CanalGlass 冷萃咖啡瓶", "CanalGlass", "家居生活", "NL", "耐热玻璃冷萃瓶 旅行办公 冷泡茶 荷兰设计", ["NL", "EU", "GB", "SG"], [("S1", "琥珀色 500ml", 29.0, "EUR", 60)], [("容量", "500ml"), ("滤芯", "细密不锈钢")]),
    ("P1120", "BalticLoop 反光自行车绑带", "BalticLoop", "户外运动", "PL", "反光绑带 骑行旅行 裤脚固定 夜间可见 两条装", ["PL", "EU", "GB", "US"], [("S1", "荧光黄", 12.0, "EUR", 145)], [("可见性", "反光织带"), ("套装", "2 条")]),
    ("P1121", "MapleCircuit 旅行转换插座", "MapleCircuit", "数码配件", "CA", "旅行转换插座 USB-C 双口 过载保护 北美差旅", ["CA", "US", "GB", "EU"], [("S1", "冰川白", 52.0, "CAD", 40)], [("接口", "2x USB-C + USB-A"), ("保护", "过载保护")]),
    ("P1122", "KyotoMist 折叠喷雾瓶三只", "KyotoMist", "旅行装备", "JP", "折叠喷雾瓶 分装护理液 旅行随身 三只装", ["JP", "KR", "SG", "AU"], [("S1", "透明 30ml", 1200.0, "JPY", 140)], [("套装", "3 只"), ("结构", "防漏旋盖")]),
    ("P1123", "FjordSignal 迷你营灯", "FjordSignal", "户外运动", "NO", "迷你营灯 暖光 挂扣 露营 应急 北欧户外", ["NO", "EU", "GB", "CA"], [("S1", "冰川蓝", 35.0, "EUR", 57)], [("亮度", "三档暖光"), ("续航", "约 20 小时")]),
    ("P1124", "AndesClip 多用途登山扣", "AndesClip", "户外运动", "CL", "铝合金登山扣 旅行挂载 水瓶钥匙 户外 两只装", ["CL", "BR", "US", "AU"], [("S1", "赤陶红", 14.0, "USD", 132)], [("材质", "铝合金"), ("套装", "2 只")]),
]


# 420 SPU 扩容语料：以「商品族 × 属性变体」生成 312 个独立 SPU，保持种子文件可审阅。
# 每个条目均是 Globex 自建的虚构演示数据；不会使用真实品牌、认证或市场准入承诺。
# 元组：(品牌前缀, 中文商品名, 关键词化描述, 材质, 核心特征, 使用场景)。
_EXPANDED_FAMILIES: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "旅行装备": [
        ("CarryMori", "可扩展登机背包", "登机背包 扩容 分区 轻便 差旅 收纳", "再生尼龙", "扩容拉链", "短途飞行"),
        ("RailNest", "火车旅行收纳包", "旅行收纳 分隔 干湿分离 轻量 高铁", "涤纶防泼水布", "双层分区", "高铁出行"),
        ("Wayfarer", "折叠衣物整理袋", "衣物整理 折叠 收纳 行李箱 省空间", "棉麻混纺", "可视网格", "行李分装"),
        ("PortSide", "旅行洗漱挂包", "洗漱包 挂钩 防泼水 分装 出差", "再生聚酯纤维", "展开挂放", "酒店入住"),
        ("CloudWalk", "轻量城市日用包", "城市背包 轻便 防泼水 通勤 旅行", "再生尼龙", "透气背板", "城市步行"),
        ("TransitForm", "行李箱内衬收纳盒", "行李箱 内衬 收纳 分区 衣物整理", "牛津布", "可压缩侧壁", "长途旅行"),
        ("CabinLeaf", "飞机脚踏吊床", "飞机脚踏 吊床 腿部放松 可折叠 长途飞行", "高密度织带", "长度可调", "长途飞行"),
        ("RainRoute", "旅行防雨罩", "背包防雨罩 防水 收纳 户外 旅行", "防水涂层布", "反光边条", "雨天转乘"),
        ("PassportLine", "证件分层收纳夹", "护照夹 证件 收纳 RFID 轻薄 出境", "植鞣皮革", "隐私翻页", "过关登机"),
    ],
    "户外运动": [
        ("CampRay", "营地暖光照明灯", "营地 暖光 照明 挂扣 续航 夜间", "铝合金外壳", "三档色温", "帐篷夜读"),
        ("RidgeStep", "越野徒步护膝", "徒步 护膝 支撑 透气 轻量 山路", "弹力针织布", "硅胶防滑条", "碎石徒步"),
        ("PineCook", "折叠营地餐桌", "露营 餐桌 折叠 铝合金 便携", "铝合金", "卷收桌面", "营地用餐"),
        ("TrailPulse", "夜跑反光臂包", "夜跑 臂包 反光 手机 收纳 轻便", "弹力莱卡", "夜间反光", "城市夜跑"),
        ("SummitSip", "保温运动水壶", "保温 水壶 徒步 防漏 宽口 易清洗", "304 不锈钢", "单手开盖", "山间徒步"),
        ("RiverKnot", "防水漂流收纳袋", "防水 收纳袋 漂流 涉水 卷口", "TPU 复合布", "卷口密封", "溪流漂流"),
        ("StonePeak", "折叠坐垫", "折叠 坐垫 防潮 徒步 轻便 露营", "闭孔泡棉", "防潮隔冷", "观景休息"),
        ("ForestCue", "露营路线标记扣", "路线 标记 反光 挂扣 徒步 营地", "阳极氧化铝", "高可见配色", "营地寻路"),
    ],
    "家居生活": [
        ("HearthMori", "陶瓷手冲滤杯", "陶瓷 滤杯 手冲 咖啡 无塑料 居家", "高温陶瓷", "三孔萃取", "晨间咖啡"),
        ("LinenTable", "棉麻餐垫", "棉麻 餐垫 天然材质 中性色 易清洗", "棉麻混纺", "双面织纹", "餐桌布置"),
        ("QuietVessel", "玻璃密封茶罐", "玻璃 茶罐 密封 收纳 茶叶 厨房", "高硼硅玻璃", "竹木盖", "茶叶保存"),
        ("CedarHome", "木质桌面收纳架", "木质 收纳架 桌面 整理 天然材质", "榉木", "模块拼接", "居家办公"),
        ("MoriAroma", "无火扩香石", "无火 扩香 石膏 香氛 卧室 小众", "矿物石膏", "缓释香气", "卧室氛围"),
        ("WarmFold", "可洗针织抱枕套", "针织 抱枕套 可拆洗 中性色 家居", "棉纱", "隐藏拉链", "客厅休闲"),
        ("PantryWeave", "藤编食品收纳篮", "藤编 收纳篮 厨房 天然材质 透气", "天然藤编", "可叠放", "厨房整理"),
    ],
    "数码配件": [
        ("VoltArc", "旅行氮化镓充电器", "氮化镓 充电器 快充 宽压 旅行 轻便", "阻燃 PC 外壳", "多口功率分配", "差旅充电"),
        ("EchoNest", "折叠降噪耳罩", "降噪 耳罩 折叠 通勤 飞行 续航", "蛋白皮耳罩", "环境声模式", "飞行休息"),
        ("PixelRoute", "磁吸手机支架", "磁吸 手机支架 折叠 视频通话 桌面", "铝合金", "多角度转轴", "远程会议"),
        ("CableCove", "多接口快充数据线", "数据线 多接口 快充 编织 收纳 出差", "编织尼龙", "接口切换", "移动办公"),
        ("LensTrail", "便携镜头清洁套", "镜头 清洁 相机 屏幕 便携 无酒精", "超细纤维", "防尘收纳盒", "旅行摄影"),
        ("DeskCurrent", "桌面电源整理盒", "桌面 理线 电源 收纳 插座 整理", "竹纤维复合材", "散热开孔", "桌面办公"),
    ],
    "健康护理": [
        ("CalmOrbit", "旅行热敷眼罩", "热敷 眼罩 旅行 放松 睡眠 可收纳", "亲肤织物", "三档温控", "长途休息"),
        ("RestLine", "颈肩拉伸带", "颈肩 拉伸 放松 轻便 居家 办公", "弹力织带", "长度刻度", "久坐放松"),
        ("SoftStep", "旅行足部按摩球", "足部 按摩球 旅行 轻量 收纳 放松", "天然橡胶", "颗粒表面", "步行后放松"),
        ("BreezeSleep", "可洗睡眠耳塞", "睡眠 耳塞 可洗 收纳 轻便 降低噪音", "医用级硅胶", "分码耳塞头", "酒店休息"),
        ("WarmMori", "便携热敷腰带", "热敷 腰带 轻量 办公 旅行 放松", "柔软针织面料", "定时断电", "通勤休息"),
    ],
    "母婴亲子": [
        ("LittleRoute", "儿童旅行收纳包", "儿童 旅行 收纳 分区 轻便 亲子", "再生聚酯纤维", "姓名卡位", "亲子出行"),
        ("TinySip", "儿童便携饮水杯", "儿童 水杯 防漏 便携 吸管 易清洗", "食品级不锈钢", "防呛吸嘴", "公园活动"),
        ("NestPlay", "折叠游戏收纳垫", "玩具 收纳垫 折叠 亲子 旅行", "棉帆布", "抽绳收束", "候机等待"),
        ("MoriKid", "儿童餐具收纳盒", "儿童 餐具 收纳 便携 可清洗 出行", "食品级硅胶", "分隔卡槽", "外出用餐"),
        ("CloudCub", "亲子防晒帽", "亲子 防晒帽 透气 可调节 旅行", "有机棉", "可调帽围", "海边出行"),
    ],
    "宠物出行": [
        ("PawRoute", "宠物旅行饮水瓶", "宠物 饮水瓶 防漏 便携 散步 旅行", "食品级不锈钢", "一体饮水槽", "城市散步"),
        ("TailNest", "宠物折叠食盆", "宠物 食盆 折叠 易清洗 轻便 出行", "食品级硅胶", "双层容量", "短途旅行"),
        ("FurTrail", "宠物外出收纳包", "宠物 收纳包 零食 拾便袋 分区 出行", "防泼水尼龙", "快取口袋", "日常遛宠"),
    ],
    "办公文具": [
        ("PaperMori", "差旅硬壳笔记本", "笔记本 差旅 防泼水 记录 轻便 办公", "再生纸", "平摊装订", "移动会议"),
        ("DeskLeaf", "桌面文件收纳架", "文件 收纳架 桌面 整理 办公 可叠放", "竹木复合材", "可调分格", "家庭办公"),
        ("NoteRail", "磁吸便签整理板", "便签 磁吸 整理 板 办公 任务管理", "金属面板", "模块磁吸", "项目规划"),
    ],
    "服饰配件": [
        ("MerinoWay", "轻量徒步袜", "徒步袜 透气 快干 轻量 旅行", "美利奴羊毛混纺", "足弓支撑", "徒步旅行"),
        ("UrbanBrim", "可折叠遮阳帽", "遮阳帽 折叠 透气 防晒 旅行", "再生尼龙", "可调节帽围", "城市观光"),
        ("CoastLayer", "速干旅行围巾", "围巾 速干 轻便 防风 旅行 收纳", "莫代尔混纺", "多用途系法", "昼夜温差"),
        ("StepMori", "轻量步行鞋", "步行鞋 轻量 防滑 旅行 透气", "再生网布", "缓震鞋垫", "城市步行"),
        ("RainCuff", "防泼水旅行手套", "手套 防泼水 触屏 轻便 通勤 旅行", "软壳面料", "触屏指尖", "雨天通勤"),
        ("CarryBelt", "弹力旅行腰带", "腰带 弹力 无金属 旅行 安检 轻便", "弹力织带", "无金属扣", "过安检"),
    ],
    "运动健身": [
        ("PaceLoop", "跑步腰包", "跑步 腰包 贴身 防汗 手机 收纳", "弹力莱卡", "防晃结构", "城市跑步"),
        ("YogaMori", "折叠瑜伽垫", "瑜伽垫 折叠 防滑 轻便 旅行", "天然橡胶", "对折收纳", "旅宿练习"),
        ("CoreTrail", "弹力训练带套组", "训练带 拉伸 健身 收纳 轻量", "天然乳胶", "阻力分级", "居家训练"),
        ("CycleLeaf", "骑行补给收纳包", "骑行 收纳包 防泼水 补给 轻便", "防泼水尼龙", "快取拉链", "周末骑行"),
        ("RecoverArc", "运动拉伸滚轮", "拉伸 滚轮 放松 健身 便携 肌肉", "高密度泡棉", "纹理滚压", "训练恢复"),
    ],
}

_EXPANDED_CATEGORY_TARGETS = {
    "旅行装备": 54, "户外运动": 46, "家居生活": 37, "数码配件": 35,
    "健康护理": 25, "母婴亲子": 20, "宠物出行": 18, "办公文具": 18,
    "服饰配件": 32, "运动健身": 27,
}

_EXPANDED_VARIANTS = (
    ("轻量基础款", "轻便", "雾灰"), ("耐用通勤款", "耐用", "岩黑"),
    ("天然材质款", "天然材质", "砂岩色"), ("大容量款", "大容量", "海蓝"),
    ("折叠旅行款", "可折叠", "苔绿"), ("礼赠精选款", "小众设计", "暖棕"),
)


def _expanded_sku_count(index: int) -> int:
    """新增 312 个 SPU 的 SKU 分布：62×1、150×2、75×3、25×4。"""
    if index < 62:
        return 1
    if index < 212:
        return 2
    if index < 287:
        return 3
    return 4


def _build_expanded_demo() -> list[Product]:
    """生成扩容目录，确保每条新增商品至少可寄送一个 V1 模拟费用市场。"""
    products: list[Product] = []
    market_options = (["CN", "US", "EU"], ["US", "GB", "CA"], ["JP", "CN", "KR"], ["EU", "GB", "JP"])
    currency_options = ("CNY", "USD", "EUR", "GBP", "JPY")
    origins = ("CN", "JP", "DE", "US", "KR", "GB", "CA", "SE")
    pid_number = 1201
    global_index = 0

    for category, target in _EXPANDED_CATEGORY_TARGETS.items():
        created = 0
        for family_index, (brand, noun, keywords, material, feature, scene) in enumerate(_EXPANDED_FAMILIES[category]):
            for variant_index, (variant, attribute, color) in enumerate(_EXPANDED_VARIANTS):
                if created >= target:
                    break
                product_id = f"P{pid_number}"
                sku_count = _expanded_sku_count(global_index)
                currency = currency_options[(global_index + family_index) % len(currency_options)]
                base_price = 39.0 + ((global_index * 17 + family_index * 13) % 170)
                skus = [
                    (
                        f"S{sku_index + 1}",
                        f"{color} / {variant} / {sku_index + 1}号规格",
                        base_price + sku_index * 11.0,
                        currency,
                        35 + ((global_index * 11 + sku_index * 17) % 180),
                    )
                    for sku_index in range(sku_count)
                ]
                products.append(Product(
                    product_id=product_id,
                    title=f"{brand} {noun} {variant}",
                    brand=brand,
                    category=category,
                    origin_country=origins[(global_index + family_index) % len(origins)],
                    description=(
                        f"{keywords} {attribute} {material} {feature} {scene} "
                        "跨境精选 多规格可选 适合比较材质 功能与价格"
                    ),
                    ships_to=list(market_options[global_index % len(market_options)]),
                    skus=[_sku(f"{product_id}-{suffix}", spec, price, sku_currency, stock)
                          for suffix, spec, price, sku_currency, stock in skus],
                    highlights=[
                        ProductHighlight("材质", material),
                        ProductHighlight("特征", feature),
                        ProductHighlight("适用", scene),
                        ProductHighlight("选择", attribute),
                    ],
                ))
                pid_number += 1
                global_index += 1
                created += 1
            if created >= target:
                break
        if created != target:
            raise RuntimeError(f"扩容品类数量不足：{category} {created}/{target}")
    return products


def _build_extra() -> list[Product]:
    """把紧凑表展开成 Product。"""
    products: list[Product] = []
    for pid, title, brand, category, origin, desc, ships_to, skus, highlights in _EXTRA_SPECS:
        products.append(
            Product(
                product_id=pid,
                title=title,
                brand=brand,
                category=category,
                origin_country=origin,
                description=desc,
                highlights=[ProductHighlight(name, value) for name, value in highlights],
                ships_to=list(ships_to),
                skus=[
                    _sku(f"{pid}-{suffix}", spec, major, currency, stock)
                    for suffix, spec, major, currency, stock in skus
                ],
            ),
        )
    return products


def _build_global_demo() -> list[Product]:
    """展开全球精选虚构目录；数据只服务于 MVP 演示。"""
    products: list[Product] = []
    for pid, title, brand, category, origin, desc, ships_to, skus, highlights in _GLOBAL_DEMO_SPECS:
        products.append(Product(
            product_id=pid, title=title, brand=brand, category=category,
            origin_country=origin, description=desc, ships_to=list(ships_to),
            highlights=[ProductHighlight(name, value) for name, value in highlights],
            skus=[_sku(f"{pid}-{suffix}", spec, major, currency, stock)
                  for suffix, spec, major, currency, stock in skus],
        ))
    return products


def _build_compliant_demo() -> list[Product]:
    """展开自建虚构目录；仅用于开发、演示和召回评测。"""
    products: list[Product] = []
    for pid, title, brand, category, origin, desc, ships_to, skus, highlights in _COMPLIANT_DEMO_SPECS:
        products.append(Product(
            product_id=pid, title=title, brand=brand, category=category,
            origin_country=origin, description=desc, ships_to=list(ships_to),
            highlights=[ProductHighlight(name, value) for name, value in highlights],
            skus=[_sku(f"{pid}-{suffix}", spec, major, currency, stock)
                  for suffix, spec, major, currency, stock in skus],
        ))
    return products


def build_seed_products() -> list[Product]:
    return [
        Product(
            product_id="P1001",
            title="Nomadica 旅行三件套（收纳袋+颈枕+眼罩）",
            brand="Nomadica",
            category="旅行装备",
            origin_country="VN",
            description="帆布加尼龙材质 结实耐磨 抗造 轻便 无塑料感 小众设计师品牌 适合长途飞行 旅行收纳",
            highlights=[
                ProductHighlight("材质", "帆布+再生尼龙，非塑料"),
                ProductHighlight("重量", "全套 420g 轻便"),
                ProductHighlight("风格", "小众设计师联名款"),
            ],
            ships_to=["CN", "US", "SG"],
            skus=[
                _sku("P1001-S1", "军绿色", 189.0, "CNY", 50),
                _sku("P1001-S2", "沙漠黄", 199.0, "CNY", 30),
            ],
        ),
        Product(
            product_id="P1002",
            title="TrailOx 20寸登机行李箱 铝框款",
            brand="TrailOx",
            category="旅行装备",
            origin_country="DE",
            description="铝镁合金框架 PC箱体 结实抗摔 抗造 万向静音轮 TSA海关锁 登机尺寸 商务旅行",
            highlights=[
                ProductHighlight("箱体", "德国工艺铝框，抗摔"),
                ProductHighlight("轮组", "日本静音万向轮"),
            ],
            ships_to=["CN", "US", "EU"],
            skus=[
                _sku("P1002-S1", "银色 / 20寸", 899.0, "CNY", 20),
                _sku("P1002-S2", "黑色 / 20寸", 899.0, "CNY", 15),
            ],
        ),
        Product(
            product_id="P1003",
            title="Wanderlite 折叠旅行双肩包 35L",
            brand="Wanderlite",
            category="旅行装备",
            origin_country="KR",
            description="防泼水尼龙 超轻 可折叠收纳 大容量 35升 徒步 城市通勤 便宜实惠 高性价比",
            highlights=[
                ProductHighlight("重量", "仅 380g 超轻"),
                ProductHighlight("收纳", "可折叠成手掌大小"),
            ],
            ships_to=["CN", "JP", "SG"],
            skus=[
                _sku("P1003-S1", "石墨黑", 129.0, "CNY", 80),
                _sku("P1003-S2", "雾霾蓝", 129.0, "CNY", 60),
            ],
        ),
        Product(
            product_id="P1004",
            title="AeroHush 主动降噪蓝牙耳机 Pro",
            brand="AeroHush",
            category="数码配件",
            origin_country="US",
            description="主动降噪 蓝牙5.4 40小时续航 通话降噪 飞行旅行伴侣 头戴式 折叠便携",
            highlights=[
                ProductHighlight("降噪", "-45dB 深度主动降噪"),
                ProductHighlight("续航", "40 小时长续航"),
            ],
            ships_to=["CN", "US", "EU"],
            skus=[
                _sku("P1004-S1", "曜石黑", 219.0, "USD", 40),
                _sku("P1004-S2", "月光白", 229.0, "USD", 25),
            ],
        ),
        Product(
            product_id="P1005",
            title="VoltTrek 65W 氮化镓旅行充电器（全球插脚）",
            brand="VoltTrek",
            category="数码配件",
            origin_country="CN",
            description="氮化镓 GaN 65W 快充 全球通用插脚 英标欧标美标 出国旅行 多口 Type-C 轻巧",
            highlights=[
                ProductHighlight("插脚", "全球 150+ 国家通用"),
                ProductHighlight("功率", "65W 双口快充"),
            ],
            ships_to=["CN", "US", "EU", "JP"],
            skus=[
                _sku("P1005-S1", "标准版", 159.0, "CNY", 100),
            ],
        ),
        Product(
            product_id="P1006",
            title="TerraCotta 手工粗陶旅行茶具套装",
            brand="TerraCotta",
            category="家居生活",
            origin_country="JP",
            description="手工粗陶 一壶两杯 便携旅行装 无塑料 天然材质 小众手作 茶道 送礼",
            highlights=[
                ProductHighlight("材质", "天然粗陶，无塑料"),
                ProductHighlight("工艺", "日本手作窑烧"),
            ],
            ships_to=["CN", "JP"],
            skus=[
                _sku("P1006-S1", "原色", 268.0, "CNY", 18),
            ],
        ),
        Product(
            product_id="P1007",
            title="PeakDry 速干旅行毛巾三件装",
            brand="PeakDry",
            category="旅行装备",
            origin_country="TW",
            description="超细纤维 速干 轻薄 抗菌 三条装 大中小 游泳 健身 户外 便宜 高性价比",
            highlights=[
                ProductHighlight("速干", "3 分钟拧干即用"),
                ProductHighlight("装量", "大中小三条装"),
            ],
            ships_to=["CN", "US", "SG"],
            skus=[
                _sku("P1007-S1", "灰蓝绿三色", 79.0, "CNY", 200),
            ],
        ),
        Product(
            product_id="P1008",
            title="LumenGo 便携露营灯 可充电",
            brand="LumenGo",
            category="户外运动",
            origin_country="CN",
            description="露营灯 三档调光 Type-C充电 磁吸挂钩 防水 IPX5 户外 应急 停电 抗造耐摔",
            highlights=[
                ProductHighlight("防护", "IPX5 防水，抗摔"),
                ProductHighlight("续航", "最长 72 小时"),
            ],
            ships_to=["CN", "US", "EU"],
            skus=[
                _sku("P1008-S1", "军绿", 89.0, "CNY", 150),
                _sku("P1008-S2", "橙色", 89.0, "CNY", 90),
            ],
        ),
        Product(
            product_id="P1009",
            title="SilkRoute 桑蚕丝旅行睡袋内胆",
            brand="SilkRoute",
            category="旅行装备",
            origin_country="CN",
            description="100%桑蚕丝 亲肤 隔脏 超轻 200g 卷收便携 酒店青旅 露营 天然材质 无塑料",
            highlights=[
                ProductHighlight("材质", "100% 桑蚕丝，天然无塑料"),
                ProductHighlight("重量", "仅 200g"),
            ],
            ships_to=["CN", "US", "EU", "JP"],
            skus=[
                _sku("P1009-S1", "本白", 329.0, "CNY", 35),
            ],
        ),
        Product(
            product_id="P1010",
            title="CascadePro 钛合金折叠登山杖一对",
            brand="CascadePro",
            category="户外运动",
            origin_country="US",
            description="钛合金 折叠五节 快锁 减震 徒步 登山 结实抗造 轻量 260g单支 专业户外",
            highlights=[
                ProductHighlight("材质", "航空钛合金，结实抗造"),
                ProductHighlight("折叠", "五节折叠仅 36cm"),
            ],
            ships_to=["US", "CN", "EU"],
            skus=[
                _sku("P1010-S1", "钛原色一对", 149.0, "USD", 22),
            ],
        ),
        *_build_extra(),
        *_build_compliant_demo(),
        *_build_global_demo(),
        *_build_expanded_demo(),
    ]
