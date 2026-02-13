.PHONY: help install install-dev build clean test lint format uninstall docker-build docker-run

help:
	@echo "视频处理系统 - 可用命令:"
	@echo ""
	@echo "  make install       - 安装视频处理系统"
	@echo "  make install-dev   - 安装开发模式（包含测试工具）"
	@echo "  make build         - 构建安装包"
	@echo "  make clean         - 清理构建文件和缓存"
	@echo "  make test          - 运行测试"
	@echo "  make lint          - 代码检查"
	@echo "  make format        - 代码格式化"
	@echo "  make uninstall     - 卸载视频处理系统"
	@echo ""

install:
	pip install -e .
	mkdir -p data/input/mediasource data/output logs
	@if [ ! -f .env ]; then cp .env.example .env; echo "已创建 .env 文件，请编辑配置 API 密钥"; fi
	@echo "安装完成! 运行 'video-processor --help' 查看使用说明"

install-dev:
	pip install -e ".[dev]"
	mkdir -p data/input/mediasource data/output logs
	@if [ ! -f .env ]; then cp .env.example .env; fi
	@echo "开发模式安装完成!"

build:
	pip install build
	python -m build
	@echo "构建完成，安装包位于 dist/ 目录"

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf __pycache__ app/__pycache__ app/*/__pycache__
	rm -rf .pytest_cache .mypy_cache
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	@echo "清理完成"

test:
	python -m pytest tests/ -v

lint:
	flake8 app tests --max-line-length=100 --ignore=E501,W503
	@echo "代码检查完成"

format:
	black app tests --line-length=100
	@echo "代码格式化完成"

uninstall:
	pip uninstall video-processor -y
	@echo "卸载完成"
