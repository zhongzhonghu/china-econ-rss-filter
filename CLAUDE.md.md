# CLAUDE.md

## Project: China Economic RSS Filter

This is a Windows-based local Python project for filtering Chinese economic RSS / WeChat RSS articles and publishing a curated RSS feed through GitHub Pages.

Expected project root:

```text
D:\Claude\china-econ-rss-filter
```

Claude Code must work inside this project folder only. Do not create files directly under `D:\Claude`.

---

## 1. Core Objective

The user maintains an **RSS subscription Excel table**. This Excel file is the master source list.

The system should:

```text
config/rss_sources.xlsx
→ validate RSS sources
→ generate config/feeds.yaml
→ fetch RSS articles
→ extract article text
→ remove duplicates
→ apply rule-based filtering
→ classify candidate articles with LLM/API
→ score and rank articles
→ store results in SQLite
→ generate output/daily_digest.md
→ generate output/selected_feed.xml
→ copy selected_feed.xml to docs/selected_feed.xml
→ publish through GitHub Pages
→ subscribe in Folo using the GitHub Pages URL
```

The final selected RSS feed should contain only articles that are:

1. related to China;
2. related to economics, finance, policy, industry, trade, markets, or industrial structure;
3. original or high-quality enough;
4. contain expert viewpoints or latest economic facts;
5. not advertisements, stock-promotion articles, emotional commentary, or low-quality reposts.

---

## 2. First Working Goal

Make this command work:

```bash
python -m src.main run
```

It should run the full pipeline:

```text
import-sources → fetch → classify → digest → feed → publish-assets
```

The command should generate:

```text
output/daily_digest.md
output/selected_articles.csv
output/selected_feed.xml
docs/selected_feed.xml
docs/index.html
```

`docs/selected_feed.xml` is the file to be published by GitHub Pages.

---

## 3. GitHub Pages Publishing Requirement

The project must support publishing the curated RSS feed as a static GitHub Pages file.

### 3.1 Public RSS URL Pattern

After GitHub Pages is enabled, the final RSS URL should look like:

```text
https://<github-username>.github.io/<repo-name>/selected_feed.xml
```

Example:

```text
https://zhongzhonghu.github.io/china-econ-rss-filter/selected_feed.xml
```

This URL can be subscribed to in Folo, Feedly, Inoreader, FreshRSS, Miniflux, or any standard RSS reader.

### 3.2 Static Publishing Directory

Use this directory for GitHub Pages:

```text
docs/
```

The system should copy RSS output to:

```text
docs/selected_feed.xml
```

Also create a simple page:

```text
docs/index.html
```

The page should show:

- project name;
- latest build time;
- a link to `selected_feed.xml`;
- a short explanation that this is a curated China economic RSS feed.

### 3.3 Required Command

Implement:

```bash
python -m src.main publish-assets
```

This command should:

1. create `docs/` if it does not exist;
2. copy `output/selected_feed.xml` to `docs/selected_feed.xml`;
3. create or update `docs/index.html`;
4. create or update `docs/feed_info.json` with latest build metadata;
5. not require any server backend.

### 3.4 README GitHub Pages Instructions

The README must explain how to publish the feed through GitHub Pages:

```text
1. Create a GitHub repository, for example china-econ-rss-filter.
2. Push this project to GitHub.
3. Open GitHub repository Settings.
4. Go to Pages.
5. Under Build and deployment, choose:
   Source: Deploy from a branch
   Branch: main
   Folder: /docs
6. Save.
7. After GitHub Pages is deployed, subscribe in Folo to:
   https://<github-username>.github.io/<repo-name>/selected_feed.xml
```

### 3.5 Git Commands for User

The README should include these commands:

```bash
git init
git add .
git commit -m "Initial China economic RSS filter"
git branch -M main
git remote add origin https://github.com/<github-username>/<repo-name>.git
git push -u origin main
```

For later updates:

```bash
python -m src.main run
git add output docs data
git commit -m "Update selected RSS feed"
git push
```

Do not hard-code the user's GitHub username or repo name in Python code.

---

## 4. RSS Source Management Through Excel

### 4.1 Master Source File

The RSS source list should be maintained in:

```text
config/rss_sources.xlsx
```

This Excel file is the user's main editing interface.

Claude Code should implement an importer:

```text
src/excel_importer.py
```

The importer should read the Excel table and generate:

```text
config/feeds.yaml
output/rss_sources_validation.md
```

The pipeline should read RSS sources from `config/feeds.yaml`.

---

### 4.2 Required Excel Sheet and Columns

