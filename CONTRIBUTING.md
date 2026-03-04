# Contributing to Agent Reach

Thank you for your interest in contributing to Agent Reach! This document provides guidelines and instructions for contributing.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a new branch for your contribution
4. Make your changes
5. Run tests and linting
6. Submit a pull request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Agent-Reach.git
cd Agent-Reach

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks (optional but recommended)
pre-commit install
```

## Code Style

We use the following tools to maintain code quality:

- **ruff**: Linting and import sorting
- **mypy**: Type checking
- **pytest**: Testing

Run all checks before submitting a PR:

```bash
# Linting
ruff check agent_reach tests
ruff format agent_reach tests

# Type checking
mypy agent_reach

# Tests
pytest
```

## Adding New Channels

Agent Reach uses a unified channel interface. To add a new platform:

1. Create a new file in `agent_reach/channels/`
2. Implement the channel contract (see existing channels for examples)
3. Add tests in `tests/test_channels.py`
4. Update `agent_reach/doctor.py` to include the new channel
5. Update documentation

## Pull Request Guidelines

- **Small, focused changes** are preferred over large refactors
- Include tests for new functionality
- Update documentation if needed
- Follow existing code style
- Reference any related issues

## Reporting Issues

When reporting bugs, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Any error messages

## Questions?

Feel free to open an issue for questions or join discussions.

---

感谢您对 Agent Reach 的贡献！本文档提供了贡献指南。

## 快速开始

1. 在 GitHub 上 fork 仓库
2. 本地 clone 您的 fork
3. 创建新分支
4. 提交更改
5. 运行测试和 lint
6. 提交 pull request

## 代码规范

- 使用 **ruff** 进行代码检查
- 使用 **mypy** 进行类型检查
- 使用 **pytest** 运行测试

## 添加新渠道

1. 在 `agent_reach/channels/` 创建新文件
2. 实现渠道接口
3. 添加测试
4. 更新 doctor 检测
5. 更新文档
