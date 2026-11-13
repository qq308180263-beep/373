# 《暗黑破坏神2：重制版》本地 SQLite 数据库初始化脚本 (`init_db.sql`)

> **架构说明**：
> 1. 强制开启 **WAL (Write-Ahead Logging)** 模式，保障 Windows 客户端 UI 线程读取走势图与后台多线程写入价格数据时互不阻塞。
> 2. 所有核心业务表均预留 `platform` 多平台兼容字段及 `ext_json` 弹性扩展字段，方便后期无缝扩展功能而无需重构表结构。

```sql
-- =========================================================================
-- 0. SQLite 并发与性能优化配置
-- =========================================================================
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;

-- =========================================================================
-- 1. 系统参数与数据清理规则表 (system_configs)
-- =========================================================================
CREATE TABLE IF NOT EXISTS system_configs (
    config_key      TEXT PRIMARY KEY,               -- 配置键名
    config_value    TEXT NOT NULL,                  -- 配置值
    value_type      TEXT DEFAULT 'string',          -- 类型: string / int / float / bool / json
    description     TEXT,                           -- 参数中文说明
    updated_at      DATETIME DEFAULT (datetime('now', 'localtime'))
);

-- =========================================================================
-- 2. 可维护监控关键词配置表 (monitor_keywords)
-- =========================================================================
CREATE TABLE IF NOT EXISTS monitor_keywords (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL DEFAULT 'DD373',  -- 交易平台标识 (预留多平台扩展)
    game_mode       TEXT NOT NULL,                  -- 区服模式: 天梯软核 / 天梯专家 / 非天梯软核 / 非天梯专家
    task_category   TEXT NOT NULL,                  -- 任务类型: 通货汇率监控 / 标品日用分析 / 在售同款巡检
    keyword         TEXT NOT NULL,                  -- 搜索关键词 (如: 30号贝, 谐角之冠)
    standard_name   TEXT,                           -- 关联的D2R标准物品名 (便于归类聚合)
    price_min       REAL DEFAULT 0.0,               -- 最低价格过滤门禁 (防底层垃圾单)
    price_max       REAL DEFAULT 99999.0,           -- 最高价格过滤门禁
    is_active       INTEGER NOT NULL DEFAULT 1,     -- 是否启用: 1=启用, 0=暂停
    ext_json        TEXT DEFAULT '{}',              -- 弹性扩展字段
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    updated_at      DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_keywords_active ON monitor_keywords(platform, is_active, task_category);

-- =========================================================================
-- 3. 通货汇率与兑换历史时序表 (currency_rates_timeseries)
-- 专为前端【通货走势图】与【打包套餐净值剥离】提供历史时间轴数据
-- =========================================================================
CREATE TABLE IF NOT EXISTS currency_rates_timeseries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL DEFAULT 'DD373',
    game_mode       TEXT NOT NULL,                  -- 天梯软核 / 非天梯软核等
    currency_code   TEXT NOT NULL,                  -- 标准符文编号: 31#乔 / 30#贝 / 28#罗 / 紫PG / 洗点水
    unit_price_cny  REAL NOT NULL,                  -- 清洗后的当前健康人民币单价
    ratio_to_ber    REAL,                           -- 相对 30#贝 的实时兑换比率 (如 1乔 = 1.65贝)
    sample_count    INTEGER DEFAULT 0,              -- 本次计算采纳的有效挂单样本数
    recorded_at     DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_currency_ts ON currency_rates_timeseries(platform, game_mode, currency_code, recorded_at);

-- =========================================================================
-- 4. 标品与装备历史价格走势表 (sku_price_timeseries)
-- 专为前端【标品价格带走势图】与【自动定价引擎】提供基准价目点位
-- =========================================================================
CREATE TABLE IF NOT EXISTS sku_price_timeseries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform            TEXT NOT NULL DEFAULT 'DD373',
    sku_key             TEXT NOT NULL,              -- 唯一聚合键: 如 "天梯软核_谐角之冠_有形"
    game_mode           TEXT NOT NULL,
    standard_name       TEXT NOT NULL,              -- D2R 官方标准名
    is_ethereal         INTEGER NOT NULL DEFAULT 0, -- 0=有形, 1=无形
    item_tier           TEXT NOT NULL,              -- 走量标品 / 稀缺极品
    weighted_avg_price  REAL NOT NULL,              -- 时间衰减加权均价
    p25_low_price       REAL,                       -- 25%分位竞争低价 (价格优势区参考)
    p50_median_price    REAL,                       -- 50%分位主流中位价
    p75_high_price      REAL,                       -- 75%分位高价 (用于画健康价格阴影带)
    real_sold_avg_price REAL,                       -- 探测到的真实成交均价 (可为空)
    valid_sample_count  INTEGER DEFAULT 0,          -- 有效样本数量
    ext_json            TEXT DEFAULT '{}',          -- 弹性扩展字段
    recorded_at         DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sku_ts ON sku_price_timeseries(platform, sku_key, recorded_at);

-- =========================================================================
-- 5. D2R 黑话词典与极品变量知识库表 (d2r_knowledge_base)
-- 供 AI 提示词动态检索注入 (RAG)，支持客户端界面随时增删改
-- =========================================================================
CREATE TABLE IF NOT EXISTS d2r_knowledge_base (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_name   TEXT NOT NULL UNIQUE,           -- D2R 官方标准中文名 (如: 谐角之冠)
    category        TEXT NOT NULL,                  -- 类别: 暗金装备 / 符文之语 / 极品底材 / 高级符文 / 杂货通货
    aliases_json    TEXT NOT NULL DEFAULT '[]',     -- 玩家黑话别名 JSON 数组 (如: ["军帽", "军帽Shako"])
    item_tier       TEXT NOT NULL DEFAULT '走量标品',-- 默认分级: 走量标品 / 稀缺极品
    variable_rules  TEXT,                           -- 极品变量判定标准 (如: "满防141; 格里芬满变:-20电抗/+15电伤")
    ext_json        TEXT DEFAULT '{}',
    updated_at      DATETIME DEFAULT (datetime('now', 'localtime'))
);

-- =========================================================================
-- 6. AI 语义解析缓存与负样本黑名单表 (ai_semantic_cache)
-- 缓存已解析过的竞品标题结构化结果，并拦截人工标记的恶意引流话术
-- =========================================================================
CREATE TABLE IF NOT EXISTS ai_semantic_cache (
    title_hash      TEXT PRIMARY KEY,               -- 商品标题 MD5 哈希值
    raw_title       TEXT NOT NULL,                  -- 原始竞品标题
    parsed_json     TEXT NOT NULL,                  -- AI 提取出的标准结构化 JSON
    is_blacklisted  INTEGER NOT NULL DEFAULT 0,     -- 1=人工或AI标记的恶意引流/蹭词条黑名单
    hit_count       INTEGER NOT NULL DEFAULT 1,     -- 缓存命中次数统计
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    last_hit_at     DATETIME DEFAULT (datetime('now', 'localtime'))
);

-- =========================================================================
-- 7. 本地调价风控账本表 (local_pricing_guard)
-- 补充平台 API 缺失的私有商业风控属性 (成本底线、防抖冷却期、图片防重指纹)
-- =========================================================================
CREATE TABLE IF NOT EXISTS local_pricing_guard (
    platform_item_id TEXT PRIMARY KEY,              -- 关联平台(DD373)上的自家在售商品 ID
    platform         TEXT NOT NULL DEFAULT 'DD373',
    sku_key          TEXT NOT NULL,                 -- 关联的基准价目键
    image_fingerprint TEXT UNIQUE,                  -- 截图组合 MD5 指纹 (防重复上架同一装备)
    min_cost_floor   REAL NOT NULL DEFAULT 0.0,     -- 本地保底成本红线 (自动调价绝不跌破此值)
    pricing_strategy TEXT NOT NULL DEFAULT '薄利走量', -- 策略: 薄利走量 / 稀缺高溢价 / 锁定不调价
    last_price       REAL,                          -- 上次设定的售价
    last_repriced_at DATETIME,                      -- 上次自动调价时间戳 (用于计算冷却期)
    ext_json         TEXT DEFAULT '{}',
    created_at       DATETIME DEFAULT (datetime('now', 'localtime'))
);

-- =========================================================================
-- 8. 自动化上架与调价操作审计流水表 (reprice_audit_logs)
-- 记录每一次自动动作的前后价格与原因，支持一键清理与异常溯源
-- =========================================================================
CREATE TABLE IF NOT EXISTS reprice_audit_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    platform         TEXT NOT NULL DEFAULT 'DD373',
    platform_item_id TEXT NOT NULL,
    action_type      TEXT NOT NULL,                 -- 操作类型: 自动上架 / 自动降价 / 自动涨价 / 人工确认上架 / 熔断拦截
    old_price        REAL,                          -- 调价前价格 (新上架为 NULL)
    new_price        REAL NOT NULL,                 -- 操作后价格
    market_ref_price REAL,                          -- 当时参考的市场加权均价
    trigger_reason   TEXT,                          -- 触发原因说明 (如: "均价下浮5%保持P25优势")
    api_status       TEXT DEFAULT 'SUCCESS',        -- 接口执行结果: SUCCESS / FAILED
    created_at       DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON reprice_audit_logs(created_at);

-- =========================================================================
-- 9. 初始化预置基础配置与 D2R 典型知识库数据
-- =========================================================================
INSERT OR IGNORE INTO system_configs (config_key, config_value, value_type, description) VALUES
('db_schema_version', '1', 'int', '当前数据库架构版本号'),
('reprice_cooldown_hours', '6', 'int', '同一商品自动调价最小冷却间隔(小时)，防频繁改价风控'),
('price_diff_deadband_pct', '3.0', 'float', '触发自动调价的最小价差百分比(%)，小于此波动不改价'),
('走量_discount_pct', '5.0', 'float', '走量标品相对市场有效均价的下浮竞争比例(%)'),
('high_value_review_limit', '500.0', 'float', '单品估值超过此金额(元)强制转入人工复核队列'),
('ai_confidence_threshold', '85', 'int', '视觉大模型识图最低置信度门禁(0-100)'),
('snapshot_retention_days', '30', 'int', '本地时间轴JSON快照默认保留天数');

INSERT OR IGNORE INTO d2r_knowledge_base (standard_name, category, aliases_json, item_tier, variable_rules) VALUES
('31#乔', '高级符文', '["Jah", "31号", "31号乔", "乔符文"]', '走量标品', '固定属性无变量，硬通货基准'),
('30#贝', '高级符文', '["Ber", "30号", "30号贝", "贝符文"]', '走量标品', '固定属性无变量，核心锚定通货'),
('28#罗', '高级符文', '["Lo", "28号", "28号罗", "罗符文"]', '走量标品', '固定属性无变量'),
('谐角之冠', '暗金装备', '["军帽", "Shako", "绿帽子"]', '走量标品', '防御力98-141浮动，141满防为小极品'),
('格里芬之眼', '暗金装备', '["格力风", "年纪头", "电头", "Griffon"]', '稀缺极品', '减电抗15%-20%，加电伤10%-15%；-20/+15为天价满变'),
('死神的丧钟', '暗金装备', '["死丧", "Reaper"]', '稀缺极品', '重点区分有形与无形(Ethereal)；无形且ED接近240%/15吸血为极品'),
('谜团', '符文之语', '["Enigma", "TP甲", "传送甲"]', '稀缺极品', '关注底材(执政官铠甲/法师铠甲/灰暮寿衣)及15ED无耐久底材');
```
