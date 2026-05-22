import platform

_SYSTEM = platform.system()


def cjk_font(size: int = 10, bold: bool = False) -> tuple:
    if _SYSTEM == "Darwin":
        family = "PingFang TC"
    elif _SYSTEM == "Windows":
        family = "Microsoft JhengHei"
    else:
        family = "Noto Sans CJK TC"
    return (family, size, "bold") if bold else (family, size)


def is_macos() -> bool:
    return _SYSTEM == "Darwin"


def is_windows() -> bool:
    return _SYSTEM == "Windows"
