# China Economic RSS Filter

一个本地 Python 工具，从多个中国经济 RSS 源抓取文章，通过规则过滤 + LLM 分类，生成精选 RSS 订阅源，并通过 GitHub Pages 发布。

## 功能概述

- 从 Excel 表格（`config/rss_sources.xlsx`）管理 RSS 订阅源
- 自动抓取、提取正文、去重
- 关键词规则快速过滤
- LLM（Claude Haiku / GPT-4o-mini）精细分类（可选，无 API key 时纯规则模式）
- 生成 `output/daily_digest.md`、`output/selected_feed.xml`
- 发布到 `docs/` 目录，通过 GitHub Pages 提供 RSS 订阅 URL

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API key（可选）
```

### 3. 运行完整管道

```bash
python -m src.main run
```

首次运行时如果没有 `config/rss_sources.xlsx`，会自动生成模板文件 `config/rss_sources_template.xlsx`。
编辑模板，填入真实 RSS 源后，将文件重命名为 `rss_sources.xlsx`，再次运行即可。

## 命令说明

```bash
python -m src.main import-sources   # 从 Excel 导入 RSS 源，生成 feeds.yaml
python -m src.main fetch            # 抓取 RSS 文章
python -m src.main classify         # 规则过滤 + LLM 分类
python -m src.main digest           # 生成每日摘要 Markdown 和 CSV
python -m src.main feed             # 生成 selected_feed.xml
python -m src.main publish-assets   # 将产物拷贝到 docs/
python -m src.main run              # 以上所有步骤一键执行
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `output/daily_digest.md` | 按主题分组的每日精选文章摘要 |
| `output/selected_articles.csv` | 精选文章 CSV 表格 |
| `output/selected_feed.xml` | 精选 RSS 2.0 Feed |
| `docs/selected_feed.xml` | GitHub Pages 发布的 RSS Feed |
| `docs/index.html` | GitHub Pages 首页 |
| `docs/feed_info.json` | 构建元数据 |

## 通过 GitHub Pages 发布 RSS

### 发布步骤

1. 在 GitHub 上创建一个仓库，例如 `china-econ-rss-filter`。
2. 将本项目推送到 GitHub。
3. 打开仓库的 **Settings**。
4. 进入 **Pages** 页面。
5. 在 **Build and deployment** 下选择：
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/docs**
6. 点击 **Save**。
7. 等待 GitHub Pages 部署完成后，在 Folo 中订阅：

```
https://<github-username>.github.io/<repo-name>/selected_feed.xml
```

示例：

```
https://zhongzhonghu.github.io/china-econ-rss-filter/selected_feed.xml
```

### 初次推送 Git 命令

```bash
git init
git add .
git commit -m "Initial China economic RSS filter"
git branch -M main
git remote add origin https://github.com/<github-username>/<repo-name>.git
git push -u origin main
```

### 每次更新

```bash
python -m src.main run
git add output docs data
git commit -m "Update selected RSS feed"
git push
```

## 筛选逻辑

保留文章须满足：
- 中国相关性 ≥ 0.65
- 经济相关性 ≥ 0.60
- 噪声分 ≤ 0.40
- 专家观点或最新经济事实分 ≥ 0.60（或含专家观点/最新数据）

优先级分值公式：
```
priority_score =
  0.25 × 中国相关性
  + 0.20 × 经济相关性
  + 0.20 × 专家/事实分
  + 0.15 × 原创性
  + 0.10 × 来源质量
  + 0.10 × 时效性
  - 0.25 × 噪声分
```

## LLM 分类（tool-calling 模式）

使用 tool-calling（function calling）而非纯 JSON prompt，结构化输出更可靠。

推荐廉价模型：
- `claude-haiku-4-5-20251001`（Anthropic，约 $0.075/200篇）
- `gpt-4o-mini`（OpenAI，约 $0.045/200篇）

无 API key 时自动降级为纯本地规则模式，不影响基本运行。

## 项目结构

```
china-econ-rss-filter/
├── config/
│   ├── rss_sources.xlsx          # 用户维护的 RSS 源表（私有）
│   ├── rss_sources_template.xlsx # 自动生成的模板
│   ├── feeds.yaml                # 自动生成的 RSS 源配置
│   ├── topics.yaml               # 22 个主题分类
│   ├── filter_rules.yaml         # 关键词规则
│   └── source_whitelist/blacklist.yaml
├── data/
│   └── articles.sqlite           # 文章数据库
├── docs/                         # GitHub Pages 发布目录
│   ├── index.html
│   ├── selected_feed.xml
│   └── feed_info.json
├── output/                       # 生成产物
├── prompts/
│   └── classify_article.md       # LLM 分类提示词
├── src/                          # 源码
└── tests/                        # 测试
```
