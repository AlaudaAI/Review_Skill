# Google Reviews Boost - 产品方案与实施计划

## 产品概述

帮助本地商户（SMB）提升 Google Reviews 数量和质量的工具。核心流程：商户提供客户联系方式 → 系统生成个性化短链接 → 客户点击链接后自动跳转 Google Maps 并预填评价内容 → 客户一键粘贴提交。

---

## 系统架构（保持最简）

```
Frontend (React SPA)          Backend (Node/Express or Python/FastAPI)
  ├── 商户 Portal                ├── API
  │   ├── 登录                   │   ├── POST /api/biz          (创建商户)
  │   ├── 发送 Review 请求       │   ├── POST /api/reviews/send  (发送链接)
  │   └── Dashboard              │   ├── GET  /api/reviews/stats  (统计)
  │                              │   └── GET  /r/:code            (短链接跳转)
  └── 客户 Landing Page          │
      └── 跳转+剪贴板逻辑        ├── Services
                                 │   ├── Link Generator (短链接)
                                 │   ├── Message Generator (LLM 生成评价文本)
                                 │   ├── Email Sender (SendGrid/SES)
                                 │   └── SMS Sender (Twilio)
                                 │
                                 └── DB (SQLite → PostgreSQL)
```

---

## Phase 1: Core MVP（现在实现）

目标：**一个可用的端到端产品，商户可以自助发送 review 请求并追踪结果。**

### 1.1 数据模型（3 张表，够用）

| 表 | 字段 |
|---|---|
| `business` | id, name, google_maps_url, created_at |
| `review_request` | id, business_id, customer_name, customer_contact (email/phone), contact_type (email/sms), short_code, review_text, status (pending/sent/clicked/completed), created_at, sent_at, clicked_at |
| `short_link` | 不需要单独表，short_code 直接放在 review_request 里 |

status 流转: `pending → sent → clicked → (completed 暂时无法准确追踪)`

> 注意：Google 不提供 webhook 通知评论是否提交成功，所以 `clicked` 是我们能追踪到的最后状态。后续可通过 Google Business Profile API 定期拉取新评论来粗略匹配。

### 1.2 后端 API

| 端点 | 功能 |
|---|---|
| `POST /api/business` | 创建/更新商户信息（name + google_maps_url） |
| `POST /api/reviews/send` | 接收 customer_name, contact, contact_type → 生成 review_text + short_code → 发送 email/SMS |
| `GET /r/:code` | 短链接跳转：记录 clicked 状态 → 返回 landing page |
| `GET /api/reviews/stats?business_id=x` | 返回该商户的发送/点击统计 |

### 1.3 短链接 + Landing Page（核心体验）

- 短链接用 nanoid 生成 6-8 位 code，存在 review_request 表里
- `GET /r/:code` 返回一个轻量 HTML 页面（不需要 SPA）：
  - 自动将预生成的 review_text 写入剪贴板（`navigator.clipboard.writeText`）
  - 显示简短提示："评价内容已复制到剪贴板，正在跳转 Google Maps..."
  - 2 秒后 `window.location.href` 跳转到商户的 Google Maps 评价页面
  - 页面上显示步骤说明（点击 5 星 → 粘贴 → 提交）

### 1.4 Review 文本生成

- MVP 阶段：用简单模板 + 少量变体，不需要 LLM
  - 模板示例：`"Had a wonderful experience at {biz_name}! The service was great and I'd definitely recommend it to friends."`
  - 准备 5-10 个模板，随机选择，替换变量
- 后续：接入 LLM（GPT/Claude）根据商户类型、特色生成更自然的文本

### 1.5 发送渠道

- **Email**：用 SendGrid 或 AWS SES，MVP 先支持 Email
- **SMS**：用 Twilio，MVP 也支持（因为 SMS 打开率远高于 Email，是核心场景）
- 消息内容：简短文案 + 短链接

### 1.6 商户 Portal UI（保持极简）

只需 3 个页面：

1. **设置页**：输入商户名称 + Google Maps 链接
2. **发送页**：输入客户姓名 + email/手机号 → 点击发送（也支持批量 CSV 上传）
3. **Dashboard 页**：
   - 总览：已发送 / 已点击 / 点击率
   - 列表：每条 review request 的状态（pending/sent/clicked + 时间戳）

> 不需要登录系统。MVP 阶段用简单的 URL token 或 basic auth 保护即可。

### 1.7 技术选型建议

| 层 | 选型 | 理由 |
|---|---|---|
| Backend | **Python + FastAPI** 或 **Node + Express** | 快速开发，MVP 够用 |
| Frontend | **React (Vite)** | 简单 SPA，3 个页面 |
| DB | **SQLite** | 零运维，MVP 数据量小，后续迁移 PostgreSQL |
| Email | **SendGrid** | 免费额度够 MVP |
| SMS | **Twilio** | 行业标准 |
| 部署 | **单机部署 (VPS/Railway/Fly.io)** | 前后端同一个服务 |

---

## Phase 2: 产品完善（MVP 验证后）

| 功能 | 说明 |
|---|---|
| LLM 生成评价文本 | 根据商户类型/特色，用 LLM 生成更自然多样的评价文本 |
| 商户自定义消息 | 商户可以配置希望客户提到的关键词（如 "鸡尾酒很棒"、"氛围好"） |
| 嵌入小礼物激励 | 在 landing page 显示 "感谢评价！下次到店出示可获得 [免费饮品]" |
| 客户来源集成 | 对接 Resy / Toast / Square 等平台，自动获取客户联系方式 |
| 认证 & 多商户 | 正式的登录系统，支持多商户独立管理 |
| 评价完成追踪 | 通过 Google Business Profile API 定期拉取新评论，与 review_request 粗略匹配 |

## Phase 3: 规模化（有付费客户后）

| 功能 | 说明 |
|---|---|
| 自动化定期发送 | 商户设置规则，系统自动给新客户发送 review 请求 |
| 商户报告 | 定期邮件给商户，汇报 review 增长情况 |
| A/B 测试 | 不同消息模板/发送时间的效果对比 |
| 白标 | 允许商户自定义品牌 |
| Negative review 拦截 | 先问客户体验如何，差评引导到私下反馈而非 Google |

---

## MVP 实施顺序

```
Step 1: 项目初始化 + 数据模型 + 基础 API
Step 2: 短链接 + Landing Page（核心体验，可以先手动测试）
Step 3: Email/SMS 发送
Step 4: 商户 Portal UI（设置 + 发送 + Dashboard）
Step 5: 端到端测试 + 部署
```

---

## 关键决策点

1. **tech stack 选型**：Python/FastAPI vs Node/Express？（建议根据团队熟悉度选择）
2. **是否需要视频教程给 reviewer？** → 建议 MVP 不做，landing page 上 3 步文字说明够用。如果点击率低再考虑加视频。
3. **短链接域名**：是否需要自定义短域名？MVP 用主域名的 `/r/:code` 路径即可。