The Excel workbook should contain a sheet named:

```text
sources
```

Required columns:

```text
enabled
source_id
source_name
rss_url
source_type
source_quality_score
language
region_scope
primary_topic_hint
notes
```

Column meanings:

| Column | Meaning | Example |
|---|---|---|
| `enabled` | Whether this source should be used. Accept `1`, `0`, `TRUE`, `FALSE`, `yes`, `no` | `1` |
| `source_id` | Stable machine-readable source ID | `cf40` |
| `source_name` | Human-readable source name | `中国金融四十人论坛` |
| `rss_url` | RSS feed URL | `https://example.com/feed.xml` |
| `source_type` | Source type | `official`, `media`, `think_tank`, `sell_side`, `wechat`, `academic`, `industry`, `unknown` |
| `source_quality_score` | Source quality score from 0 to 1 | `0.85` |
| `language` | Main language | `zh`, `en`, `mixed` |
| `region_scope` | Geographic focus | `china`, `global_with_china`, `global`, `overseas_only` |
| `primary_topic_hint` | Optional default topic hint | `T03` |
| `notes` | User notes | `宏观政策与金融市场` |

---

### 4.3 Optional Excel Columns

Support optional columns if present:

```text
wechat_account
rss_provider
original_homepage
update_frequency
paywall_status
requires_fulltext
include_keywords
exclude_keywords
topic_hints
priority_group
owner_notes
```

Column meanings:

| Column | Meaning |
|---|---|
| `wechat_account` | WeChat public account name if applicable |
| `rss_provider` | `rsshub`, `wechat2rss`, `wewe-rss`, `official`, `manual`, `unknown` |
| `original_homepage` | Official homepage or account page |
| `update_frequency` | `daily`, `weekly`, `irregular`, etc. |
| `paywall_status` | `free`, `partial`, `paid`, `unknown` |
| `requires_fulltext` | Whether full-text extraction is important |
| `include_keywords` | Source-specific include keywords, separated by comma or semicolon |
| `exclude_keywords` | Source-specific exclude keywords, separated by comma or semicolon |
| `topic_hints` | Multiple topic IDs, such as `T03;T17;T21` |
| `priority_group` | `core`, `normal`, `experimental` |
| `owner_notes` | Additional user notes |

---

### 4.4 Excel Validation Rules

Validation requirements:

1. `rss_url` must not be empty for enabled rows.
2. `source_name` must not be empty for enabled rows.
3. `source_quality_score` must be converted to a float between 0 and 1.
4. `primary_topic_hint`, if provided, must be one of `T01` to `T22`.
5. `topic_hints`, if provided, must only contain `T01` to `T22`.
6. Duplicate `rss_url` rows should be deduplicated.
7. Duplicate `source_id` rows should produce a warning.
8. Disabled rows should be ignored but not deleted.
9. Invalid enabled rows should be skipped with a clear warning.
10. The importer should write a validation report:

```text
output/rss_sources_validation.md
```

If `config/rss_sources.xlsx` does not exist, create:

```text
config/rss_sources_template.xlsx
config/feeds.yaml
```

The template should contain the required columns and a few placeholder example rows.

---

## 5. Generated feeds.yaml Format

After reading Excel, generate:

```text
config/feeds.yaml
```

Expected format:

```yaml
feeds:
  - source_id: cf40
    name: 中国金融四十人论坛
    url: https://example.com/feed.xml
    source_type: think_tank
    source_quality_score: 0.85
    language: zh
    region_scope: china
    primary_topic_hint: T03
    topic_hints:
      - T03
      - T17
    rss_provider: rsshub
    enabled: true
    notes: 宏观政策与金融市场
```

---

## 6. Required Commands

Implement in `src/main.py`:

```bash
python -m src.main import-sources
python -m src.main fetch
python -m src.main classify
python -m src.main digest
python -m src.main feed
python -m src.main publish-assets
python -m src.main run
```

### `import-sources`

- Read `config/rss_sources.xlsx`.
- Validate source rows.
- Generate `config/feeds.yaml`.
- Generate `output/rss_sources_validation.md`.
- If Excel does not exist, create `config/rss_sources_template.xlsx` and sample `config/feeds.yaml`.

### `fetch`

- Read `config/feeds.yaml`.
- Fetch RSS entries.
- Extract article text.
- Store new articles in SQLite.

### `classify`

- Select unclassified articles.
- Run local rule filter.
- Send candidates to LLM if API key is available.
- Store LLM JSON.
- Compute final score.
- If no API key is available, still run local filters and generate local-rule-based outputs.

### `digest`

