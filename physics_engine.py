from zone_config import TRAIL_CONFIGS
from zone_config import GLOBAL_CONFIG
from typing import List, Dict, Tuple

_AI_WEIGHT = 0.6

# ==========================================
# 核心计算逻辑 (集成 DI 与 自定义评级)
# ==========================================
class TrailConditionAnalyzer:
    def __init__(self, hourly_data: List[Dict], trail_config: Dict):
        self.data = hourly_data
        self.cfg_global = GLOBAL_CONFIG
        self.cfg_trail = trail_config

        self.dew_residue = 0.0
        
        self.swi = 0.0  
        self.di = 0.0   
        self.rsi = 0.0  

    def _get_swi_label(self, swi:float, di:float) -> str:
        """获取土壤评级 (优先判定 Dusty 状态)"""
        if swi < self.cfg_trail["dust_trigger_swi"]:
            if di >= self.cfg_global["dusty_threshold"]:
                return "dusty"
            return "dry"
            
        for level in self.cfg_global["grading"]["swi"]:
            if swi <= level["max"]:
                return level["label"]
        return "muddy"

    def _get_rsi_label(self, rsi:float) -> str:
        """获取硬质表面评级"""
        for level in self.cfg_global["grading"]["rsi"]:
            if rsi <= level["max"]:
                return level["label"]
        return "dangerous"

    def merging_scores_and_ai_labels(self, ai_swi_label: str, ai_rsi_label: str, swi: float, rsi: float, di: float) -> Tuple[str, str]:
        if _AI_WEIGHT <= 0.0:
            return ai_swi_label, ai_rsi_label
        ai_swi = GLOBAL_CONFIG["label_to_score"]["swi"][ai_swi_label][0]
        ai_rsi = GLOBAL_CONFIG["label_to_score"]["rsi"][ai_rsi_label][0]
        ai_di = GLOBAL_CONFIG["label_to_score"]["swi"][ai_swi_label][1]
        
        final_swi = (swi * (1 - _AI_WEIGHT)) + (ai_swi * _AI_WEIGHT) if abs(swi - ai_swi) < 3 else (swi * (1 - _AI_WEIGHT/2)) + (ai_swi * _AI_WEIGHT/2)
        final_rsi = (rsi * (1 - _AI_WEIGHT)) + (ai_rsi * _AI_WEIGHT) if abs(rsi - ai_rsi) < 3 else (rsi * (1 - _AI_WEIGHT/2)) + (ai_rsi * _AI_WEIGHT/2)
        final_di = (di * (1 - _AI_WEIGHT)) + (ai_di * _AI_WEIGHT) if abs(di - ai_di) < 5 else (di * (1 - _AI_WEIGHT/2)) + (ai_di * _AI_WEIGHT/2)
        
        final_swi_label = self._get_swi_label(final_swi, final_di)
        final_rsi_label = self._get_rsi_label(final_rsi)
        
        return final_swi_label, final_rsi_label

    def calculate(self) -> Tuple[float, float, str, str]:
        recent_rain = []

        # ==========================================
        # 第一阶段：历史状态时序推演 (按小时顺序)
        # ==========================================
        for hour in self.data:
            t = hour.get("temp", 0)
            h = hour.get("humidity", 0)
            c = hour.get("cloud", 0)
            p = hour.get("precip", 0)
            
            # 1. 动态保留系数 (E_t)
            e_t = (self.cfg_trail["evap_base"] 
                   - self.cfg_global["evap_temp_weight"] * (t - self.cfg_global["evap_temp_baseline"]) 
                   + self.cfg_global["evap_hum_weight"] * (h - self.cfg_global["evap_hum_baseline"]) 
                   + self.cfg_global["evap_cloud_weight"] * (c - self.cfg_global["evap_cloud_baseline"]))
            e_t = max(self.cfg_global["evap_min"], min(self.cfg_global["evap_max"], e_t))

            # 2. 土壤水分 (SWI)
            infiltrated_rain = min(p, self.cfg_trail["soil_i_max"])
            self.swi = (self.swi * e_t) + (infiltrated_rain / self.cfg_trail["swi_scale"] * 10)
            self.swi = min(self.cfg_global["max_score"], self.swi)

            # 3. 沙化指数 (DI)
            if self.swi < self.cfg_trail["dust_trigger_swi"]:
                heat_stress = max(0, t - self.cfg_global["dust_temp_baseline"])
                self.di += self.cfg_trail["dust_accum_rate"] * (1 + heat_stress)
                self.di = min(self.cfg_global["max_score"], self.di)
            else:
                self.di = 0.0

            # 4. 维护 RSI 降水滑动窗口
            recent_rain.append(p)
            if len(recent_rain) > self.cfg_trail["rsi_rain_lookback"]:
                recent_rain.pop(0)

            # 5. 【新增】：晨露与结露残留 (Dew Residue)
            if h >= self.cfg_trail.get("dew_trigger_humidity", 92.0):
                # 湿度达到露点边缘，硬质表面强制挂满水膜
                self.dew_residue = self.cfg_trail.get("dew_max_penalty", 4.0)
            else:
                # 湿度下降，露水开始按比例蒸发（脱离土壤，干得比 SWI 快）
                self.dew_residue *= self.cfg_trail.get("dew_decay_rate", 0.85)
            
        # ==========================================
        # 第二阶段：当前即时路况结算 (最终态)
        # ==========================================
        if not self.data:
            return 0.0, 0.0, "unknown", "unknown"
            
        current_hour = self.data[-1]
        current_precip = current_hour.get("precip", 0)
        
        # 6. 基础 RSI = 降水累积 + 历史残留的晨露
        rain_sum = sum(recent_rain)
        base_rsi = (rain_sum * self.cfg_trail["rsi_rain_weight"]) + self.dew_residue
        
        # 7. 即时降水绝对惩罚
        if current_precip >= self.cfg_trail.get("active_rain_threshold", 0.2):
            self.rsi = base_rsi + self.cfg_trail.get("active_rain_penalty", 5.0)
        else:
            self.rsi = base_rsi
            
        self.rsi = min(self.cfg_global["max_score"], self.rsi)

        swi_label = self._get_swi_label(self.swi, self.di)
        rsi_label = self._get_rsi_label(self.rsi)

        return round(self.swi, 1), round(self.rsi, 1), swi_label, rsi_label
