"""
视频处理系统 - 兼容旧版本 pip 的安装配置
推荐使用 pyproject.toml 进行安装
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("app/requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="video-processor",
    version="1.1.0",
    author="Video Processor Team",
    description="智能视频内容分析和剪辑系统，支持语音识别、AI分析和自动剪辑",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/video-processor",
    packages=find_packages(include=["app*", "src*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Video",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "video-processor=app.main:main",
            "vp=app.main:main",
            "video-server=app.services.http_server:start_server",
            "video-ws-server=app.services.websocket_server:start_server",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.txt", "*.md", "*.json", ".env.example"],
    },
)