- Generate `output/daily_digest.md`.
- Export `output/selected_articles.csv`.
- Group kept articles by topic.
- Sort by priority score.

### `feed`

- Generate `output/selected_feed.xml`.
- The feed must be valid RSS 2.0.
- The feed should be readable by Folo and other standard RSS readers.

### `publish-assets`

- Copy `output/selected_feed.xml` to `docs/selected_feed.xml`.
- Generate `docs/index.html`.
- Generate `docs/feed_info.json`.

### `run`

Run:

```text
import-sources → fetch → classify → digest → feed → publish-assets
```

---

## 7. Project Structure

Create this structure:

```text
china-econ-rss-filter/
│
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   ├── rss_sources.xlsx
│   ├── rss_sources_template.xlsx
│   ├── feeds.yaml
│   ├── topics.yaml
│   ├── source_whitelist.yaml
│   ├── source_blacklist.yaml
│   └── filter_rules.yaml
│
├── data/
│   └── articles.sqlite
│
├── output/
│   ├── rss_sources_validation.md
│   ├── daily_digest.md
│   ├── selected_articles.csv
│   └── selected_feed.xml
│
├── docs/
│   ├── index.html
│   ├── feed_info.json
│   └── selected_feed.xml
│
├── prompts/
│   └── classify_article.md
│
├── src/
│   ├── __init__.py
│   ├── config_loader.py
│   ├── excel_importer.py
│   ├── database.py
│   ├── fetch_feeds.py
│   ├── extract_article.py
│   ├── deduplicate.py
│   ├── rule_filter.py
│   ├── llm_classifier.py
│   ├── scoring.py
│   ├── digest_generator.py
│   ├── rss_feed_generator.py
│   ├── publish_assets.py
│   └── main.py
│
└── tests/
    ├── test_excel_importer.py
    ├── test_rule_filter.py
    ├── test_scoring.py
    ├── test_deduplicate.py
    └── test_rss_feed_generator.py
```

---

## 8. Topic Taxonomy

Create `config/topics.yaml` with these topic IDs.

Each kept article must have one `primary_topic` and zero or more `secondary_topics`.

```yaml
T01: 宏观增长、GDP、周期、PMI
T02: 财政政策、税收、赤字、专项债
T03: 货币政策、社融、信贷、利率
T04: 人民币汇率、资本流动、外储
T05: 房地产、土地财政、城投债
T06: 地方政府债务与财政可持续性
T07: 外贸、出口、关税、全球供应链
T08: 产业政策、产能过剩、反内卷
T09: 制造业升级、工业企业利润
T10: 光伏、新能源、储能
T11: 电动车、汽车出口、智能制造
T12: 半导体、AI、数字经济
T13: 钢铁、化工、有色、传统工业
T14: 消费、收入、就业、居民资产负债表
T15: 人口、教育、医疗、长期增长
T16: 通胀、PPI、CPI、价格体系
T17: 金融市场、股市、债市、银行
T18: 民营经济、平台经济、企业信心
T19: 国企改革、央企、地方国资
T20: 区域经济、城市群、园区、地方竞争
T21: 国际政治经济、制裁、地缘风险
T22: 数据、方法、统计口径、研究报告
```

Do not invent new topic IDs unless the user explicitly requests it.

---

## 9. Filtering Logic

### 9.1 Final Keep Rule

Keep an article if:

```text
china_relevance_score >= 0.65
AND economic_relevance_score >= 0.60
AND noise_score <= 0.40
AND (
    expert_or_fact_score >= 0.60
    OR has_expert_opinion == true
    OR has_latest_economic_fact == true
)
```

### 9.2 Priority Score

Use:

```text
priority_score =
0.25 * china_relevance_score
+ 0.20 * economic_relevance_score
+ 0.20 * expert_or_fact_score
+ 0.15 * originality_score
+ 0.10 * source_quality_score
+ 0.10 * freshness_score
- 0.25 * noise_score
```

Clamp the final value to `[0, 1]`.

### 9.3 Priority Level

```text
score >= 0.75          High
0.55 <= score < 0.75   Medium
score < 0.55           Low
```

The daily digest should normally include High and selected Medium articles.

---

## 10. Local Keyword Rules

Create `config/filter_rules.yaml`.

