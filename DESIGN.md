# DESIGN.md (Unified Standard Design System Source of Truth)

본 문서는 **Light SaaS 대시보드(Edaca Style)**와 **Dark/Glassmorphism 시스템**의 장점을 통합한 전역 표준 디자인 토큰 및 웹앱 개발 디자인 시스템 지침이다.

---

## 0. Source of Truth & Fallback Rules (소스 탐색 및 폴백 수칙)

### 디자인 소스 탐색 우선순위
UI/디자인 작업 관련 요청 수신 시, 코딩 개시 전 아래 순서로 `DESIGN.md` 존재 여부를 탐색하고 **반드시 먼저 읽은 후** 작업을 시작해야 한다:

1. **1순위 (프로젝트 지침)**: 현재 작업 프로젝트 루트 디렉터리의 `DESIGN.md`
2. **2순위 (사용자 전역 지침)**: 사용자 전역 설정 디렉터리 (`%USERPROFILE%\.codex\DESIGN.md` 또는 `%USERPROFILE%\OneDrive\workspace\DESIGN.md`)

### 적용 및 폴백 수칙
- **DESIGN.md 탐색 필수화**: 디자인 관련 키워드("디자인", "UI", "화면", "페이지", "레이아웃", "컴포넌트", "스타일", "폰트" 등) 포함 요청 시 `DESIGN.md` 읽기를 선행한다.
- **모든 경로에 DESIGN.md 미존재 시**: 임의의 색상/폰트/여백 생성을 엄격히 금지하며, 임의 구현을 멈추고 사용자에게 프로젝트 디자인 토큰 또는 기준 가이드 확정을 즉시 요청한다.
- **요청과 DESIGN.md 충돌 시**: 충돌되는 항목과 디자인 트레이드오프를 사용자에게 명확히 설명하고 진행 방향 확인 절차를 거친 후 진행한다.

---

## 1. Design Principles (디자인 원칙)

- **Dual-Theme Elegance (Light & Dark)**: 맑고 정갈한 **Clean Light Theme**를 기본값으로 하되, 동일한 토큰 체계로 **Dark / Glassmorphic Theme** 전환(`[data-theme="dark"]`)을 완벽하게 지원한다.
- **Electric Royal & Indigo Signature**: 시그니처 포인트 컬러로 **Electric Royal Blue (`#0066FF`)**와 **Indigo (`#6366F1`)**를 사용한다. 범용 순색(기본 Red/Blue/Green)의 직접 사용을 철저히 금지한다.
- **Floating Surface & Soft Radii**: 모든 카드와 모달은 **16px~20px의 넉넉한 곡률(Radius)**과 부드러운 **엘리베이션 쉐도우**를 부여하여 입체감과 깊이감을 연출한다.
- **Pill Controls & Micro-interactions**: 버튼, 뱃지, 상태 표시기는 **Pill (9999px)** 형식을 다수 적용하며, 호버 업(`translateY(-2px)`), 눌림 효과(`scale(0.97)`), 부드러운 트랜지션(`0.2s cubic-bezier`)을 보장한다.
- **Multi-Color Visual Analytics**: 차트 시각화에는 맑은 블루, 하늘색, 코랄/오렌지, 민트 에메랄드, 퍼플, 라임 옐로우의 조화로운 멀티 팔레트를 적용한다.

---

## 2. Dual-Theme Color System (색상 변수 정의)

