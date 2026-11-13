import os
import sqlite3
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """获取项目根目录（兼容 Python 源码运行与 PyInstaller 打包后的 exe 路径）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def init_directories(base_dir: Path):
    """创建标准工程目录与文件夹状态机"""
    dirs = [
        base_dir / "app" / "adapters",
        base_dir / "app" / "core",
        base_dir / "app" / "ui",
        base_dir / "config",
        base_dir / "storage" / "raw_snapshots",
        base_dir / "storage" / "browser_profile",
        base_dir / "storage" / "vector_index",
        base_dir / "workspace" / "01_待上架",
        base_dir / "workspace" / "02_处理中",
        base_dir / "workspace" / "03_待人工复核",
        base_dir / "workspace" / "04_已上架归档",
        base_dir / "workspace" / "05_异常隔离",
        base_dir / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"✅ [目录初始化] 已成功校验并创建 {len(dirs)} 个标准工作目录。")


def init_env_file(base_dir: Path):
    """生成默认配置文件模板 (.env)，防止首次运行缺少配置报错"""
    env_path = base_dir / ".env"
    if not env_path.exists():
        default_env = (
            "# 本地大模型 Ollama 配置 (RTX 4060 Ti 潮汐按需加载)\n"
            "LOCAL_VLM_BASE_URL=http://127.0.0\n"
            "LOCAL_VLM_MODEL=qwen3-vl:8b\n"
            "LOCAL_VLM_KEEP_ALIVE=3m\n\n"
            "# 远程云端大模型 DeepSeek 配置 (用于 SEO 爆款标题精加工与复杂推理)\n"
            "DEEPSEEK_API_KEY=请在此填入你的DeepSeek_API_Key\n"
            "DEEPSEEK_BASE_URL=https://deepseek.com\n"
            "DEEPSEEK_MODEL=deepseek-chat\n\n"
            "# HuggingFace 国内镜像加速 (用于首次下载 BAAI/bge-m3 到系统内存)\n"
            "HF_ENDPOINT=https://hf-mirror.com\n"
        )
        env_path.write_text(default_env, encoding="utf-8")
        print("✅ [配置初始化] 已生成默认环境变量文件 (.env)，请记得填入 DeepSeek API Key。")


def init_database(base_dir: Path):
    """初始化 SQLite 数据库 (开启 WAL 并发模式 + 8 张核心表 + D2R 预置数据)"""
    db_path = base_dir / "storage" / "d2r_market.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 1. 开启 WAL 并发模式与性能优化
    cursor.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA foreign_keys = ON;
        PRAGMA temp_store = MEMORY;

        -- 表1: 系统全局参数与清理规则表
        CREATE TABLE IF NOT EXISTS system_configs (
            config_key      TEXT PRIMARY KEY,
            config_value    TEXT NOT NULL,
            value_type      TEXT DEFAULT 'string',
            description     TEXT,
            updated_at      DATETIME DEFAULT (datetime('now', 'localtime'))
        );

        -- 表2: 可维护白名单监控关键词配置表
        CREATE TABLE IF NOT EXISTS monitor_keywords (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            platform            TEXT NOT NULL DEFAULT 'DD373',
            game_mode           TEXT NOT NULL,
            item_category       TEXT NOT NULL, -- RUNE / CURRENCY / DAILY_UNIQUE / SOCKET_BASE / GODLY_RARE
            platform_cat_id     TEXT DEFAULT '',
            keyword             TEXT NOT NULL,
            standard_name       TEXT,
            price_min           REAL DEFAULT 0.0,
            price_max           REAL DEFAULT 99999.0,
            crawl_interval_mins INTEGER NOT NULL DEFAULT 60,
            is_active           INTEGER NOT NULL DEFAULT 1,
            last_crawled_at     DATETIME,
            ext_json            TEXT DEFAULT '{}',
            created_at          DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_kw_active ON monitor_keywords(platform, is_active, item_category);

        -- 表3: 通货汇率与兑换历史时序表 (驱动通货走势图)
        CREATE TABLE IF NOT EXISTS currency_rates_timeseries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL DEFAULT 'DD373',
            game_mode       TEXT NOT NULL,
            currency_code   TEXT NOT NULL,
            unit_price_cny  REAL NOT NULL,
            ratio_to_ber    REAL,
            sample_count    INTEGER DEFAULT 0,
            recorded_at     DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_curr_ts ON currency_rates_timeseries(platform, game_mode, currency_code, recorded_at);

        -- 表4: 标品与装备历史价格走势表 (驱动价格带走势图与自动定价)
        CREATE TABLE IF NOT EXISTS sku_price_timeseries (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            platform            TEXT NOT NULL DEFAULT 'DD373',
            sku_key             TEXT NOT NULL,
            game_mode           TEXT NOT NULL,
            item_category       TEXT NOT NULL,
            standard_name       TEXT NOT NULL,
            is_ethereal         INTEGER NOT NULL DEFAULT 0,
            weighted_avg_price  REAL NOT NULL,
            p25_low_price       REAL,
            p50_median_price    REAL,
            p75_high_price      REAL,
            real_sold_avg_price REAL,
            valid_sample_count  INTEGER DEFAULT 0,
            ext_json            TEXT DEFAULT '{}',
            recorded_at         DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_sku_ts ON sku_price_timeseries(platform, sku_key, recorded_at);

        -- 表5: D2R 黑话词典与极品变量知识库表 (RAG 动态注入)
        CREATE TABLE IF NOT EXISTS d2r_knowledge_base (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            standard_name   TEXT NOT NULL UNIQUE,
            item_category   TEXT NOT NULL,
            aliases_json    TEXT NOT NULL DEFAULT '[]',
            variable_rules  TEXT,
            ext_json        TEXT DEFAULT '{}',
            updated_at      DATETIME DEFAULT (datetime('now', 'localtime'))
        );

        -- 表6: AI 语义解析缓存与负样本黑名单表
        CREATE TABLE IF NOT EXISTS ai_semantic_cache (
            title_hash      TEXT PRIMARY KEY,
            raw_title       TEXT NOT NULL,
            parsed_json     TEXT NOT NULL,
            is_blacklisted  INTEGER NOT NULL DEFAULT 0,
            hit_count       INTEGER NOT NULL DEFAULT 1,
            created_at      DATETIME DEFAULT (datetime('now', 'localtime'))
        );

        -- 表7: 本地调价风控账本表 (权限开关、出货策略、双边安全笼、防重指纹)
        CREATE TABLE IF NOT EXISTS local_pricing_guard (
            platform_item_id  TEXT PRIMARY KEY,
            platform          TEXT NOT NULL DEFAULT 'DD373',
            sku_key           TEXT NOT NULL,
            image_fingerprint TEXT UNIQUE,
            reprice_mode      TEXT NOT NULL DEFAULT 'ADVISORY_ONLY', -- ADVISORY_ONLY / SEMI_AUTO / FULL_AUTO
            sales_strategy    TEXT NOT NULL DEFAULT 'HOT_STABLE',    -- PROFIT_HARVEST / HOT_STABLE / FAST_TURNOVER / GODLY_LOCK
            min_cost_floor    REAL NOT NULL DEFAULT 0.0,
            max_price_ceiling REAL NOT NULL DEFAULT 99999.0,
            allow_night_drop  INTEGER NOT NULL DEFAULT 0,
            last_price        REAL,
            last_repriced_at  DATETIME,
            ext_json          TEXT DEFAULT '{}',
            created_at        DATETIME DEFAULT (datetime('now', 'localtime'))
        );

        -- 表8: 自动化上架与调价审计流水表
        CREATE TABLE IF NOT EXISTS reprice_audit_logs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            platform         TEXT NOT NULL DEFAULT 'DD373',
            platform_item_id TEXT NOT NULL,
            action_type      TEXT NOT NULL,
            old_price        REAL,
            new_price        REAL NOT NULL,
            market_ref_price REAL,
            trigger_reason   TEXT,
            api_status       TEXT DEFAULT 'SUCCESS',
            created_at       DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_audit_time ON reprice_audit_logs(created_at);
    """)

    # 2. 写入默认系统配置（幂等插入，不覆盖用户已有修改）
    default_configs = [
        ("db_schema_version", "1", "int", "当前数据库架构版本号"),
        ("global_reprice_mode", "ADVISORY_ONLY", "string", "全局默认改价模式: ADVISORY_ONLY(仅建议) / SEMI_AUTO(半自动) / FULL_AUTO(全自动)"),
        ("reprice_cooldown_hours", "6", "int", "同一商品自动调价冷却期(小时)"),
        ("price_diff_deadband_pct", "3.0", "float", "触发自动改价的最小价差波动死区(%)"),
        ("profit_harvest_gap_pct", "20.0", "float", "触发利润收割向上提价的断层价差阈值(%)"),
        ("low_competition_hours", '{"start": "01:00", "end": "09:30"}', "json", "低竞争保护时段(只升不降)"),
        ("high_value_review_limit", "500.0", "float", "单品估值超过此金额(元)强制转入人工复核"),
        ("ai_confidence_threshold", "85", "int", "云端视觉模型识图最低置信度门禁"),
        ("snapshot_retention_days", "30", "int", "本地时间轴JSON快照默认保留天数"),
        ("bound_listing_folder", str(base_dir / "workspace" / "01_待上架"), "string", "当前监听的本地待上架截图目录"),
        ("bound_game_mode", "术士军临-天梯软核", "string", "待上架目录绑定的默认游戏区服模式"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO system_configs (config_key, config_value, value_type, description) VALUES (?, ?, ?, ?)",
        default_configs,
    )

    # 3. 写入 D2R 基础黑话与变量知识库预置数据
    default_kb = [
        ("31#乔", "RUNE", '["Jah", "31号", "31号乔", "乔符文"]', "硬通货基准，无变量"),
        ("30#贝", "RUNE", '["Ber", "30号", "30号贝", "贝符文"]', "核心锚定通货，无变量"),
        ("28#罗", "RUNE", '["Lo", "28号", "28号罗", "罗符文"]', "高级符文，无变量"),
        ("紫PG", "CURRENCY", '["完美紫宝石", "紫宝石", "PAmethyst", "紫pg"]', "手工项链刚需通货，通常按10个或40个一组交易"),
        ("谐角之冠", "DAILY_UNIQUE", '["军帽", "Shako", "绿帽子"]', "防御力98-141浮动，141满防为小极品"),
        ("格里芬之眼", "GODLY_RARE", '["格力风", "年纪头", "电头", "Griffon"]', "减电抗15%-20%，加电伤10%-15%；-20/+15为天价满变"),
        ("死神的丧钟", "GODLY_RARE", '["死丧", "Reaper"]', "重点区分有形与无形(Ethereal)；无形且ED接近240%/15吸血为极品"),
        ("执政官铠甲", "SOCKET_BASE", '["AP甲", "执政官", "Archon Plate"]', "重点提取凹槽数(3孔/4孔)、是否无形及15ED增强防御"),
        ("狂战士斧", "SOCKET_BASE", '["BA", "狂战斧", "Berserker Axe"]', "重点提取凹槽数(5孔/6孔)、是否无形及15ED增强伤害"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO d2r_knowledge_base (standard_name, item_category, aliases_json, variable_rules) VALUES (?, ?, ?, ?)",
        default_kb,
    )

    conn.commit()
    conn.close()