```yaml
china_keywords:
  - 中国
  - 我国
  - 国内
  - 内地
  - 大陆
  - 人民币
  - 央行
  - 财政部
  - 发改委
  - 商务部
  - 海关总署
  - 国家统计局
  - A股
  - 港股
  - 地方政府
  - 中国企业
  - 中资
  - 出口
  - 进口
  - 社融
  - CPI
  - PPI
  - PMI
  - 房地产
  - 城投
  - 专项债
  - 民营经济
  - 国企

economic_keywords:
  - GDP
  - PMI
  - CPI
  - PPI
  - 社融
  - 信贷
  - 财政
  - 货币政策
  - 税收
  - 地方债
  - 专项债
  - 房地产
  - 出口
  - 进口
  - 汇率
  - 利率
  - 通胀
  - 通缩
  - 就业
  - 收入
  - 消费
  - 投资
  - 产能
  - 价格
  - 利润
  - 制造业
  - 产业链
  - 供应链
  - 关税
  - 贸易
  - 金融市场
  - 银行
  - 债券
  - 股票
  - 企业盈利

originality_keywords:
  - 原创
  - 首发
  - 独家
  - 专访
  - 本文作者
  - 作者系
  - 课题组
  - 研究报告
  - 调研
  - 深度
  - 访谈
  - 圆桌
  - 演讲实录

repost_keywords:
  - 转载自
  - 转自
  - 来源：
  - 摘编自
  - 综合自
  - 本文转载
  - 原文刊发于
  - 版权归原作者所有
  - 如有侵权请联系删除

noise_keywords:
  - 荐股
  - 牛股
  - 涨停
  - 内幕
  - 暴涨
  - 抄底
  - 财富自由
  - 训练营
  - 课程
  - 直播课
  - 社群
  - 扫码入群
  - 免费领取
  - 带货
  - 广告
  - 软文
```

---

## 11. LLM Classification Schema

The LLM classifier must return JSON compatible with this structure:

```json
{
  "keep": true,
  "primary_topic": "T08",
  "secondary_topics": ["T10", "T07"],
  "china_relevance_score": 0.92,
  "economic_relevance_score": 0.88,
  "originality_score": 0.74,
  "expert_or_fact_score": 0.81,
  "source_quality_score": 0.75,
  "freshness_score": 0.90,
  "noise_score": 0.12,
  "has_expert_opinion": true,
  "has_latest_economic_fact": true,
  "expert_names": ["string"],
  "institutions": ["string"],
  "key_facts": ["string"],
  "expert_viewpoints": ["string"],
  "summary": "string",
  "reason_for_keep_or_reject": "string"
}
```

Rules:

1. Scores must be floats between 0 and 1.
2. `primary_topic` must be one of `T01` to `T22`.
3. `secondary_topics` must only contain `T01` to `T22`.
4. `keep` must be boolean.
5. Output must be valid JSON only.
6. Do not include Markdown in the API output.

---

## 12. Classification Prompt

Create `prompts/classify_article.md`:

```text
你是一个中国经济信息筛选系统。请根据文章标题、来源、作者、发布时间、摘要和正文，判断这篇文章是否应该被保留。

保留标准：
1. 必须与中国经济、中国政策、中国企业、中国市场或中国外部经济关系有关。
2. 必须具有经济、金融、产业、贸易、财政、消费、就业、房地产、科技产业等实质内容。
3. 优先保留原创文章、首发文章、深度分析、专家观点、机构研究、官方数据解读。
4. 如果只是转载、摘编、标题党、课程广告、荐股、情绪化评论，应降低优先级或剔除。
5. 如果文章包含最新经济事实、官方数据、政策变化、企业经营事实或行业价格变化，应提高优先级。
6. 请从 22 个主题中选择一个主主题，可以选择多个副主题。
7. 必须返回严格 JSON，不要输出额外解释。

特别注意：
- 不要因为文章提到“中国”就自动保留。必须有实质经济内容。
- 不要因为文章来自知名账号就自动保留。仍需判断内容质量。
- 如果是海外经济文章，但直接影响中国贸易、供应链、汇率、产业竞争或地缘经济风险，可以保留。
- 如果文章只是观点情绪，没有事实、机制或专家分析，应降低评分。
```

---

## 13. Database Schema

Use SQLite for MVP.

Create table `articles`:

