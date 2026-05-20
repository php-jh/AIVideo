"""
AI短剧生成器 - 测试脚本
验证代码是否能正常运行
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试导入"""
    try:
        from logger import setup_logging
        logger = setup_logging()
        logger.info("日志系统导入成功")
        
        from config import load_config, save_config
        config = load_config()
        logger.info(f"配置导入成功，配置项数量: {len(config)}")
        
        from core.story_generator import StoryGenerator
        logger.info("StoryGenerator 导入成功")
        
        from core.image_generator import ImageGenerator
        logger.info("ImageGenerator 导入成功")
        
        from core.voice_generator import VoiceGenerator
        logger.info("VoiceGenerator 导入成功")
        
        from core.video_composer import VideoComposer
        logger.info("VideoComposer 导入成功")
        
        return True
    except Exception as e:
        print(f"导入测试失败: {e}")
        return False

def test_config():
    """测试配置"""
    try:
        from config import load_config, save_config, get_output_dir
        
        # 测试加载配置
        config = load_config()
        print(f"配置加载成功: {len(config)} 项")
        
        # 测试保存配置
        test_config = config.copy()
        test_config["test_key"] = "test_value"
        save_config(test_config)
        
        # 重新加载
        reloaded_config = load_config()
        if reloaded_config.get("test_key") == "test_value":
            print("配置保存和加载测试通过")
        else:
            print("配置保存和加载测试失败")
            return False
        
        # 测试输出目录
        output_dir = get_output_dir()
        print(f"输出目录: {output_dir}")
        
        return True
    except Exception as e:
        print(f"配置测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("开始测试 AI 短剧生成器...")
    print("=" * 50)
    
    # 测试导入
    print("\n1. 测试导入:")
    if test_imports():
        print("[OK] 导入测试通过")
    else:
        print("[FAIL] 导入测试失败")
        return
    
    # 测试配置
    print("\n2. 测试配置:")
    if test_config():
        print("[OK] 配置测试通过")
    else:
        print("[FAIL] 配置测试失败")
        return
    
    print("\n" + "=" * 50)
    print("所有测试通过！")
    print("\n可以运行主程序:")
    print("  python main.py")

if __name__ == "__main__":
    main()