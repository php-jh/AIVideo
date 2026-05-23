"""
AI短剧生成器 - 启动器
双击exe自动激活video39环境并运行main.py
"""
import os
import sys
import subprocess


def get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main():
    current_dir = get_exe_dir()
    python_path = r"F:\opt\conad\envs\video39\python.exe"
    main_script = os.path.join(current_dir, "main.py")

    if not os.path.exists(python_path):
        print("错误: 找不到Python: " + python_path)
        input("按回车键退出...")
        return

    if not os.path.exists(main_script):
        print("错误: 找不到主程序: " + main_script)
        input("按回车键退出...")
        return

    print("正在启动 AI Short Drama Generator...")
    print("Python: " + python_path)
    print("程序: " + main_script)
    print()

    try:
        proc = subprocess.Popen(
            [python_path, main_script],
            cwd=current_dir,
        )
        proc.wait()
        if proc.returncode != 0:
            print("\n程序退出，返回码: " + str(proc.returncode))
            input("按回车键退出...")
    except Exception as e:
        print("\n启动失败: " + str(e))
        input("按回车键退出...")


if __name__ == "__main__":
    main()