```sql
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    canonical_url TEXT,
    title TEXT,
    source_id TEXT,
    source TEXT,
    source_type TEXT,
    source_quality_score REAL,
    author TEXT,
    published_at TEXT,
    fetched_at TEXT,
    rss_summary TEXT,
    raw_text TEXT,
    cleaned_text TEXT,
    content_hash TEXT,
    title_hash TEXT,
    extraction_status TEXT,
    rule_keep INTEGER,
    rule_reject_reason TEXT,
    llm_result_json TEXT,
    final_keep INTEGER,
    final_priority_score REAL,
    priority_level TEXT,
    primary_topic TEXT,
    secondary_topics TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Create table `runs`:

```sql
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    total_fetched INTEGER,
    total_new INTEGER,
    total_rule_candidates INTEGER,
    total_llm_classified INTEGER,
    total_kept INTEGER,
    notes TEXT
);
```

---

## 14. selected_feed.xml Requirements

Generate:

```text
output/selected_feed.xml
docs/selected_feed.xml
```

The XML must be valid RSS 2.0.

Each `<item>` should include:

- `<title>`
- `<link>`
- `<guid>`
- `<pubDate>`
- `<source>`
- one or more `<category>`
- `<description>` wrapped in CDATA

The description should include:

- priority level and score;
- source;
- primary topic;
- secondary topics;
- reason for keeping;
- key facts;
- expert viewpoints;
- summary.

Example item:

```xml
<item>
  <title>Article title</title>
  <link>https://example.com/article</link>
  <guid isPermaLink="false">article-content-hash</guid>
  <pubDate>Sun, 24 May 2026 09:15:00 +0800</pubDate>
  <source>Source Name</source>
  <category>T03 货币政策、社融、信贷、利率</category>
  <description><![CDATA[
    <p><strong>Priority:</strong> High, score: 0.86</p>
    <p><strong>Why keep:</strong> Contains latest policy data and expert interpretation.</p>
    <p><strong>Summary:</strong> Short summary here.</p>
  ]]></description>
</item>
```

Limit the feed to the latest 100 selected articles.

Sort by `published_at` descending.

Escape XML special characters correctly.

---

## 15. Environment Variables

Create `.env.example`:

```text
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
MAX_ARTICLES_PER_RUN=200
MAX_ARTICLE_CHARS_FOR_LLM=12000
DATABASE_PATH=data/articles.sqlite
PUBLIC_FEED_BASE_URL=
```

`PUBLIC_FEED_BASE_URL` is optional and can later be set to:

```text
https://<github-username>.github.io/<repo-name>
```

Do not hard-code API keys or GitHub usernames.

---

## 16. Recommended Packages

Create `requirements.txt` with:

```text
feedparser
requests
beautifulsoup4
readability-lxml
trafilatura
pyyaml
python-dotenv
pydantic
openai
pandas
openpyxl
rapidfuzz
pytest
```

Use standard `sqlite3` unless there is a strong reason to add another database package.

---

## 17. Error Handling

1. If `rss_sources.xlsx` is missing, create a template and sample feeds.
2. If one RSS feed fails, log the error and continue.
3. If one article extraction fails, use RSS summary as fallback.
4. If LLM API fails, mark the article as pending and continue.
5. If LLM JSON is invalid, retry once.
6. If still invalid, store the error and continue.
7. If no articles are kept, still generate valid `daily_digest.md` and `selected_feed.xml`.
8. Never crash the whole run because of one bad feed or one bad article.

---

## 18. Do Not Do

Do not:

1. build a dashboard in MVP;
2. use Docker in MVP;
3. add Supabase in MVP;
4. delete raw data;
5. store API keys in code;
6. hard-code Windows absolute paths inside Python modules;
7. hard-code GitHub username or repo name;
8. classify all articles with LLM before local filtering;
9. use free-form LLM prose as classification data;
10. create files outside the project root;
11. invent new topics unless requested.

---

## 19. Acceptance Criteria

The MVP is complete when:

1. `python -m src.main run` works.
2. `config/rss_sources.xlsx` or `config/rss_sources_template.xlsx` exists.
3. `config/feeds.yaml` is generated from Excel or sample data.
4. SQLite database is created automatically.
5. Duplicate URLs are not inserted twice.
6. Rule-based filtering works.
7. LLM classification works when API key is configured.
8. The project still works without API key using only local filters.
9. `output/daily_digest.md` is generated.
10. `output/selected_feed.xml` is generated.
11. `docs/selected_feed.xml` is generated for GitHub Pages.
12. `docs/index.html` is generated.
13. README explains how to enable GitHub Pages and subscribe in Folo.
14. Each selected article has a clear keep reason.
15. The code is modular enough to modify feeds, topics, thresholds, and publishing behavior later.

---

## 20. First Task for Claude Code

Read this file carefully.

Then create the project skeleton and implement the first working MVP.

Start with the local command:

```bash
python -m src.main run
```

Then ensure the GitHub Pages assets exist:

```text
docs/index.html
docs/selected_feed.xml
docs/feed_info.json
```

The priority is a working local-to-GitHub-Pages RSS pipeline, not a perfect classifier.
