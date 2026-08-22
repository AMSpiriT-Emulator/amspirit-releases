"""Setup script for amspirit_debug_gui (optional)."""

from setuptools import setup

setup(
    name="amspirit-debug-gui",
    version="1.14.0",
    description="Tkinter debug GUI for AMSpiriT-Lite emulator",
    author="AMSpiriT Community",
    url="https://github.com/keuperj/Amspirit",
    packages=["amspirit_debug_gui"],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "amspirit_debug_gui=amspirit_debug_gui.__main__:main",
        ],
    },
    extras_require={
        "dev": ["pytest", "black", "flake8"],
    },
)
