# Kaggle Capstone — Compliance Checklist (against the OFFICIAL rubric)

*"AI Agents: Intensive Vibe Coding" Capstone · Track: **Agents for Business** · ≤ 2,500-word writeup.*

> Mapped to the official rubric. **✅ done · ⚠️ action needed before submit.**

---

## A. Required submission deliverables

| # | Deliverable | Status | Notes |
|---|---|:--:|---|
| A1 | **Kaggle Writeup** (title, subtitle, ≤ 2,500 words, **select the Track**) | ✅ content / ⚠️ publish | `WRITEUP.md` = **1,784 words** (well under). Create it as a Kaggle Writeup, set Track = **Agents for Business**, then **Submit**. |
| A2 | **Media Gallery** — **cover image required** + the video | ⚠️ action | Add a cover image (use `docs/ARCHITECTURE.png`, or a UI screenshot of the Trust panel). The video also attaches here. |
| A3 | **Public Video** — YouTube, **≤ 5 min** | ⚠️ record | Script: `docs/VIDEO-SCRIPT.md`. Publish to YouTube **Public/Unlisted**. **Must show Antigravity + a deploy** (see B). |
| A4 | **Public Project Link** — live demo OR public code repo **with setup instructions** (no login/paywall) | ⚠️ push | Push `athena/` to a **public GitHub repo**; the `README.md` already has full setup. Paste the URL into the writeup. |

## B. Course concepts — demonstrate **≥ 3** (we cover 6)

| Key concept | Where the rubric wants it | ATHENA | Status |
|---|---|---|:--:|
| Agent / multi-agent system (ADK) | **Code** | `research-concierge/app/agent.py` (Sequential + Loop agents) | ✅ |
| MCP server | **Code** | `services/api/athena/mcp/server.py` (FastMCP) | ✅ |
| **Antigravity** | **Video** | built/audited in Antigravity — **must be shown on screen in the video** | ⚠️ video |
| Security features | Code or Video | Fernet vault, SSRF/rebind guard, bearer auth, injection fences | ✅ |
| Deployability | **Video** | `docker compose up` self-healing stack — **show it running in the video** | ⚠️ video |
| Agent skills (Agents CLI) | Code or Video | `agents-cli-manifest.yaml`, `api/skills.py` (rerank/verify) | ✅ |

> **4 concepts are already proven in code; 2 (Antigravity, Deployability) the rubric expects in the VIDEO.** So the video isn't optional polish — it carries two required concepts. Make sure the recording literally shows the **Antigravity IDE/workflow** and a **`docker compose up`**.

## C. Category 1 — The Pitch (30 pts)

| Criterion (pts) | ATHENA | Status |
|---|---|:--:|
| Core Concept & Value (10) | Verifiable-trust research analyst; agents are central + meaningful; squarely "Agents for Business" (due diligence / market research where a wrong citation costs money) | ✅ |
| YouTube Video (10) | Problem · Why-agents · Architecture · Demo · The Build — all in the script | ⚠️ record |
| Writeup (10) | Problem → solution → architecture → build journey, clearly articulated | ✅ |

## D. Category 2 — Implementation (70 pts)

| Criterion (pts) | ATHENA | Status |
|---|---|:--:|
| Technical Implementation (50) | Strong layered architecture; meaningful multi-agent design; clever tool use (MCP, cross-encoder rerank, entailment NLI, RRF, multi-hop); **heavily commented code**; 306+47 tests; 4-agent audit | ✅ |
| 🚨 **No API keys / passwords in code** | **Verified clean** — only fake test fixtures + a local-dev Postgres password | ✅ |
| Documentation (20) | `README.md` covers problem, solution, architecture, **setup instructions**, and a **diagram** | ✅ |

## E. Pre-submission punch-list (the only things left — all ACTIONS)

- [ ] **Record + upload the video** (YouTube, ≤5 min) — **show Antigravity on screen** and a **`docker compose up`** (those two concepts live in the video).
- [ ] **Push to a public GitHub repo**; paste the URL into `WRITEUP.md` (`<your public GitHub URL>`) + the submission's Project Link.
- [ ] **Cover image** in the Media Gallery (architecture PNG or a Trust-panel screenshot).
- [ ] **Create the Kaggle Writeup**, set Track = **Agents for Business**, attach video + project link, click **Submit** before the deadline.
- [ ] (Set the Figma board to "Anyone with the link can view" if you keep the interactive link.)

---

**Verdict:** the *project and documentation* meet the rubric — word count ✅, no secrets ✅, ≥3 concepts ✅ (6 covered), strong architecture + commented code ✅, README with setup + diagram ✅. The remaining gaps are **submission actions** (video, public repo, cover image, publish), not technical or documentation deficiencies.
