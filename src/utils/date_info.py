from datetime import datetime
import holidays

class DateInfo:
    """日期信息处理类，提供星期和节假日查询功能"""
    
    def __init__(self):
        """初始化中国节假日数据库"""
        self.cn_holidays = holidays.China()
    
    def get_weekday(self):
        """获取当前星期信息
        Returns:
            str: 中文格式的星期表示（如星期一）
        """
        weekdays = ["星期一", "星期二", "星期三", 
                   "星期四", "星期五", "星期六", "星期日"]
        return weekdays[datetime.now().weekday()]
    
    def check_holiday(self):
        """检查当前日期是否为节假日
        Returns:
            tuple: (是否节假日, 节日名称)
        """
        today = datetime.now().date()
        if today in self.cn_holidays:
            return True, self.cn_holidays.get(today)
        return False, "非节假日"