### Light Theme Tokens (`[data-theme="light"]`, Default)
```css
:root, [data-theme="light"] {
  /* Canvas & Surface */
  --color-bg-base: #f8fafc;         /* Slate 50 (App Canvas Background) */
  --color-bg-surface: #ffffff;      /* Pure White Card Background */
  --color-bg-subtle: #f1f5f9;       /* Slate 100 (Secondary Container / Sub-card) */
  --color-bg-hover: #e2e8f0;        /* Slate 200 */

  /* Primary & Accents */
  --color-primary: #0066ff;         /* Vibrant Electric Royal Blue */
  --color-primary-hover: #0052cc;   /* Deep Royal Blue */
  --color-primary-light: #e0edff;   /* Soft Blue Tint */
  --gradient-primary: linear-gradient(135deg, #0066ff 0%, #3b82f6 100%);
  --gradient-glass: linear-gradient(135deg, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0.4) 100%);

  /* Borders & Shadows */
  --color-border: #f1f5f9;          /* Subtle Card Border */
  --color-border-strong: #e2e8f0;   /* Divider Line */
  --shadow-card: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.02);
  --shadow-hover: 0 10px 25px -3px rgba(0, 102, 255, 0.15);

  /* Typography Colors */
  --color-text-main: #0f172a;       /* Slate 900 (Main Title) */
  --color-text-body: #334155;       /* Slate 700 (Body Text) */
  --color-text-muted: #94a3b8;      /* Slate 400 (Subtext/Caption) */
  --color-text-on-primary: #ffffff; /* White Text on Primary Accent */
}
```

### Dark Theme Tokens (`[data-theme="dark"]`)
```css
[data-theme="dark"] {
  /* Canvas & Surface */
  --color-bg-base: #0f172a;         /* Slate 900 (Dark Canvas) */
  --color-bg-surface: #1e293b;      /* Slate 800 (Dark Card Background) */
  --color-bg-subtle: #334155;       /* Slate 700 (Sub Container) */
  --color-bg-hover: #475569;        /* Slate 600 */

  /* Primary & Accents */
  --color-primary: #6366f1;         /* Vibrant Indigo */
  --color-primary-hover: #4f46e5;   /* Deep Indigo */
  --color-primary-light: rgba(99, 102, 241, 0.2);
  --gradient-primary: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%);
  --gradient-glass: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.01) 100%);

  /* Borders & Shadows */
  --color-border: #334155;          /* Dark Border */
  --color-border-strong: #475569;   /* Dark Divider */
  --shadow-card: 0 4px 20px -2px rgba(0, 0, 0, 0.3);
  --shadow-hover: 0 10px 25px -3px rgba(99, 102, 241, 0.3);

  /* Typography Colors */
  --color-text-main: #f8fafc;       /* Slate 50 */
  --color-text-body: #cbd5e1;       /* Slate 300 */
  --color-text-muted: #64748b;      /* Slate 500 */
  --color-text-on-primary: #ffffff;
}
```

### Common Accents & Status Indicators
```css
:root {
  /* Shared Secondary Palette */
  --color-accent-sky: #38bdf8;      /* Sky Blue */
  --color-accent-cyan: #06b6d4;     /* Cyan 500 */
  --color-accent-coral: #ff6b4a;    /* Warm Coral/Orange */
  --color-accent-mint: #10b981;     /* Mint Emerald */
  --color-accent-purple: #8b5cf6;   /* Violet/Purple */
  --color-accent-yellow: #facc15;   /* Lime Yellow */

  /* Status Colors */
  --color-success: #10b981;  --color-success-bg: rgba(16, 185, 129, 0.12);
  --color-warning: #f59e0b;  --color-warning-bg: rgba(245, 158, 11, 0.12);
  --color-danger: #ef4444;   --color-danger-bg: rgba(239, 68, 68, 0.12);
  --color-info: #3b82f6;     --color-info-bg: rgba(59, 130, 246, 0.12);
}
```

---

## 3. Typography & Spacing Scale (타이포그래피 및 규격)

### Font Families
- **Primary Text**: `'Plus Jakarta Sans'`, `'Inter'`, `-apple-system`, `BlinkMacSystemFont`, `sans-serif`
- **Monospace & Code**: `'JetBrains Mono'`, `'Fira Code'`, `monospace`

