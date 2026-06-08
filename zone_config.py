# ==========================================
# 1. 全局共享配置 (评级标准、环境基准线、满分限制)
# ==========================================
GLOBAL_CONFIG = {
    "max_score": 10.0,
    
    # 动态蒸发系数的基准线 (共享环境变量)
    "evap_temp_weight": 0.001,
    "evap_temp_baseline": 15.0,
    "evap_hum_weight": 0.001,
    "evap_hum_baseline": 60.0,
    "evap_cloud_weight": 0.0002,
    "evap_cloud_baseline": 50.0,
    "evap_min": 0.90,
    "evap_max": 0.999,

    "dew_trigger_humidity": 92.0,   # 触发物理结露的空气湿度线 (%)
    "dew_max_penalty": 4.0,         # 结露拉满时的湿滑附加分
    "dew_decay_rate": 0.9,         # 露水蒸发保留率 (0.85 代表每小时蒸发15%)
        
    "active_rain_threshold": 0.2,
    "active_rain_penalty": 5.0,
    
    # 沙化触发的环境基准
    "dust_temp_baseline": 22.0,
    "dusty_threshold": 10.0,       # DI 超过 4.0 触发 dusty 评级
    
    # 你的自定义状态评级字典
    "grading": {
        "swi": [
            {"max": 2.5, "label": "good"},
            {"max": 4.0, "label": "damp"},
            {"max": 7.5, "label": "wet"},
            {"max": 10.1, "label": "muddy"}
        ],
        "rsi": [
            {"max": 1.0, "label": "dry"},
            {"max": 7.5, "label": "slick"},
            {"max": 10.1, "label": "dangerous"}
        ]
    },

    # 黄金守则标签到分数的映射
    "label_to_score": {
        "swi": {
            "dusty": [0.0, 15.0],
            "dry": [0.0, 5.0],
            "good": [1.5, 0.0],
            "damp": [3.75, 0.0],
            "wet": [5.75, 0.0],
            "muddy": [9.25, 0.0],
            
        },
        "rsi": {
            "dry": [0.5],
            "slick": [5.0],
            "dangerous": [9.25]
        }
    }
}

# ==========================================
# 2. 各大骑行区域特异性物理参数配置
# ==========================================
TRAIL_CONFIGS = {
    "Mount Seymour": {
        "trail_name": "Mount Seymour",
        "swi_scale": 20.0,             # 基准保水性
        "soil_i_max": 7.5,             # 基准渗透率
        "evap_base": 0.997,             # 基准蒸发率
        "dust_trigger_swi": 0.5,       # 触发沙化的 SWI 阈值
        "dust_accum_rate": 0.03,       # 沙化速率
        "rsi_rain_lookback": 24,       # 树根岩石考量过去 12 小时降水
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 75.0,     # 返潮阈值
        "rsi_hum_penalty": 5.0
    },
    
    "Mount Fromme": {
        "trail_name": "Mount Fromme",
        "swi_scale": 20.0,             # 【抗毁容】很难变得极其泥泞
        "soil_i_max": 7.5,             # 【排水快】大量降水作为径流排走
        "evap_base": 0.997,
        "dust_trigger_swi": 0.5,
        "dust_accum_rate": 0.03,
        "rsi_rain_lookback": 24,       # 花岗岩 and 树根依然湿滑
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 75.0,
        "rsi_hum_penalty": 5.0
    },
    
    "Cypress Mountain": {
        "trail_name": "Cypress Mountain",
        "swi_scale": 25.0,             # 深层黑土
        "soil_i_max": 8.0,
        "evap_base": 0.998,            # 【极慢蒸发】林冠太厚，阻挡阳光
        "dust_trigger_swi": 0.5,
        "dust_accum_rate": 0.02,       # 【耐旱】很难彻底沙化
        "rsi_rain_lookback": 24,       # 【危险黑冰】树根长达 24 小时难以干透
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 70.0,     # 【极易返潮】
        "rsi_hum_penalty": 5.0
    },
    
    "Eagle Mountain": {
        "trail_name": "Eagle Mountain",
        "swi_scale": 25.0,             # 土层较薄
        "soil_i_max": 5.0,
        "evap_base": 0.995,             # 【极快干燥】暴露度高，风吹日晒
        "dust_trigger_swi": 0.5,       # 【极易沙化】SWI 较高时就开始起浮土
        "dust_accum_rate": 0.02,       # 【高速沙化】
        "rsi_rain_lookback": 12,        # 【干得快】石板出太阳几小时就恢复抓地
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 80.0,     # 相对不容易返潮
        "rsi_hum_penalty": 5.0
    },
    
    "Burke Mountain": {
        "trail_name": "Burke Mountain",
        "swi_scale": 25.0,             # 【沼泽泥浆】极低的容水量，马马上满分
        "soil_i_max": 8.0,             # 【不透水】黏土吸水但无法深层渗透
        "evap_base": 0.998,            # 蒸发慢
        "dust_trigger_swi": 0.5,       # 必须骨干才会沙化
        "dust_accum_rate": 0.02,
        "rsi_rain_lookback": 24,
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 65.0,     # 【极其潮湿】一点湿气树根就打滑
        "rsi_hum_penalty": 5.0
    },
    
    "Alice Lake": {
        "trail_name": "Alice Lake",
        "swi_scale": 20.0,             # 复制 Mount Fromme 的配置
        "soil_i_max": 7.5,
        "evap_base": 0.997,
        "dust_trigger_swi": 0.5,
        "dust_accum_rate": 0.03,
        "rsi_rain_lookback": 24,
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 75.0,
        "rsi_hum_penalty": 5.0
    },
    
    "Diamond Head": {
        "trail_name": "Diamond Head",
        "swi_scale": 20.0,             # 复制 Mount Seymour 的配置
        "soil_i_max": 7.5,
        "evap_base": 0.997,
        "dust_trigger_swi": 0.5,
        "dust_accum_rate": 0.03,
        "rsi_rain_lookback": 24,
        "rsi_rain_weight": 1.2,
        "rsi_hum_threshold": 75.0,
        "rsi_hum_penalty": 5.0
    }
}