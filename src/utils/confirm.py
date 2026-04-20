"""
人工确认工具：支持交互式 Enter 确认，非交互环境自动等待兜底
"""
import time


def wait_confirm(prompt: str = "操作完成后按 Enter 确认") -> bool:
    """
    等待人工确认。
    - 交互式环境：Enter=成功，输入 'failed'=失败
    - 非交互环境（VSCode / stdout 重定向）：自动等待 300s 后视为成功
    返回 True=成功，False=失败/跳过
    """
    print(f"\n{'='*60}")
    print(f"  {prompt}")
    print("  直接按 Enter=确认成功 | 输入 failed=标记失败 | 输入 skip=跳过")
    print('='*60)
    try:
        user_input = input("  > ").strip().lower()
        if user_input == "failed":
            return False
        if user_input == "skip":
            return False
        return True
    except EOFError:
        # 非交互环境（VSCode 等）：固定等待后自动标记失败
        wait_secs = 1200
        print(f"  [非交互模式] 等待 {wait_secs}s，超时后自动标记失败...")
        for remaining in range(wait_secs, 0, -30):
            print(f"  剩余: {remaining}s", flush=True)
            time.sleep(30)
        return False