### Typography Hierarchy
| Token | Size | Weight | Line Height | Usage |
|---|---|---|---|---|
| `--font-h1` | 1.875rem (30px) | 700 (Bold) | 1.2 | Main Page / Dashboard Title |
| `--font-h2` | 1.375rem (22px) | 600 (SemiBold) | 1.3 | Card Title / Section Header |
| `--font-h3` | 1.125rem (18px) | 600 (SemiBold) | 1.4 | Panel Title / Widget Header |
| `--font-stat` | 1.75rem (28px) | 700 (Bold) | 1.2 | KPI Metric Big Numbers |
| `--font-body` | 0.938rem (15px) | 400 (Regular) | 1.5 | Standard List & Paragraph |
| `--font-caption` | 0.813rem (13px)| 500 (Medium) | 1.4 | Badges, Subtext, Chart Labels |

### Spacing & Radius Tokens
- **Spacing Scale**: `4px` (`xs`), `8px` (`sm`), `16px` (`md`), `24px` (`lg`), `32px` (`xl`), `48px` (`2xl`)
- **Border Radius**:
  - `--radius-sm`: `6px` (Mini Tags, Input Badges)
  - `--radius-md`: `10px` (Active Nav Items, Sub-buttons)
  - `--radius-lg`: `18px` (Main Dashboard Cards, Panels, Modals)
  - `--radius-pill`: `9999px` (Pill Buttons, Status Badges, Avatars)

---

## 4. Component Rules & Web App Specifications (컴포넌트 규격)

### 1) Navigation & Sidebar
- **Active Navigation Item**: Background `var(--color-primary)`, Color `#ffffff`, Radius `10px`, Box Shadow `0 4px 14px rgba(0, 102, 255, 0.3)`
- **Inactive Item**: Color `var(--color-text-muted)`, Hover Background `var(--color-bg-subtle)`

### 2) KPI Summary Cards
- White/Dark Surface Card + `18px` Radius + `--shadow-card`
- **Icon Container**: Round Square (`44px` x `44px`, `border-radius: 12px`) with pastel tint accent background
- **Split Counter Layout**: Sub-metrics (Active / Upcoming / New) split by subtle vertical borders (`var(--color-border)`)

### 3) Data Tables (정렬 규격 수칙 필수)
- **Table Row**: Clean layout with hover highlight (`var(--color-bg-subtle)`)
- **Sort Indicators (정렬 기호 필수)**:
  - 비활성 정렬 열: 흐린 중립 기호 `⇅` (`opacity: 0.35`, Color `var(--color-text-muted)`)
  - 활성 정렬 열: 진한 방향 화살표 `▲` / `▼` (`font-weight: bold`, Color `var(--color-primary)`)

### 4) Charts & Visualizations
- **Line/Area Charts**: Smooth Spline Area Chart with soft gradient fill (`rgba(0,102,255,0.15)` to `transparent`)
- **Column Bar Charts**: Top-Rounded Column Bars (`border-top-left-radius: 6px`, `border-top-right-radius: 6px`), Active Bar Highlighted in Primary Royal Blue
- **Donut Charts**: Multi-color Segment Ring (Royal Blue, Sky Blue, Coral, Mint, Yellow)

### 5) Lists & Action Items
- User Avatar (`40px` Pill) + 2-Line Meta Text + Value Amount + Circle Action Button (`32px` x `32px`, Royal Blue, White Arrow `→`) + Soft Pill Badge (`9999px`)

---

## 5. Micro-animations & Transitions (애니메이션)

- **Default Transition**: `all 0.2s cubic-bezier(0.4, 0, 0.2, 1)`
- **Card Hover Elevation**: `transform: translateY(-2px)`, Shadow upgrade on hover
- **Active Press State**: `transform: scale(0.97)` on `:active`
- **Modal / Overlay Animation**: Fade in + Scale up (`0.95` -> `1.00`)

---

## 6. Linting & Validation Rules

- 디자인 수정 또는 UI 코드 작성 시 `npm.cmd run design:lint`를 수행한다.
- CSS 변수를 우회한 하드코딩 헥사코드, 순색 사용, 정렬 기호 누락을 린트로 차단한다.
